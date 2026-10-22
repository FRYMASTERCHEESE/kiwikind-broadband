"""Isolated synthetic provider objects; never contacts Stripe or charges money."""
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
from portal.testing import owner_fixture
from . import live_gateway as gateway, live_service as service
from .live_models import LiveAgreement, LiveInvoice, LiveEvent

ENV={'KIWIKIND_LIVE_BILLING_ENABLED':'1','KIWIKIND_LIVE_RELEASE_APPROVED':'1',
    'STRIPE_LIVE_SECRET_KEY':'rk_live_synthetic','STRIPE_LIVE_ACCOUNT_ID':'acct_synthetic',
    'STRIPE_LIVE_WEBHOOK_SECRET':'whsec_synthetic','STRIPE_LIVE_GST_RATE_ID':'txr_synthetic'}


@override_settings(PUBLIC_ORIGIN='https://kiwikind.example.invalid', PAGES_ENABLED=True,
    PAGES_URL='https://frymastercheese.github.io/kiwikind-broadband-website/',
    PAGES_API_ONLY=True, ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True)
class LiveBillingTests(TestCase):
    def setUp(self):
        env=patch.dict(os.environ,ENV);env.start();self.addCleanup(env.stop)
        U=get_user_model()
        self.owner=U.objects.create_user('operator',is_staff=True,is_superuser=True)
        self.owner_client=Client();owner_fixture(self.owner_client,self.owner)
        self.user=U.objects.create_user('synthetic-customer','customer@example.invalid')
        self.other=U.objects.create_user('other','other@example.invalid')
        self.client.force_login(self.user)
        self.a=LiveAgreement.objects.create(user=self.user,created_by=self.owner,
            label='Synthetic service',service_reference='synthetic-only',
            source_monthly_cents=1000,source_setup_cents=200,service_terms='Synthetic written terms',
            supplier_confirmed=True,bill_from=timezone.localdate(),reviewed=True,
            approved_by=self.owner,approved_at=timezone.now())
        self.api=MagicMock()
        self.api.v1.tax_rates.retrieve.return_value=dict(id='txr_synthetic',object='tax_rate',livemode=True,active=True,inclusive=True,percentage=15,country='NZ')
        mock=patch('payments.live_gateway.client',return_value=self.api);mock.start();self.addCleanup(mock.stop)
        self.session=dict(id='cs_live_synthetic',object='checkout.session',livemode=True,
            mode='subscription',currency='nzd',amount_total=2680,client_reference_id=str(self.a.pk),
            metadata={'kiwikind_live_agreement':str(self.a.pk)},status='open',
            url='https://checkout.stripe.com/c/pay/cs_live_synthetic',subscription=None,customer=None)
        self.api.v1.checkout.sessions.create.side_effect=lambda *a,**kw:dict(self.session)
        self.api.v1.checkout.sessions.retrieve.side_effect=lambda *a,**kw:dict(self.session)

    def post(self,**changes):
        data=dict(agreement_id=str(self.a.pk),terms_version=str(self.a.terms_version),accept_live_recurring=True)
        data.update(changes)
        return self.client.post('/api/payments/checkout',json.dumps(data),content_type='application/json')

    def started(self):
        self.a.checkout_started_at=timezone.now();self.a.checkout_email=self.user.email;self.a.gst_rate_id='txr_synthetic'
        self.a.checkout_id=self.session['id'];self.a.save()
        self.session.update(status='complete',subscription='sub_synthetic',customer='cus_synthetic')
        self.sub=dict(id='sub_synthetic',object='subscription',livemode=True,
            metadata={'kiwikind_live_agreement':str(self.a.pk)},customer='cus_synthetic',status='active',
            cancel_at_period_end=False,default_tax_rates=[{'id':'txr_synthetic'}],items={'data':[{'quantity':1,'price':{'unit_amount':1450,
                'currency':'nzd','recurring':{'interval':'month','interval_count':1}}}]})
        self.api.v1.subscriptions.retrieve.side_effect=lambda *a,**kw:dict(self.sub)

    def hook(self,kind,obj,**changes):
        event=dict(id='evt_'+uuid.uuid4().hex,object='event',livemode=True,
            api_version=gateway.API_VERSION,type=kind,data={'object':obj})
        event.update(changes);body=json.dumps(event).encode();stamp=int(time.time())
        sig=hmac.new(ENV['STRIPE_LIVE_WEBHOOK_SECRET'].encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
        return self.client.post('/api/payments/webhook',body,content_type='application/json',
            HTTP_STRIPE_SIGNATURE=f't={stamp},v1={sig}')

    def test_final_inclusive_amounts_and_nonrecurring_setup(self):
        self.assertEqual(self.post().status_code,200)
        params=self.api.v1.checkout.sessions.create.call_args.args[0]
        monthly,setup=params['line_items']
        self.assertEqual(monthly['price_data']['unit_amount'],1450)
        self.assertEqual(setup['price_data']['unit_amount'],1230)
        self.assertEqual(monthly['price_data']['recurring'],{'interval':'month'})
        self.assertNotIn('recurring',setup['price_data'])
        self.assertEqual(monthly['price_data']['tax_behavior'],'inclusive')
        self.assertFalse(params['automatic_tax']['enabled'])
        self.assertEqual(params['subscription_data']['default_tax_rates'],['txr_synthetic'])
        self.assertTrue(params['success_url'].startswith('https://frymastercheese.github.io/'))

    def test_anonymous_and_other_customer_cannot_checkout(self):
        self.client.logout();self.assertEqual(self.post().status_code,401)
        self.client.force_login(self.other);self.assertEqual(self.post().status_code,404)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_live_payment_writes_require_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        for action in ('checkout','cancel'):
            response=client.post('/api/payments/'+action,json.dumps({'agreement_id':str(self.a.pk),'accept_live_recurring':True,'accept_live_cancel':True}),content_type='application/json')
            self.assertEqual(response.status_code,403)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_explicit_consent_and_current_terms_required(self):
        self.assertEqual(self.post(accept_live_recurring=False).status_code,400)
        self.assertEqual(self.post(terms_version=str(uuid.uuid4())).status_code,409)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_new_all_in_agreement_amount_reaches_stripe_checkout(self):
        self.a.pricing_policy = 'all_in_v2'
        self.a.save()
        self.assertEqual((self.a.monthly_cents, self.a.setup_cents), (1532, 1273))
        self.session['amount_total'] = 2805
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        params = self.api.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params['mode'], 'subscription')
        self.assertEqual(params['line_items'][0]['price_data']['unit_amount'], 1532)
        self.assertEqual(params['line_items'][1]['price_data']['unit_amount'], 1273)
        self.assertNotIn('recurring', params['line_items'][1]['price_data'])
        self.assertEqual(params['line_items'][0]['price_data']['tax_behavior'], 'inclusive')
        self.assertEqual(self.a.monthly_cents + self.a.setup_cents, 2805)

    def test_browser_cannot_change_approved_price(self):
        self.assertEqual(self.post(monthly_cents=1,setup_cents=0).status_code,200)
        self.assertEqual(self.api.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'],1450)

    def test_unconfirmed_supply_or_future_start_cannot_charge(self):
        self.a.bill_from=timezone.localdate()+timedelta(days=1);self.a.save()
        self.assertEqual(self.post().status_code,400)
        self.a.bill_from=timezone.localdate();self.a.supplier_confirmed=False;self.a.save()
        self.assertEqual(self.post().status_code,400)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_unapproved_owner_cannot_create_payable_offer(self):
        self.a.approved_by=self.other;self.a.save()
        self.assertEqual(self.post().status_code,404)

    def test_new_checkout_disabled_without_both_switches(self):
        # Do not mock the configuration guard in this test.
        with patch('payments.live_views.gateway.client',side_effect=gateway.BillingUnavailable):
            with patch.dict(os.environ,{'KIWIKIND_LIVE_BILLING_ENABLED':'0'}):
                self.assertFalse(gateway.configured())
                self.assertEqual(self.post().status_code,503)

    def test_test_key_and_test_object_rejected(self):
        with patch.dict(os.environ,{'STRIPE_LIVE_SECRET_KEY':'rk_test_synthetic'}):
            self.assertFalse(gateway.credentials_ready())
        with self.assertRaises(gateway.ReconciliationError):gateway.live_object({'livemode':False})
        self.assertFalse(gateway.safe_checkout('https://checkout.stripe.com/c/pay/cs_test_no'))
        self.assertFalse(gateway.safe_checkout('https://checkout.stripe.com.evil.invalid/c/pay/cs_live_no'))

    def test_retry_reuses_session_and_price_becomes_immutable(self):
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post().status_code,200)
        self.api.v1.checkout.sessions.create.assert_called_once()
        self.a.refresh_from_db();self.a.source_monthly_cents=2000
        with self.assertRaises(ValidationError):self.a.save()

    def test_lost_provider_response_has_stable_idempotency(self):
        self.api.v1.checkout.sessions.create.side_effect=gateway.BillingUnavailable
        self.assertEqual(self.post().status_code,503)
        key=self.api.v1.checkout.sessions.create.call_args.kwargs['options']['idempotency_key']
        self.assertEqual(self.post().status_code,503)
        self.assertEqual(key,self.api.v1.checkout.sessions.create.call_args.kwargs['options']['idempotency_key'])

    def test_webhook_signature_and_mode_checked(self):
        self.assertEqual(self.client.post('/api/payments/webhook','{}',content_type='application/json').status_code,400)
        self.assertEqual(self.hook('checkout.session.completed',self.session,livemode=False).status_code,400)
        self.assertEqual(LiveEvent.objects.count(),0)

    def test_webhook_binds_subscription_and_is_replay_safe(self):
        self.started()
        self.assertEqual(self.hook('checkout.session.completed',self.session,id='evt_replay').status_code,200)
        self.assertEqual(self.hook('checkout.session.completed',self.session,id='evt_replay').status_code,200)
        self.assertEqual(LiveEvent.objects.count(),1)
        self.a.refresh_from_db();self.assertEqual(self.a.status,'active')
        self.assertEqual(self.a.customer_id,'cus_synthetic')

    def test_mismatched_recurring_amount_rolls_back_webhook(self):
        self.started();self.sub['items']['data'][0]['price']['unit_amount']=2680
        self.assertEqual(self.hook('checkout.session.completed',self.session).status_code,503)
        self.assertEqual(LiveEvent.objects.count(),0)

    def test_renewal_excludes_setup_and_current_state_wins(self):
        self.started()
        invoice=dict(id='in_cycle',object='invoice',livemode=True,
            parent={'subscription_details':{'subscription':'sub_synthetic'}},billing_reason='subscription_cycle',
            total=1450,currency='nzd',customer='cus_synthetic',status='open')
        self.api.v1.invoices.retrieve.return_value=invoice
        self.assertEqual(self.hook('invoice.payment_failed',invoice).status_code,200)
        self.assertEqual(LiveInvoice.objects.get().amount_cents,1450)
        invoice['total']=2680
        self.assertEqual(self.hook('invoice.finalized',invoice).status_code,503)

    def test_export_includes_own_live_records_without_supplier_costs(self):
        data=self.client.get('/api/privacy/export').json()
        self.assertEqual(len(data['payment_agreements']),1)
        self.assertNotIn('source_monthly_cents',data['payment_agreements'][0])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/privacy/export').json()['payment_agreements'],[])

    def test_owner_api_cannot_bypass_approval_and_calculates_totals(self):
        values=dict(user=self.user.pk,label='Second synthetic',service_reference='synthetic-second',
            source_monthly_cents=2000,source_setup_cents=0,service_terms='Written synthetic terms',
            bill_from=str(timezone.localdate()),supplier_confirmed=True,reviewed=True)
        url='/api/owner/operations/payment-agreements'
        response=self.owner_client.post(url,json.dumps({'values':values}),content_type='application/json')
        self.assertEqual(response.status_code,400)
        values['confirm_live_offer']=True
        response=self.owner_client.post(url,json.dumps({'values':values}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['record']['monthly_cents'],2600)
        self.assertEqual(response.json()['record']['setup_cents'],1000)

    def test_missing_setup_prevents_approval(self):
        self.a.source_setup_cents=None
        with self.assertRaises(ValidationError):self.a.full_clean()

    def test_exclusive_or_wrong_gst_rate_blocks_checkout(self):
        self.api.v1.tax_rates.retrieve.return_value.update(inclusive=False)
        self.assertEqual(self.post().status_code,503)
        self.api.v1.checkout.sessions.create.assert_not_called()
        self.a.refresh_from_db();self.assertIsNone(self.a.checkout_started_at)

    def test_cancellation_and_history_remain_after_owner_deactivated(self):
        self.started()
        with transaction.atomic():service.bind_subscription(self.api,'sub_synthetic')
        self.owner.is_active=False;self.owner.save()
        self.assertEqual(len(self.client.get('/api/payments/summary').json()['agreements']),1)
        self.api.v1.subscriptions.update.return_value={**self.sub,'cancel_at_period_end':True}
        response=self.client.post('/api/payments/cancel',json.dumps({'agreement_id':str(self.a.pk),'accept_live_cancel':True}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)

    def test_signed_webhook_remains_active_while_new_checkouts_paused(self):
        self.started()
        with patch.dict(os.environ,{'KIWIKIND_LIVE_BILLING_ENABLED':'0'}):
            self.assertFalse(gateway.configured())
            self.assertEqual(self.hook('checkout.session.completed',self.session).status_code,200)

    def test_real_signature_invalid_account_or_version_rejected(self):
        for changes in ({'account':'acct_foreign'},{'api_version':'old-version'}):
            self.assertEqual(self.hook('checkout.session.completed',self.session,**changes).status_code,400)

    def test_paid_invoice_binds_actual_payment_intent(self):
        self.started()
        invoice=dict(id='in_first',object='invoice',livemode=True,
            parent={'subscription_details':{'subscription':'sub_synthetic'}},billing_reason='subscription_create',
            total=2680,amount_paid=2680,currency='nzd',customer='cus_synthetic',status='paid')
        self.api.v1.invoices.retrieve.return_value=invoice
        self.api.v1.invoice_payments.list.return_value={'data':[dict(object='invoice_payment',livemode=True,
            invoice='in_first',amount_paid=2680,currency='nzd',payment={'payment_intent':'pi_synthetic'})],'has_more':False}
        self.api.v1.payment_intents.retrieve.return_value=dict(id='pi_synthetic',object='payment_intent',livemode=True,
            amount_received=2680,currency='nzd',customer='cus_synthetic',status='succeeded')
        self.assertEqual(self.hook('invoice.paid',invoice).status_code,200)
        self.assertEqual(LiveInvoice.objects.get().payment_intent,'pi_synthetic')
        self.api.v1.charges.retrieve.return_value=dict(id='ch_synthetic',object='charge',livemode=True,
            payment_intent='pi_synthetic',currency='nzd',amount=2680,amount_refunded=2680,customer='cus_synthetic')
        self.assertEqual(self.hook('charge.refunded',{'id':'ch_synthetic','object':'charge','livemode':True}).status_code,200)
        self.assertEqual(LiveInvoice.objects.get().refunded_cents,2680)
