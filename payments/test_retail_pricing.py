from unittest import TestCase
from .retail_pricing import order_quote


class RetailPricingTests(TestCase):
    def test_additions_are_inclusive_not_taxed_again(self):
        quote = order_quote(10000, 2000)
        self.assertEqual(quote['monthly_cents'], 11800)
        self.assertEqual(quote['setup_cents'], 3300)
        self.assertEqual(quote['first_invoice_cents'], 15100)

    def test_zero_supplier_setup_still_has_one_setup_addition(self):
        self.assertEqual(order_quote(0, 0)['setup_cents'], 1000)

    def test_missing_installation_price_prevents_payable_total(self):
        quote = order_quote(10000, None)
        self.assertFalse(quote['quote_complete'])
        self.assertIsNone(quote['first_invoice_cents'])

    def test_invalid_or_browser_style_amounts_are_rejected(self):
        for value in (-1, True, 1.5, '100', 1000001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                order_quote(value, 0)
            with self.subTest(setup=value), self.assertRaises(ValueError):
                order_quote(0, value)

    def test_first_invoice_matches_displayed_lines_at_rounding_boundary(self):
        quote = order_quote(3, 3)
        self.assertEqual(quote['monthly_cents'], 303)
        self.assertEqual(quote['setup_cents'], 1003)
        self.assertEqual(quote['first_invoice_cents'], 1306)

    def test_setup_never_recurs_in_monthly_amount(self):
        self.assertEqual(order_quote(10000, 2000)['monthly_cents'],
                         order_quote(10000, 4000)['monthly_cents'])

    def test_full_upfront_gst_price_budgets_collection_costs(self):
        from .all_in_prices import estimated_fees, all_in_amount
        old = order_quote(6992, 3500)
        final = order_quote(6992, 3500, include_processing=True)
        self.assertEqual((old['monthly_cents'], old['setup_cents']), (8341, 5025))
        self.assertEqual((final['monthly_cents'], final['setup_cents'],
                          final['first_invoice_cents']), (8662, 5200, 13862))
        self.assertEqual(final['monthly_cents'] - estimated_fees(final['monthly_cents']),
                         old['monthly_cents'])
        self.assertEqual(final['first_invoice_cents'] -
                         estimated_fees(final['first_invoice_cents']),
                         old['first_invoice_cents'])
        self.assertEqual(all_in_amount(old['monthly_cents']), final['monthly_cents'])
        self.assertEqual(final['monthly_addition_cents'], 300)
        self.assertEqual(final['setup_addition_cents'], 1000)

    def test_all_in_unknown_setup_stays_unpayable_and_setup_is_not_recurring(self):
        incomplete = order_quote(6992, None, include_processing=True)
        self.assertEqual(incomplete['monthly_cents'], 8662)
        self.assertIsNone(incomplete['setup_cents'])
        self.assertIsNone(incomplete['first_invoice_cents'])
        self.assertFalse(incomplete['quote_complete'])
        for cents in (0, 500, 2500, 10000, 100000):
            complete = order_quote(cents, 0, include_processing=True)
            changed = order_quote(cents, 3500, include_processing=True)
            self.assertEqual(complete['monthly_cents'], changed['monthly_cents'])
            self.assertGreater(changed['setup_cents'], complete['setup_cents'])
        with self.assertRaises(ValueError):
            order_quote(1000, 0, include_processing='yes')
