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
