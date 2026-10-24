from django.test import TestCase, override_settings
from payments.retail_pricing import order_quote
from payments.live_models import LiveAgreement, default_price_policy
from . import test_private_catalogue as private_catalogue_tests


@override_settings(KIWIKIND_VETTA_SOURCE_PRICES_ONLY=True,
    KIWIKIND_ALL_IN_RETAIL_ENABLED=True, BROADBAND_CATALOGUE_ENABLED=True,
    PLAN_PUBLICATION_ENABLED=True)
class VettaSourcePriceTests(TestCase):
    def test_web_android_and_owner_preview_use_source_amounts_only(self):
        release = private_catalogue_tests.PrivateCatalogueTests.publish(self)
        web = self.client.get('/api/broadband/catalogue').json()['products'][0]
        app = self.client.get('/api/plans').json()['plans'][0]
        owner = self.client.get(f'/api/owner/catalogue-releases/{release.pk}').json()['products'][0]
        for value in (web['default_quote'], owner['retail_preview']):
            self.assertEqual((value['monthly_cents'], value['setup_cents'], value['first_invoice_cents']),
                (4830, 1380, 6210))
        self.assertEqual(web['headline_monthly_cents'], 4830)
        self.assertEqual((app['retail_monthly_cents'], app['retail_setup_cents']), (4830, 1380))
        self.assertNotIn('source_ref', str(web))

    def test_no_added_fees_and_unknown_setup_stays_unknown(self):
        value = order_quote(4201, None, source_prices_only=True,
            include_processing=True, monthly_price_increase_cents=400)
        self.assertEqual(value['monthly_cents'], 4831)
        self.assertIsNone(value['setup_cents'])
        self.assertIsNone(value['first_invoice_cents'])
        self.assertEqual(value['monthly_addition_cents'], 0)
        self.assertEqual(order_quote(4201, 1703, source_prices_only=True)['setup_cents'], 1958)

    def test_new_agreements_use_source_policy_and_historical_policy_is_unchanged(self):
        self.assertEqual(default_price_policy(), 'vetta_source_v1')
        new = LiveAgreement(source_monthly_cents=4200, source_setup_cents=1200)
        new.calculate_quote()
        self.assertEqual((new.monthly_cents, new.setup_cents), (4830, 1380))
        old = LiveAgreement(source_monthly_cents=4200, source_setup_cents=1200,
            pricing_policy='all_in_v3')
        old.calculate_quote()
        expected = order_quote(4200, 1200, include_processing=True, monthly_price_increase_cents=400)
        self.assertEqual((old.monthly_cents, old.setup_cents),
            (expected['monthly_cents'], expected['setup_cents']))
