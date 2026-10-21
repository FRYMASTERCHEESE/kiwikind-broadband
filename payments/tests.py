"""Disposable accounts, fake API objects and real webhook signature verification."""
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from portal.models import AuditEvent, Invoice, Order
from portal.testing import owner_fixture
from . import gateway, service
from .admin import TestAgreementForm
from .models import TestAgreement, TestInvoice, TestEvent

TEST_ENV = {'KIWIKIND_STRIPE_SANDBOX':'1', 'STRIPE_TEST_SECRET_KEY':'sk_test_synthetic',
    'STRIPE_TEST_WEBHOOK_SECRET':'whsec_synthetic', 'STRIPE_TEST_ACCOUNT_ID':'acct_synthetic'}


@override_settings(PUBLIC_ORIGIN='https://kiwikind.example.invalid', PLAN_PUBLICATION_ENABLED=False)
class BillingTests(TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, TEST_ENV); self.env.start(); self.addCleanup(self.env.stop)
        self.owner = get_user_model().objects.create_user('operator', is_staff=True, is_superuser=True)
        self.user = get_user_model().objects.create_user('synthetic-customer', 'customer@example.invalid')
        self.other = get_user_model().objects.create_user('other-customer', 'other@example.invalid')
        self.client.force_login(self.user)
        self.a = TestAgreement.objects.create(user=self.user, created_by=self.owner,
            monthly_cents=1000, setup_cents=200, reviewed=True)
        self.api = MagicMock()
        self.patch = patch('payments.gateway.client', return_value=self.api)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.session = dict(id='cs_test_synthetic',object='checkout.session',livemode=False,
            mode='subscription',currency='nzd',amount_total=1200,client_reference_id=str(self.a.pk),
            metadata={'kiwikind_test_agreement':str(self.a.pk)},status='open',
            url='https://checkout.stripe.com/c/pay/cs_test_synthetic',subscription=None,customer=None)
        self.api.v1.checkout.sessions.create.side_effect=lambda *a,**kw:dict(self.session)
        self.api.v1.checkout.sessions.retrieve.side_effect=lambda *a,**kw:dict(self.session)

    def post(self, path='checkout', **changes):
        data = dict(agreement_id=str(self.a.pk),terms_version=str(self.a.terms_version),accept_test_recurring=True)
        data.update(changes)
        return self.client.post('/api/billing/'+path, json.dumps(data), content_type='application/json')

    def started(self):
        self.a.checkout_started_at = timezone.now()
        self.a.checkout_email = self.user.email
        self.a.checkout_id = self.session['id']; self.a.save()
        self.session.update(status='complete',subscription='sub_synthetic',customer='cus_synthetic')
        self.sub = dict(id='sub_synthetic',object='subscription',livemode=False,
            metadata={'kiwikind_test_agreement':str(self.a.pk)},customer='cus_synthetic',status='active',
            cancel_at_period_end=False,items={'data':[{'quantity':1,'price':{'unit_amount':1000,
                'currency':'nzd','recurring':{'interval':'month','interval_count':1}}}]})
        self.api.v1.subscriptions.retrieve.side_effect=lambda *a,**kw:dict(self.sub)
        return self.a

    def paid(self):
        self.started()
        self.invoice = dict(id='in_synthetic',object='invoice',livemode=False,
            parent={'subscription_details':{'subscription':'sub_synthetic'}},billing_reason='subscription_create',
            total=1200,amount_paid=1200,currency='nzd',customer='cus_synthetic',status='paid')
        self.api.v1.invoices.retrieve.side_effect=lambda *a,**kw:dict(self.invoice)
        self.api.v1.invoice_payments.list.return_value={'data':[dict(object='invoice_payment',livemode=False,
            invoice='in_synthetic',amount_paid=1200,currency='nzd',payment={'payment_intent':'pi_synthetic'})], 'has_more':False}
        self.pi = dict(id='pi_synthetic',object='payment_intent',livemode=False,amount_received=1200,
            currency='nzd',customer='cus_synthetic',status='succeeded')
        self.api.v1.payment_intents.retrieve.side_effect=lambda *a,**kw:dict(self.pi)
        self.charge = dict(id='ch_synthetic',object='charge',livemode=False,payment_intent='pi_synthetic',
            currency='nzd',amount=1200,amount_refunded=0,customer='cus_synthetic')
        self.api.v1.charges.retrieve.side_effect=lambda *a,**kw:dict(self.charge)
        return self.invoice

    def event(self, kind, obj, **changes):
        data = dict(id='evt_'+uuid.uuid4().hex,object='event',api_version=gateway.API_VERSION,
            livemode=False,type=kind,data={'object':obj})
        data.update(changes); return data

    def hook(self, event, secret=None, timestamp=None):
        body=json.dumps(event).encode(); stamp=int(time.time()) if timestamp is None else timestamp
        signature=hmac.new((secret or TEST_ENV['STRIPE_TEST_WEBHOOK_SECRET']).encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
        return self.client.post('/api/billing/webhook',body,content_type='application/json',
            HTTP_STRIPE_SIGNATURE=f't={stamp},v1={signature}')

    def test_anonymous_account_paths_denied(self):
        self.client.logout()
        for path in ('summary','checkout','cancel','refund'):
            response=self.client.get('/api/billing/'+path) if path=='summary' else self.post(path)
            self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.get('/billing/').status_code,302)
        self.assertEqual(self.client.get('/admin/billing-readiness/').status_code,404)

    def test_account_scoped_summary_no_provider_identifiers(self):
        TestAgreement.objects.create(user=self.other,created_by=self.owner,monthly_cents=999,reviewed=True,label='Another private agreement')
        response=self.client.get('/api/billing/summary')
        data=response.json(); self.assertEqual(len(data['agreements']),1)
        self.assertFalse(data['live_payments_enabled']);self.assertNotContains(response,'Another private')
        for field in ('checkout_email','checkout_id','customer_id','subscription_id','STRIPE_TEST_SECRET_KEY'):
            self.assertNotContains(response,field)
        self.assertIn('no-store',response['Cache-Control'])

    def test_unreviewed_agreement_hidden_and_unchargeable(self):
        self.a.reviewed=False;self.a.save()
        self.assertEqual(self.client.get('/api/billing/summary').json()['agreements'],[])
        self.assertEqual(self.post().status_code,404)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_other_account_checkout_cancel_denied(self):
        self.started();self.client.force_login(self.other)
        self.assertEqual(self.post().status_code,404)
        self.assertEqual(self.post('cancel',accept_test_cancel=True).status_code,404)

    def test_explicit_consent_required(self):
        for value in (False,'true',1,None):
            with self.subTest(value=value): self.assertEqual(self.post(accept_test_recurring=value).status_code,400)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_missing_and_invalid_identifiers_are_controlled(self):
        for identifier in ('','bad','00000000-0000-0000-0000-000000000000'):
            self.assertIn(self.post(agreement_id=identifier).status_code,(400,404))

    def test_changed_price_version_rejects_checkout(self):
        self.assertEqual(self.post(terms_version=str(uuid.uuid4())).status_code,409)
        self.api.v1.checkout.sessions.create.assert_not_called()
        self.a.refresh_from_db();self.assertIsNone(self.a.checkout_started_at)

    def test_missing_version_is_not_consent_to_current_price(self):
        self.assertEqual(self.post(terms_version=None).status_code,400)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_amount_is_server_owned_and_audited(self):
        response=self.post(monthly_cents=1,setup_cents=0,price='price_forged')
        self.assertEqual(response.status_code,200,response.content)
        self.assertTrue(response.json()['test_only'])
        args,kwargs=self.api.v1.checkout.sessions.create.call_args
        self.assertEqual(args[0]['line_items'][0]['price_data']['unit_amount'],1000)
        self.assertEqual(args[0]['line_items'][1]['price_data']['unit_amount'],200)
        self.assertTrue(kwargs['options']['idempotency_key'].endswith(str(self.a.pk)))
        self.assertTrue(AuditEvent.objects.filter(action='sandbox_recurring_consent',actor=self.user).exists())
        self.a.refresh_from_db();self.assertEqual(self.a.checkout_email,self.user.email)
        self.assertGreater(args[0]['expires_at'],time.time()+1800)

    def test_checkout_uses_supported_endive_card_selection(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        args, _ = self.api.v1.checkout.sessions.create.call_args
        self.assertNotIn('payment_method_types', args[0])
        self.assertEqual(args[0]['allowed_payment_method_types'], ['card'])

    def test_repeated_checkout_reuses_session(self):
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.api.v1.checkout.sessions.create.call_count,1)
        self.assertEqual(AuditEvent.objects.filter(action='sandbox_recurring_consent').count(),1)

    def test_network_error_retains_attempt_and_reuses_idempotency(self):
        import stripe
        self.api.v1.checkout.sessions.create.side_effect=stripe.APIConnectionError('Synthetic unavailable')
        self.assertEqual(self.post().status_code,503)
        first=self.api.v1.checkout.sessions.create.call_args
        self.a.refresh_from_db();self.assertIsNotNone(self.a.checkout_started_at)
        self.assertIsNone(self.a.checkout_id)
        self.api.v1.checkout.sessions.create.side_effect=lambda *a,**kw:dict(self.session)
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(first,self.api.v1.checkout.sessions.create.call_args)

    def test_old_attempt_never_recreated_after_idempotency_window(self):
        self.a.checkout_started_at=timezone.now()-timedelta(hours=24);self.a.save()
        self.assertEqual(self.post().status_code,409)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_hostile_or_live_checkout_response_rejected(self):
        for changes in ({'livemode':True},{'amount_total':1},{'currency':'usd'},
                {'url':'https://checkout.stripe.com.evil.invalid/c/pay/cs_test_x'},
                {'url':'https://checkout.stripe.com/c/pay/cs_live_x'},{'client_reference_id':str(uuid.uuid4())}):
            with self.subTest(changes=changes):
                original=dict(self.session);self.session.update(changes)
                self.assertEqual(self.post().status_code,409)
                self.session=original
        self.a.refresh_from_db();self.assertIsNone(self.a.checkout_id)

    def test_expired_checkout_not_replaced(self):
        self.session['status']='expired'
        self.assertEqual(self.post().status_code,409)
        self.assertFalse(TestInvoice.objects.exists())

    def test_csrf_enforced_for_browser_mutations(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/api/billing/checkout',json.dumps({'accept_test_recurring':True}),content_type='application/json').status_code,403)

    def test_webhook_valid_signature_reconciles_first_invoice_out_of_order(self):
        self.paid()
        response=self.hook(self.event('invoice.paid',self.invoice))
        self.assertEqual(response.status_code,200,response.content)
        self.a.refresh_from_db();self.assertEqual(self.a.subscription_id,'sub_synthetic')
        self.assertEqual(self.a.status,'active')
        record=TestInvoice.objects.get();self.assertEqual(record.amount_cents,1200)
        self.assertEqual(record.payment_intent,'pi_synthetic');self.assertEqual(record.status,'paid')
        self.assertFalse(Invoice.objects.exists());self.assertFalse(Order.objects.exists())

    def test_webhook_invalid_and_expired_signature_rejected(self):
        self.paid();event=self.event('invoice.paid',self.invoice)
        self.assertEqual(self.hook(event,secret='whsec_wrong').status_code,400)
        self.assertEqual(self.hook(event,timestamp=int(time.time())-600).status_code,400)
        self.assertFalse(TestEvent.objects.exists());self.assertFalse(TestInvoice.objects.exists())

    def test_webhook_live_account_and_version_rejected(self):
        self.paid()
        for changes in ({'livemode':True},{'account':'acct_other'},{'api_version':'2020-03-02'}):
            with self.subTest(changes=changes):self.assertEqual(self.hook(self.event('invoice.paid',self.invoice,**changes)).status_code,400)
        self.assertFalse(TestEvent.objects.exists())

    def test_duplicate_webhook_does_not_repeat_ledger_work(self):
        self.paid();event=self.event('invoice.paid',self.invoice)
        self.assertEqual(self.hook(event).status_code,200)
        calls=self.api.v1.invoices.retrieve.call_count
        response=self.hook(event);self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['duplicate'])
        self.assertEqual(self.api.v1.invoices.retrieve.call_count,calls)
        self.assertEqual(TestInvoice.objects.count(),1)

    def test_failed_reconciliation_rolls_back_receipt_for_retry(self):
        self.paid();self.invoice['total']=1;event=self.event('invoice.paid',self.invoice)
        self.assertEqual(self.hook(event).status_code,503)
        self.assertFalse(TestEvent.objects.exists());self.assertFalse(TestInvoice.objects.exists())
        self.invoice['total']=1200
        self.assertEqual(self.hook(event).status_code,200)
        self.assertEqual(TestEvent.objects.count(),1)

    def test_invoice_customer_mismatch_never_credits_account(self):
        self.paid();self.invoice['customer']='cus_other'
        self.assertEqual(self.hook(self.event('invoice.paid',self.invoice)).status_code,503)
        self.assertFalse(TestInvoice.objects.exists())

    def test_paid_invoice_requires_matching_payment_intent(self):
        self.paid();self.pi['customer']='cus_other'
        self.assertEqual(self.hook(self.event('invoice.paid',self.invoice)).status_code,503)
        self.assertFalse(TestInvoice.objects.exists())

    def test_delayed_failure_reads_current_paid_state(self):
        self.paid();old=dict(self.invoice,status='open',amount_paid=0)
        self.assertEqual(self.hook(self.event('invoice.payment_failed',old)).status_code,200)
        self.assertEqual(TestInvoice.objects.get().status,'paid')

    def test_delayed_active_event_cannot_revive_cancelled_subscription(self):
        self.started();old=dict(self.sub);self.sub['status']='canceled'
        self.assertEqual(self.hook(self.event('customer.subscription.updated',old)).status_code,200)
        self.a.refresh_from_db();self.assertEqual(self.a.status,'canceled')

    def test_subscription_cannot_bind_using_metadata_alone(self):
        self.started();self.session['subscription']='sub_other'
        self.assertEqual(self.hook(self.event('customer.subscription.created',self.sub)).status_code,503)
        self.a.refresh_from_db();self.assertIsNone(self.a.subscription_id)

    def test_unrelated_subscription_ignored(self):
        self.started();self.sub['metadata']={}
        self.assertEqual(self.hook(self.event('customer.subscription.created',self.sub)).status_code,200)
        self.a.refresh_from_db();self.assertIsNone(self.a.subscription_id)

    def test_renewal_excludes_oneoff_setup(self):
        self.paid();self.invoice.update(billing_reason='subscription_cycle',total=1000,amount_paid=1000)
        self.pi['amount_received']=1000
        self.api.v1.invoice_payments.list.return_value['data'][0]['amount_paid']=1000
        self.assertEqual(self.hook(self.event('invoice.paid',self.invoice)).status_code,200)
        self.assertEqual(TestInvoice.objects.get().amount_cents,1000)

    def test_explicit_cancellation_is_account_scoped_and_repeat_safe(self):
        self.started()
        with transaction.atomic():service.bind_subscription(self.api,'sub_synthetic')
        self.assertEqual(self.post('cancel',accept_test_cancel=False).status_code,400)
        def cancel(*args,**kw):self.sub['cancel_at_period_end']=True;return dict(self.sub)
        self.api.v1.subscriptions.update.side_effect=cancel
        self.assertEqual(self.post('cancel',accept_test_cancel=True).status_code,200)
        self.assertEqual(self.post('cancel',accept_test_cancel=True).status_code,200)
        self.assertEqual(self.api.v1.subscriptions.update.call_count,1)
        self.assertFalse(Order.objects.exists())

    def test_customer_and_spoofed_staff_cannot_refund(self):
        self.paid();self.hook(self.event('invoice.paid',self.invoice));ledger=TestInvoice.objects.get()
        self.assertEqual(self.post('refund',invoice_id=str(ledger.pk),accept_test_refund=True).status_code,404)
        self.user.email='kiwikindbroadband@gmail.com';self.user.is_staff=True;self.user.is_superuser=True;self.user.save()
        self.assertEqual(self.post('refund',invoice_id=str(ledger.pk),accept_test_refund=True).status_code,404)
        self.api.v1.refunds.create.assert_not_called()

    def test_owner_refund_requires_mfa_and_validated_intent(self):
        self.paid();self.hook(self.event('invoice.paid',self.invoice));ledger=TestInvoice.objects.get()
        owner_fixture(self.client,self.owner)
        self.api.v1.refunds.create.return_value=dict(id='re_synthetic',object='refund',amount=1200,currency='nzd',payment_intent='pi_synthetic',status='pending')
        response=self.post('refund',invoice_id=str(ledger.pk),accept_test_refund=True)
        self.assertEqual(response.status_code,200,response.content)
        ledger.refresh_from_db();self.assertEqual(ledger.refunded_cents,0)
        self.charge['amount_refunded']=1200
        self.assertEqual(self.hook(self.event('charge.refunded',self.charge)).status_code,200)
        ledger.refresh_from_db();self.assertEqual(ledger.refunded_cents,1200)
        self.assertEqual(self.post('refund',invoice_id=str(ledger.pk),accept_test_refund=True).status_code,409)
        session=self.client.session;session.pop('otp_device_id');session.save()
        self.assertEqual(self.post('refund',invoice_id=str(ledger.pk),accept_test_refund=True).status_code,404)

    def test_refund_and_dispute_reconcile_against_charge(self):
        self.paid();self.hook(self.event('invoice.paid',self.invoice))
        dispute=dict(id='dp_synthetic',object='dispute',livemode=False,charge='ch_synthetic',status='needs_response')
        self.api.v1.disputes.retrieve.return_value=dispute
        self.assertEqual(self.hook(self.event('charge.dispute.created',dispute)).status_code,200)
        self.assertEqual(TestInvoice.objects.get().dispute_status,'needs_response')

    def test_readiness_is_owner_mfa_only_and_never_returns_keys(self):
        self.assertEqual(self.client.get('/admin/billing-readiness/').status_code,404)
        owner_fixture(self.client,self.owner)
        response=self.client.get('/admin/billing-readiness/');self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['provider_tested'])
        self.assertNotContains(response,TEST_ENV['STRIPE_TEST_SECRET_KEY'])
        self.assertNotContains(response,TEST_ENV['STRIPE_TEST_WEBHOOK_SECRET'])

    def test_owner_admin_test_agreement_is_immutable_after_attempt(self):
        self.post();owner_fixture(self.client,self.owner)
        response=self.client.post(f'/admin/payments/testagreement/{self.a.pk}/change/',{'monthly_cents':1})
        self.assertEqual(response.status_code,403)
        self.a.refresh_from_db();self.assertEqual(self.a.monthly_cents,1000)

    def test_admin_form_rotation_changes_terms_version(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from portal.testing import owner_request
        device=owner_fixture(self.client,self.owner)
        request=RequestFactory().post('/admin/');owner_request(request,self.client,self.owner,device)
        initial=self.a.terms_version
        form=TestAgreementForm(instance=self.a,data=dict(user=self.user.pk,label='Changed terms',monthly_cents=1001,setup_cents=200,reviewed=True))
        self.assertTrue(form.is_valid(),form.errors)
        admin.site._registry[TestAgreement].save_model(request,form.instance,form,True)
        self.a.refresh_from_db();self.assertNotEqual(initial,self.a.terms_version)

    def test_page_renders_without_secret_or_inline_script(self):
        response=self.client.get('/billing/?returned=1')
        self.assertContains(response,'Payment testing only')
        self.assertContains(response,'csrfmiddlewaretoken')
        self.assertNotContains(response,TEST_ENV['STRIPE_TEST_SECRET_KEY'])
        self.assertIn('no-store',response['Cache-Control'])

    def test_sandbox_records_in_own_privacy_export_only(self):
        self.paid();self.hook(self.event('invoice.paid',self.invoice))
        data=self.client.get('/api/privacy/export').json()
        self.assertEqual(len(data['sandbox_billing_agreements']),1)
        self.assertEqual(len(data['sandbox_billing_invoices']),1)
        self.client.force_login(self.other)
        data=self.client.get('/api/privacy/export').json()
        self.assertEqual(data['sandbox_billing_agreements'],[])
        self.assertEqual(data['sandbox_billing_invoices'],[])

    def test_no_live_billing_intake_or_plan_publication_activated(self):
        self.assertFalse(self.client.get('/api/status').json()['billing_enabled'])
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
        self.assertFalse(TestInvoice.objects.exists())

    def test_actual_gateway_rejects_live_key_and_wrong_account(self):
        self.patch.stop()
        with patch.dict(os.environ,STRIPE_TEST_SECRET_KEY='sk_live_synthetic'):
            self.assertFalse(gateway.configured())
            with self.assertRaises(gateway.BillingUnavailable):gateway.client()
        with patch('stripe.StripeClient',return_value=self.api):
            self.api.v1.accounts.retrieve_current.return_value={'id':'acct_other','object':'account'}
            self.api.v1.balance.retrieve.return_value={'object':'balance','livemode':False}
            with self.assertRaises(gateway.BillingUnavailable):gateway.client()
            self.api.v1.accounts.retrieve_current.return_value={'id':'acct_synthetic','object':'account'}
            self.api.v1.balance.retrieve.return_value={'object':'balance','livemode':True}
            with self.assertRaises(gateway.BillingUnavailable):gateway.client()
            self.api.v1.balance.retrieve.return_value={'object':'balance','livemode':False}
            self.assertIs(gateway.client(),self.api)

    def test_missing_config_closes_webhook(self):
        with patch.dict(os.environ,KIWIKIND_STRIPE_SANDBOX='0'):
            self.assertFalse(gateway.configured())
            self.assertEqual(self.hook(self.event('anything',{})).status_code,503)
            self.assertFalse(self.client.get('/api/billing/summary').json()['test_enabled'])

    def test_redirect_allowlist_rejects_deceptive_urls(self):
        self.assertTrue(gateway.safe_checkout('https://checkout.stripe.com/c/pay/cs_test_synthetic#test'))
        for url in (None,'https://checkout.stripe.com.evil.invalid/c/pay/cs_test_x',
                'https://user@checkout.stripe.com/c/pay/cs_test_x','https://checkout.stripe.com:444/c/pay/cs_test_x',
                'https://checkout.stripe.com\n/c/pay/cs_test_x','https://checkout.stripe.com/c/pay/cs_live_x'):
            self.assertFalse(gateway.safe_checkout(url))

    def test_invoice_refreshed_after_agreement_lock(self):
        self.paid()
        stale=dict(self.invoice,status='open',amount_paid=0)
        self.api.v1.invoices.retrieve.side_effect=[stale,dict(self.invoice)]
        self.assertEqual(self.hook(self.event('invoice.payment_failed',stale)).status_code,200)
        self.assertEqual(TestInvoice.objects.get().status,'paid')

    def test_subscription_refreshed_after_agreement_lock(self):
        self.started();stale=dict(self.sub);latest=dict(self.sub,status='canceled')
        self.api.v1.subscriptions.retrieve.side_effect=[stale,latest]
        self.assertEqual(self.hook(self.event('customer.subscription.updated',stale)).status_code,200)
        self.a.refresh_from_db();self.assertEqual(self.a.status,'canceled')

    def test_owner_refund_confirmation_page_is_not_public(self):
        self.paid();self.hook(self.event('invoice.paid',self.invoice));ledger=TestInvoice.objects.get()
        path=f'/admin/payments/testinvoice/{ledger.pk}/refund/'
        self.assertIn(self.client.get(path).status_code,(302,403,404))
        owner_fixture(self.client,self.owner)
        response=self.client.get(path);self.assertContains(response,'full TEST refund')
        self.assertContains(response,'csrfmiddlewaretoken')
        self.assertEqual(self.client.post(path,{}).status_code,200)
        self.api.v1.refunds.create.assert_not_called()
