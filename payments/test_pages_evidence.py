import os
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import TestAgreement, TestInvoice
from .pages_evidence import verify_owner_evidence


class PagesEvidenceTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('synthetic-owner')
        self.a=TestAgreement.objects.create(user=self.user,created_by=self.user,reviewed=True,
            monthly_cents=100,customer_id='cus_synthetic',subscription_id='sub_synthetic',checkout_id='cs_test_synthetic')
        TestInvoice.objects.create(agreement=self.a,provider_id='in_synthetic',amount_cents=100,
            status='paid',payment_intent='pi_synthetic')
        self.api=MagicMock()
        self.api.v1.accounts.retrieve_current.return_value={'object':'account','id':'acct_synthetic'}
        self.api.v1.balance.retrieve.return_value={'object':'balance','livemode':False}
        def obj(kind,identifier,**extra):return {'object':kind,'id':identifier,'livemode':False,**extra}
        self.api.v1.checkout.sessions.retrieve.return_value=obj('checkout.session','cs_test_synthetic',
            mode='subscription',currency='nzd',amount_total=100,client_reference_id=str(self.a.pk),
            metadata={'kiwikind_test_agreement':str(self.a.pk)},status='complete',
            subscription='sub_synthetic',customer='cus_synthetic')
        self.api.v1.subscriptions.retrieve.return_value=obj('subscription','sub_synthetic',
            customer='cus_synthetic',metadata={'kiwikind_test_agreement':str(self.a.pk)},cancel_at_period_end=True)
        self.api.v1.invoices.retrieve.return_value=obj('invoice','in_synthetic',customer='cus_synthetic',
            currency='nzd',total=100,amount_paid=100,status='paid',billing_reason='subscription_create',
            parent={'type':'subscription_details','subscription_details':{'subscription':'sub_synthetic'}})
        self.api.v1.invoice_payments.list.return_value={'has_more':False,'data':[obj('invoice_payment','inpay_synthetic',
            invoice='in_synthetic',currency='nzd',amount_paid=100,payment={'payment_intent':'pi_synthetic'})]}
        self.api.v1.payment_intents.retrieve.return_value=obj('payment_intent','pi_synthetic',
            customer='cus_synthetic',currency='nzd',amount_received=100,status='succeeded',latest_charge='ch_synthetic')
        self.api.v1.charges.retrieve.return_value=obj('charge','ch_synthetic',payment_intent='pi_synthetic',
            customer='cus_synthetic',currency='nzd',amount=100,amount_refunded=100)

    def verify(self):
        with patch.dict(os.environ,{'STRIPE_TEST_SECRET_KEY':'sk_test_synthetic',
            'STRIPE_TEST_WEBHOOK_SECRET':'whsec_synthetic','STRIPE_TEST_ACCOUNT_ID':'acct_synthetic'}),\
                patch('payments.pages_evidence.stripe.StripeClient',return_value=self.api):
            return verify_owner_evidence(self.user)

    def test_current_provider_objects_are_read_only_and_sanitized(self):
        r=self.verify();self.assertTrue(r['verified']);self.assertTrue(r['full_refund'])
        self.assertTrue(r['cancellation']);self.assertTrue(r['initial_paid_invoice'])
        self.assertNotIn('cus_synthetic',str(r));self.assertNotIn('sk_test',str(r))
        for call in self.api.mock_calls:
            self.assertIn(call[0],['v1.accounts.retrieve_current','v1.balance.retrieve',
                'v1.checkout.sessions.retrieve','v1.subscriptions.retrieve','v1.invoices.retrieve',
                'v1.payment_intents.retrieve','v1.charges.retrieve','v1.invoice_payments.list'])
        self.assertEqual(TestAgreement.objects.count(),1);self.assertEqual(TestInvoice.objects.count(),1)

    def test_live_mode_wrong_binding_and_exceptions_fail_closed(self):
        for obj,key,value in [(self.api.v1.balance.retrieve.return_value,'livemode',True),
                (self.api.v1.charges.retrieve.return_value,'customer','cus_unrelated'),
                (self.api.v1.invoices.retrieve.return_value,'total',999)]:
            prior=obj[key];obj[key]=value;self.assertFalse(self.verify()['verified']);obj[key]=prior
        self.api.v1.accounts.retrieve_current.side_effect=Exception('secret provider payload')
        r=self.verify();self.assertFalse(r['verified']);self.assertNotIn('secret provider payload',str(r))
