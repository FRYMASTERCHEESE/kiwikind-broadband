import json
import os
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .broadband import quote, ORDER_CONSENT, catalogue_source
from .models import Order, BroadbandOrder, WholesaleOrder, VerifiedSupplierOption
from .testing import owner_fixture
from decimal import Decimal
from payments.live_models import LiveAgreement
from payments.retail_pricing import order_quote


@override_settings(BROADBAND_CATALOGUE_ENABLED=True, PLAN_PUBLICATION_ENABLED=True,PUBLIC_ORIGIN='https://kiwikind.example.invalid')
class BroadbandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('broadband-customer', 'buyer@example.invalid')
        self.client.force_login(self.user)
        self.owner = get_user_model().objects.create_superuser('operator', 'operator@example.invalid', 'Synthetic-password-only')
        self.operator = Client()
        owner_fixture(self.operator, self.owner)
        from .models import PrivateCatalogueRelease
        from .private_catalogue import validate_payload, digest
        from .test_private_catalogue import sample
        payload = sample()
        payload[0].update(id='ufb', name='Synthetic regression fibre', base='0.00', baseSetup='0.00')
        payload[0]['groups'] = [
            {'id': 'speed', 'label': 'Speed', 'options': [
                {'id': '3', 'name': 'Synthetic speed', 'monthly': '69.92', 'setup': '0.00', 'unknown': False, 'usage': None}]},
            {'id': 'install', 'label': 'Installation', 'options': [
                {'id': key, 'name': key, 'monthly': '0.00', 'setup': amount, 'unknown': False, 'usage': None}
                for key, amount in [('existing-ont', '0.00'), ('churn', '20.00'), ('additional-ont', '300.00')]]}]
        payload = validate_payload(payload)
        self.release = PrivateCatalogueRelease.objects.create(payload=payload, active=True,
            verified_on=timezone.localdate(), valid_until=timezone.localdate(),
            approved_by=self.owner, approved_at=timezone.now(), approved_digest=digest(payload))
        self.selection = quote('ufb', ['3', 'existing-ont'])
        self.data = dict(product_id='ufb', selections=['3', 'existing-ont'], quote_version=self.selection['quote_version'],
            address='10 Synthetic Test Street', postcode='1010', contact_name='Synthetic Customer', phone='',
            idempotency_key=str(uuid.uuid4()), consent_version=ORDER_CONSENT, accept_review=True)

    def submit(self, **changes):
        return self.client.post('/api/broadband/orders', json.dumps({**self.data, **changes}), content_type='application/json')

    def test_private_release_and_inclusive_additions(self):
        response = self.client.get('/api/broadband/catalogue').json()
        self.assertEqual(len(response['products']), 1)
        self.assertFalse(response['supplier_orders_enabled'])
        self.assertEqual(response['payment_timing'], 'after_connection_confirmation')
        self.assertNotIn('source_monthly_cents', json.dumps(response))
        self.assertEqual(self.selection['monthly_cents'], 8341)
        self.assertEqual(self.selection['setup_cents'], 1000)
        self.assertEqual(self.selection['first_invoice_cents'], 9341)

    def test_unknown_installation_is_not_a_free_selection(self):
        with self.assertRaises(ValueError): quote('ufb', ['3', 'unknown'])
        churn = quote('ufb', ['3', 'churn'])
        self.assertEqual(churn['setup_cents'], 3300)
        self.assertEqual(churn['first_invoice_cents'], churn['monthly_cents']+3300)

    def test_removed_release_is_hidden_without_fallback(self):
        from .models import PrivateCatalogueRelease
        PrivateCatalogueRelease.objects.filter(pk=self.release.pk).update(active=False)
        with self.assertRaises(ValueError): quote('ufb', ['3', 'existing-ont'])
        self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])

    def test_rate_changes_invalidate_order_and_old_offer_draft(self):
        from .models import PrivateCatalogueRelease
        from .private_catalogue import digest, validate_payload
        self.assertEqual(self.submit().status_code, 201)
        pk = str(BroadbandOrder.objects.get().order_id)
        payload = self.release.payload
        payload[0]['groups'][0]['options'][0]['monthly'] = '70.92'
        payload = validate_payload(payload)
        PrivateCatalogueRelease.objects.filter(pk=self.release.pk).update(active=False)
        PrivateCatalogueRelease.objects.create(payload=payload, active=True,
            verified_on=timezone.localdate(), valid_until=timezone.localdate(),
            approved_by=self.owner, approved_at=timezone.now(), approved_digest=digest(payload))
        self.assertEqual(self.submit(idempotency_key=str(uuid.uuid4())).status_code, 409)
        result = self.operator.post(f'/api/owner/broadband-orders/{pk}/prepare-offer', '{}', content_type='application/json')
        self.assertEqual(result.status_code, 409)
        self.assertFalse(LiveAgreement.objects.exists())

    def test_quote_invalid_options_and_closed_gate(self):
        for selection in ([], ['99'], ['3'], ['3','99'], [True], [3], {}, None):
            with self.assertRaises(ValueError): quote('ufb', selection)
        self.assertEqual(self.client.get('/api/broadband/quote?product=ufb&options=3,existing-ont').json()['monthly_cents'], 8341)
        with override_settings(BROADBAND_CATALOGUE_ENABLED=False):
            self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])
            self.assertEqual(self.submit().status_code, 503)
            self.assertEqual(self.client.get('/api/broadband/quote?product=ufb&options=3,existing-ont').status_code, 503)

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

    def test_all_in_new_quote_and_legacy_agreement_versioning(self):
        baseline = quote('ufb', ['3', 'churn'])
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            revised = quote('ufb', ['3', 'churn'])
            self.assertGreater(revised['monthly_cents'], baseline['monthly_cents'])
            response = self.client.get('/api/broadband/quote?product=ufb&options=3,churn')
            self.assertEqual(response.json()['monthly_cents'], revised['monthly_cents'])
            agreement = LiveAgreement.objects.create(
                user=self.user, created_by=self.owner, label='Synthetic full price',
                service_reference='synthetic-all-in', source_monthly_cents=6992,
                source_setup_cents=2000, service_terms='Synthetic terms')
            self.assertEqual(agreement.pricing_policy, 'all_in_v3')
            self.assertEqual(agreement.monthly_cents, revised['monthly_cents'])
            self.assertEqual(agreement.setup_cents, revised['setup_cents'])

    def test_monthly_price_rise_is_exactly_four_dollars_with_same_setup(self):
        original = quote('ufb', ['3', 'churn'])
        self.assertEqual((original['monthly_cents'], original['setup_cents']),
                         (8341, 3300))
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            before = order_quote(original['source_monthly_cents'],
                                 original['source_setup_cents'], include_processing=True)
            after = quote('ufb', ['3', 'churn'])
            self.assertEqual(after['monthly_cents'], before['monthly_cents'] + 400)
            self.assertEqual(after['setup_cents'], before['setup_cents'])
            self.assertEqual(after['first_invoice_cents'],
                             before['first_invoice_cents'] + 400)
            listing = self.client.get('/api/broadband/catalogue').json()
            fibre = next(p for p in listing['products'] if p['id'] == 'ufb')
            from .broadband import effective_catalogue, cents
            entry = next(p for p in effective_catalogue()[0] if p['id'] == 'ufb')
            self.assertEqual(fibre['headline_monthly_cents'],
                             order_quote(cents(entry['headline']), 0, include_processing=True)['monthly_cents'] + 400)
            self.assertNotIn('monthly_addition_cents', listing)
            self.assertNotIn('setup_addition_cents', __import__('portal.broadband', fromlist=['public_quote']).public_quote(after))

    def test_all_seven_catalogue_types_get_monthly_increase(self):
        products, _ = catalogue_source()
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            for p in products:
                if p['id'] == 'ufb':
                    selections = ['3', 'churn']
                else:
                    selections = [g['options'][0]['id'] for g in p['groups']]
                result = quote(p['id'], selections)
                supplier_monthly = result['source_monthly_cents']
                supplier_setup = result['source_setup_cents']
                original = order_quote(supplier_monthly, supplier_setup,
                                       include_processing=True)
                self.assertEqual(result['monthly_cents'],
                                 original['monthly_cents'] + 400, p['id'])
                self.assertEqual(result['setup_cents'],
                                 original['setup_cents'], p['id'])

    def test_prior_agreement_amounts_are_not_recalculated(self):
        agreement = LiveAgreement.objects.create(
            user=self.user, created_by=self.owner, label='Original quote',
            service_reference='synthetic-legacy', source_monthly_cents=6992,
            source_setup_cents=2000, service_terms='Historical synthetic terms')
        self.assertEqual(agreement.pricing_policy, 'legacy_v1')
        original = (agreement.monthly_cents, agreement.setup_cents)
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            agreement.save()
            agreement.refresh_from_db()
            self.assertEqual((agreement.monthly_cents, agreement.setup_cents), original)
            self.assertEqual(agreement.pricing_policy, 'legacy_v1')

    def test_existing_all_in_v2_agreements_keep_old_prices(self):
        old = LiveAgreement.objects.create(
            user=self.user, created_by=self.owner, label='Previous all-in rate',
            service_reference='synthetic-old-all-in', pricing_policy='all_in_v2',
            source_monthly_cents=6992, source_setup_cents=3500,
            service_terms='Historical synthetic customer terms')
        original = (old.monthly_cents, old.setup_cents)
        self.assertEqual(original, (8662, 5200))
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            old.save()
            old.refresh_from_db()
        self.assertEqual((old.monthly_cents, old.setup_cents), original)
        self.assertEqual(old.pricing_policy, 'all_in_v2')

    def test_order_submission_requires_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/api/broadband/orders',json.dumps(self.data),content_type='application/json').status_code,403)
        self.assertFalse(Order.objects.exists())
