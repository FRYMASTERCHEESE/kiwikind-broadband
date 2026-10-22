import json
import os
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .broadband import quote, ORDER_CONSENT
from .models import Order, BroadbandOrder, WholesaleOrder
from .testing import owner_fixture
from payments.live_models import LiveAgreement


@override_settings(BROADBAND_CATALOGUE_ENABLED=True,PUBLIC_ORIGIN='https://kiwikind.example.invalid')
class BroadbandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('broadband-customer', 'buyer@example.invalid')
        self.client.force_login(self.user)
        self.owner = get_user_model().objects.create_superuser('operator', 'operator@example.invalid', 'Synthetic-password-only')
        self.operator = Client()
        owner_fixture(self.operator, self.owner)
        self.selection = quote('ufb', ['3'])
        self.data = dict(product_id='ufb', selections=['3'], quote_version=self.selection['quote_version'],
            address='10 Synthetic Test Street', postcode='1010', contact_name='Synthetic Customer', phone='',
            idempotency_key=str(uuid.uuid4()), consent_version=ORDER_CONSENT, accept_review=True)

    def submit(self, **changes):
        return self.client.post('/api/broadband/orders', json.dumps({**self.data, **changes}), content_type='application/json')

    def test_all_screenshot_categories_and_inclusive_additions(self):
        response = self.client.get('/api/broadband/catalogue').json()
        self.assertEqual(len(response['products']), 7)
        self.assertFalse(response['supplier_orders_enabled'])
        self.assertEqual(response['payment_timing'], 'after_connection_confirmation')
        self.assertEqual([len(p['groups'][0]['options']) for p in response['products'][:3]], [5, 5, 21])
        self.assertNotIn('source_monthly_cents', json.dumps(response))
        self.assertEqual(self.selection['monthly_cents'], 8341) # 69.92 * 1.15 + 3.00
        self.assertEqual(self.selection['setup_cents'], 1000)
        self.assertEqual(self.selection['first_invoice_cents'], 9341)
        mobile = quote('mobile-4g', ['0', '0', '0'])
        self.assertEqual((mobile['monthly_cents'], mobile['setup_cents']), (1450, 2150))
        vector = quote('vector', ['0', '5', '0', '1'])
        self.assertEqual(vector['monthly_cents'], 27764)
        self.assertEqual(vector['setup_cents'], 13650) # (25 + 85) * 1.15 + 10
        self.assertEqual(vector['first_invoice_cents'], vector['monthly_cents'] + vector['setup_cents'])

    def test_unknown_fees_and_metered_usage_are_not_silently_zero(self):
        result = quote('vector', ['1', '1', '0', '0'])
        self.assertIsNone(result['setup_cents'])
        self.assertIsNone(result['first_invoice_cents'])
        self.assertIn('0.0805/GB', result['usage'][0])
        self.assertFalse(result['quote_complete'])

    def test_quote_invalid_options_and_closed_gate(self):
        for selection in ([], ['99'], [True], [3], {}, None):
            with self.assertRaises(ValueError): quote('ufb', selection)
        self.assertEqual(self.client.get('/api/broadband/quote?product=ufb&options=3').json()['monthly_cents'], 8341)
        with override_settings(BROADBAND_CATALOGUE_ENABLED=False):
            self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])
            self.assertEqual(self.submit().status_code, 503)
            self.assertEqual(self.client.get('/api/broadband/quote?product=ufb&options=3').status_code, 503)

    def test_order_uses_server_prices_and_never_calls_stripe_or_supplier(self):
        with patch('payments.live_gateway.client') as stripe:
            response = self.submit(monthly_cents=1, setup_cents=0)
            self.assertEqual(response.status_code, 201)
            stripe.assert_not_called()
        self.assertEqual(BroadbandOrder.objects.get().quote['monthly_cents'], 8341)
        self.assertFalse(LiveAgreement.objects.exists())
        self.assertFalse(WholesaleOrder.objects.exists())
        self.assertNotIn('source_', json.dumps(response.json()))

    def test_consent_stale_quote_authentication_and_validation(self):
        self.assertEqual(self.submit(accept_review=False).status_code, 400)
        self.assertEqual(self.submit(consent_version='old').status_code, 400)
        self.assertEqual(self.submit(quote_version='tampered').status_code, 409)
        self.assertEqual(self.submit(postcode='abcd').status_code, 400)
        self.assertEqual(self.submit(address='tiny').status_code, 400)
        self.client.logout()
        self.assertEqual(self.submit().status_code, 401)
        self.assertFalse(Order.objects.exists())

    def test_idempotency_and_account_isolation(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.submit(address='20 Different Test Street').status_code, 409)
        self.assertEqual(Order.objects.count(), 1)
        result = self.client.get('/api/orders').json()['orders'][0]
        self.assertEqual(result['broadband']['monthly_cents'], 8341)
        self.assertNotIn('source_', json.dumps(result))
        self.client.force_login(get_user_model().objects.create_user('another-customer'))
        self.assertEqual(self.client.get('/api/orders').json()['orders'], [])

    def test_owner_prepares_draft_but_cannot_skip_confirmation(self):
        identifier = self.submit().json()['id']
        url = f'/api/owner/broadband-orders/{identifier}/prepare-offer'
        self.assertEqual(self.client.post(url, '{}', content_type='application/json').status_code, 403)
        response = self.operator.post(url, '{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.operator.post(url, '{}', content_type='application/json').status_code, 200)
        agreement = LiveAgreement.objects.get()
        self.assertFalse(agreement.reviewed)
        self.assertFalse(agreement.supplier_confirmed)
        self.assertIsNone(agreement.bill_from)
        self.assertEqual((agreement.monthly_cents, agreement.setup_cents), (8341, 1000))
        self.assertEqual(self.client.get('/api/payments/summary').json()['agreements'], [])
        agreement.reviewed = True
        agreement.supplier_confirmed = True
        agreement.bill_from = timezone.localdate()
        with self.assertRaises(ValidationError): agreement.full_clean()

    def test_cancelled_order_cannot_prepare_or_pay(self):
        identifier = self.submit().json()['id']
        url = f'/api/owner/broadband-orders/{identifier}/prepare-offer'
        self.operator.post(url, '{}', content_type='application/json')
        agreement = LiveAgreement.objects.get()
        agreement.service_terms = 'Confirmed synthetic terms, no real service.'
        agreement.reviewed = agreement.supplier_confirmed = True
        agreement.bill_from = timezone.localdate()
        agreement.approved_by = self.owner
        agreement.approved_at = timezone.now()
        agreement.save()
        self.assertEqual(self.client.post(f'/api/orders/{identifier}/cancel', '{}', content_type='application/json').status_code, 200)
        self.assertEqual(self.operator.post(url, '{}', content_type='application/json').status_code, 409)
        self.assertEqual(self.client.get('/api/payments/summary').json()['agreements'], [])
        with self.assertRaises(ValidationError): agreement.check_checkout_eligibility()

    def test_confirmed_order_checkout_preserves_inclusive_prices_and_single_setup(self):
        from payments.test_live_billing import ENV
        identifier=self.submit().json()['id']
        self.operator.post(f'/api/owner/broadband-orders/{identifier}/prepare-offer','{}',content_type='application/json')
        agreement=LiveAgreement.objects.get()
        url=f'/api/owner/operations/payment-agreements/{agreement.pk}'
        version=self.operator.get(url).json()['version']
        values=dict(user=self.user.pk,label=agreement.label,service_reference=agreement.service_reference,
            source_monthly_cents=6992,source_setup_cents=0,service_terms='Confirmed synthetic service terms for isolated testing.',
            bill_from=str(timezone.localdate()),supplier_confirmed=True,reviewed=True,confirm_live_offer=True)
        approval=self.operator.post(url,json.dumps({'version':version,'values':values}),content_type='application/json')
        self.assertEqual(approval.status_code,200,approval.content)
        agreement.refresh_from_db()
        api=MagicMock()
        api.v1.tax_rates.retrieve.return_value=dict(id='txr_synthetic',object='tax_rate',livemode=True,active=True,inclusive=True,percentage=15,country='NZ')
        api.v1.checkout.sessions.create.return_value=dict(id='cs_live_synthetic_broadband',object='checkout.session',livemode=True,
            mode='subscription',currency='nzd',amount_total=9341,client_reference_id=str(agreement.pk),
            metadata={'kiwikind_live_agreement':str(agreement.pk)},status='open',
            url='https://checkout.stripe.com/c/pay/cs_live_synthetic_broadband',subscription=None,customer=None)
        with patch.dict(os.environ,ENV),patch('payments.live_gateway.client',return_value=api):
            response=self.client.post('/api/payments/checkout',json.dumps(dict(agreement_id=str(agreement.pk),
                terms_version=str(agreement.terms_version),accept_live_recurring=True)),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        monthly,setup=api.v1.checkout.sessions.create.call_args.args[0]['line_items']
        self.assertEqual(monthly['price_data']['unit_amount'],8341)
        self.assertEqual(setup['price_data']['unit_amount'],1000)
        self.assertEqual(monthly['price_data']['recurring'],{'interval':'month'})
        self.assertNotIn('recurring',setup['price_data'])
        self.assertEqual(monthly['price_data']['tax_behavior'],'inclusive')
        self.assertFalse(WholesaleOrder.objects.exists())
        self.assertEqual(self.client.post(f'/api/orders/{identifier}/cancel','{}',content_type='application/json').status_code,409)
        order_url=f'/api/owner/operations/requests/{identifier}'
        version=self.operator.get(order_url).json()['version']
        self.assertEqual(self.operator.post(order_url,json.dumps({'version':version,'values':{'status':'cancelled'}}),content_type='application/json').status_code,409)

    def test_order_submission_requires_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/api/broadband/orders',json.dumps(self.data),content_type='application/json').status_code,403)
        self.assertFalse(Order.objects.exists())
