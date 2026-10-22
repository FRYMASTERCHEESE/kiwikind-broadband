import os
from io import StringIO
from unittest.mock import MagicMock, patch
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from payments import live_preflight
from payments.management.commands import stripe_inclusive_checkout_smoke as smoke


class ProviderReadinessTests(SimpleTestCase):
    def test_live_reads_use_no_mutations_and_do_not_return_customer_data(self):
        api = MagicMock()
        resources = [api.v1.checkout.sessions,api.v1.subscriptions,api.v1.customers,api.v1.products,
            api.v1.prices,api.v1.invoices,api.v1.invoice_payments,api.v1.payment_intents,api.v1.charges,api.v1.disputes]
        for resource in resources:
            resource.list.return_value = {'object':'list','data':[{'private':'NEVER_RETURN'}]}
        with patch('payments.live_preflight.live_gateway.client',return_value=api), patch(
                'payments.live_preflight.live_gateway.verified_gst_rate'):
            result=live_preflight.verify_payment_reads()
        self.assertEqual(len(result),11)
        self.assertTrue(all(result.values()))
        self.assertNotIn('NEVER_RETURN',str(result))
        self.assertTrue(all(call[0].endswith('.list') for call in api.mock_calls))

    def test_live_gst_failure_stops_provider_reads(self):
        with patch('payments.live_preflight.live_gateway.client',side_effect=ValueError('SECRET')):
            self.assertEqual(live_preflight.verify_payment_reads(),{'inclusive_nz_gst':False})

    def test_sandbox_provider_command_is_off_by_default(self):
        with patch.dict(os.environ,{smoke.FLAG:''}), patch.object(smoke.gateway,'client') as client:
            call_command('stripe_inclusive_checkout_smoke',stdout=StringIO())
            client.assert_not_called()

    @override_settings(PUBLIC_ORIGIN='https://example.invalid',PAGES_ENABLED=True,PAGES_URL='https://example.invalid/')
    def test_sandbox_uses_shared_gst_request_and_expires_without_payment(self):
        api=MagicMock()
        api.v1.tax_rates.create.return_value={'object':'tax_rate','id':'txr_testSynthetic','livemode':False,
            'inclusive':True,'country':'NZ','percentage':15}
        api.v1.tax_rates.update.return_value={'object':'tax_rate','id':'txr_testSynthetic','livemode':False,'active':False}
        session={'object':'checkout.session','id':'cs_test_synthetic','livemode':False,'mode':'subscription',
            'currency':'nzd','amount_total':2680,'status':'open','customer':None,'subscription':None,
            'url':'https://checkout.stripe.com/c/pay/cs_test_synthetic'}
        api.v1.checkout.sessions.create.return_value=session
        api.v1.checkout.sessions.retrieve.return_value=session
        api.v1.checkout.sessions.expire.return_value={**session,'status':'expired'}
        api.v1.checkout.sessions.list_line_items.return_value={'data':[
            {'amount_total':1450,'amount_tax':189,'price':{'tax_behavior':'inclusive','recurring':{'interval':'month'}}},
            {'amount_total':1230,'amount_tax':160,'price':{'tax_behavior':'inclusive','recurring':None}}]}
        output=StringIO()
        with patch.dict(os.environ,{smoke.FLAG:smoke.RUN}), patch.object(smoke,'datetime') as dt, patch.object(smoke.gateway,'client',return_value=api):
            dt.now.return_value=smoke.DEADLINE-smoke.timedelta(hours=2)
            call_command('stripe_inclusive_checkout_smoke',stdout=output)
        self.assertIn('QA: PASS',output.getvalue())
        params=api.v1.checkout.sessions.create.call_args.args[0]
        self.assertIsNone(params['customer_email'])
        self.assertEqual(params['subscription_data']['default_tax_rates'],['txr_testSynthetic'])
        self.assertNotIn('recurring',params['line_items'][1]['price_data'])
        api.v1.checkout.sessions.expire.assert_called_once_with('cs_test_synthetic')
        api.v1.tax_rates.update.assert_called_once_with('txr_testSynthetic',{'active':False})
        api.v1.payment_intents.create.assert_not_called()
        api.v1.customers.create.assert_not_called()

    def test_expired_test_window_cannot_call_stripe(self):
        with patch.dict(os.environ,{smoke.FLAG:smoke.RUN}), patch.object(smoke,'datetime') as dt, patch.object(smoke.gateway,'client') as client:
            dt.now.return_value=smoke.DEADLINE
            call_command('stripe_inclusive_checkout_smoke',stdout=StringIO())
            client.assert_not_called()
