import hashlib
import hmac
import json
import time
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from .models import Invoice, StripePayment, StripeEvent, BillingAgreement

ENV={'STRIPE_TEST_CHECKOUT_ENABLED':'1','STRIPE_TEST_PRICE_REVIEWED':'1',
     'STRIPE_TEST_SECRET_KEY':'sk_test_synthetic','STRIPE_TEST_WEBHOOK_SECRET':'whsec_synthetic'}

class BillingSafetyTests(TestCase):
    def setUp(self):
        self.enterContext(override_settings(PUBLIC_ORIGIN='https://kiwikind.example.invalid'))
        self.enterContext(patch.dict('os.environ',ENV))
        self.user=get_user_model().objects.create_user('synthetic@example.invalid',password='Synthetic-Only-Password-123!')
        self.other=get_user_model().objects.create_user('other@example.invalid',password='Synthetic-Only-Password-123!')
        self.invoice=Invoice.objects.create(user=self.user,supplier_reference='synthetic',amount_cents=10000,due_date='2026-12-01',status='unpaid',sandbox=True)
        self.client.force_login(self.user)
    def post(self,path,data):return self.client.post('/api/billing/stripe/'+path,data,content_type='application/json')
    def event(self,kind,obj,eid='evt_test',live=False,signature=True,timestamp=None):
        raw=json.dumps({'id':eid,'type':kind,'livemode':live,'data':{'object':obj}}).encode()
        t=timestamp or int(time.time())
        sig=hmac.new(b'whsec_synthetic',str(t).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return self.client.post('/api/billing/stripe/webhook',raw,content_type='application/json',HTTP_STRIPE_SIGNATURE=f't={t},v1={sig}' if signature else 'bad')
    @patch('stripe.checkout.Session.create')
    def test_server_amount_and_session_reuse(self,create):
        create.return_value={'id':'cs_test_1','url':'https://checkout.stripe.com/c/test','livemode':False}
        data={'invoice_id':str(self.invoice.pk),'amount_cents':1}
        self.assertEqual(self.post('test-checkout',data).status_code,200)
        self.assertEqual(create.call_args.kwargs['line_items'][0]['price_data']['unit_amount'],10000)
        with patch('stripe.checkout.Session.retrieve',return_value={**create.return_value,'status':'open'}):
            self.assertEqual(self.post('test-checkout',data).status_code,200)
        self.assertEqual(create.call_count,1)
    @patch('stripe.checkout.Session.create')
    def test_other_customer_and_real_ledger_never_charge(self,create):
        self.client.force_login(self.other)
        self.assertEqual(self.post('test-checkout',{'invoice_id':str(self.invoice.pk)}).status_code,404)
        self.client.force_login(self.user);self.invoice.sandbox=False;self.invoice.save()
        self.assertEqual(self.post('test-checkout',{'invoice_id':str(self.invoice.pk)}).status_code,404)
        create.assert_not_called()
    @patch('stripe.checkout.Session.create')
    def test_expired_retry_key_does_not_create_new_checkout(self,create):
        from datetime import timedelta
        from django.utils import timezone
        StripePayment.objects.create(invoice=self.invoice,amount_cents=10000,created_at=timezone.now()-timedelta(hours=24))
        self.assertEqual(self.post('test-checkout',{'invoice_id':str(self.invoice.pk)}).status_code,409)
        create.assert_not_called()
    def test_malformed_uuid_is_400(self):
        self.assertEqual(self.post('test-checkout',{'invoice_id':'bogus'}).status_code,400)
    def test_bad_expired_and_live_signatures(self):
        for kw in [{'signature':False},{'timestamp':int(time.time())-600},{'live':True}]:
            self.assertEqual(self.event('checkout.session.completed',{},**kw).status_code,400)
        self.assertEqual(StripeEvent.objects.count(),0)
    def payment_event(self,**extra):
        obj={'id':'cs_test_1','livemode':False,'mode':'payment','payment_status':'paid','currency':'nzd','amount_total':10000,'payment_intent':'pi_test'}
        obj.update(extra);return obj
    def test_verified_payment_replay_is_idempotent(self):
        StripePayment.objects.create(invoice=self.invoice,session_id='cs_test_1',amount_cents=10000)
        for _ in range(2):self.assertEqual(self.event('checkout.session.completed',self.payment_event()).status_code,200)
        self.invoice.refresh_from_db();self.assertEqual(self.invoice.status,'paid')
        self.assertEqual(StripeEvent.objects.count(),1)
    def test_mismatch_rolls_back_receipt_for_retry(self):
        StripePayment.objects.create(invoice=self.invoice,session_id='cs_test_1',amount_cents=10000)
        self.assertEqual(self.event('checkout.session.completed',self.payment_event(amount_total=1)).status_code,503)
        self.assertEqual(StripeEvent.objects.count(),0)
        self.invoice.refresh_from_db();self.assertEqual(self.invoice.status,'unpaid')
    @patch('stripe.checkout.Session.create')
    def test_subscription_needs_review_consent_and_ownership(self,create):
        a=BillingAgreement.objects.create(user=self.user,monthly_cents=9990,setup_cents=0)
        d={'agreement_id':str(a.id),'accept_test_recurring':True}
        self.assertEqual(self.post('test-subscribe',d).status_code,404)
        a.synthetic_reviewed=True;a.save()
        self.assertEqual(self.post('test-subscribe',{'agreement_id':str(a.id)}).status_code,400)
        self.client.force_login(self.other)
        self.assertEqual(self.post('test-subscribe',d).status_code,404)
        self.client.force_login(self.user)
        create.return_value={'id':'cs_test_sub','url':'https://checkout.stripe.com/c/sub','livemode':False}
        self.assertEqual(self.post('test-subscribe',d).status_code,200)
        self.assertEqual(create.call_args.kwargs['mode'],'subscription')
        self.assertEqual(create.call_args.kwargs['line_items'][0]['price_data']['recurring'],{'interval':'month'})
    @patch('stripe.InvoicePayment.list',return_value={'data':[{'status':'paid','payment':{'payment_intent':'pi_recurring'}}]})
    @patch('stripe.Invoice.retrieve')
    def test_recurring_invoice_reconciles_current_state(self,retrieve,payments):
        from django.utils import timezone
        a=BillingAgreement.objects.create(user=self.user,monthly_cents=9990,setup_cents=500,synthetic_reviewed=True,subscription_id='sub_test',consent_at=timezone.now())
        obj={'id':'in_test','livemode':False,'parent':{'subscription_details':{'subscription':'sub_test'}},'billing_reason':'subscription_create','currency':'nzd','total':10490,'status':'paid'}
        retrieve.return_value=obj
        self.assertEqual(self.event('invoice.paid',obj).status_code,200)
        ledger=Invoice.objects.get(supplier_reference='stripe-test:in_test')
        self.assertTrue(ledger.sandbox);self.assertEqual(ledger.status,'paid');self.assertEqual(ledger.amount_cents,10490)
        self.assertEqual(StripePayment.objects.get(provider_invoice_id='in_test').payment_intent,'pi_recurring')
        self.assertEqual(self.event('invoice.payment_failed',obj,eid='evt_old').status_code,200)
        ledger.refresh_from_db();self.assertEqual(ledger.status,'paid')
    def test_invoice_before_subscription_retries(self):
        obj={'id':'in_first','livemode':False,'subscription':'sub_unknown'}
        self.assertEqual(self.event('invoice.paid',obj).status_code,503)
        self.assertFalse(StripeEvent.objects.exists())
    @patch('stripe.Charge.retrieve')
    def test_refund_reconciles_current_amount(self,retrieve):
        p=StripePayment.objects.create(invoice=self.invoice,session_id='cs_test',amount_cents=10000,payment_intent='pi_test',paid=True)
        obj={'id':'ch_test','livemode':False,'payment_intent':'pi_test','currency':'nzd','amount':10000,'amount_refunded':10000}
        retrieve.return_value=obj
        self.assertEqual(self.event('charge.refunded',obj).status_code,200)
        p.refresh_from_db();self.assertEqual(p.refunded_cents,10000)
    @patch('stripe.Refund.create')
    def test_customer_cannot_refund(self,create):
        r=self.client.post('/api/admin/billing/test-refund',{'payment_id':1},content_type='application/json')
        self.assertEqual(r.status_code,404);create.assert_not_called()
    @patch('stripe.Subscription.modify')
    def test_cancel_is_owned_and_period_end_only(self,modify):
        a=BillingAgreement.objects.create(user=self.user,monthly_cents=9990,synthetic_reviewed=True,subscription_id='sub_test')
        self.client.force_login(self.other)
        self.assertEqual(self.post('test-cancel',{'agreement_id':str(a.id)}).status_code,404)
        modify.assert_not_called()
        self.client.force_login(self.user)
        self.assertEqual(self.post('test-cancel',{'agreement_id':str(a.id)}).status_code,200)
        self.assertTrue(modify.call_args.kwargs['cancel_at_period_end'])
