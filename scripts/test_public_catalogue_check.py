"""Synthetic response checks: no network, accounts, supplier rates or payments."""
import copy
import unittest
from check_public_catalogue import validate_catalogues


def sample():
    quote = {'quote_complete': True, 'gst_included': True,
        'price_confirmation_required': True, 'catalogue_version': 'synthetic',
        'monthly_cents': 10000, 'setup_cents': 2000, 'first_invoice_cents': 12000}
    product = {'id': 'synthetic', 'name': 'Synthetic service',
        'price_status': 'verified', 'price_confirmation_required': True,
        'allowance': 'Synthetic allowance', 'terms': 'Synthetic terms', 'default_quote': quote}
    plan = {'id': 'synthetic', 'retail_monthly_cents': 10000,
        'retail_setup_cents': 2000, 'first_invoice_cents': 12000,
        'allowance': product['allowance'], 'terms': product['terms'],
        'address_availability': 'unverified'}
    return ({'products': [product], 'supplier_orders_enabled': False,
        'orders_enabled': True, 'gst_included': True, 'currency': 'NZD',
        'payment_timing': 'after_connection_confirmation', 'catalogue_version': 'synthetic'},
        {'plans': [plan], 'live_orders_enabled': False})


class PublicCatalogueChecks(unittest.TestCase):
    def test_published_and_deliberately_hidden_catalogues(self):
        a,b=sample()
        self.assertEqual(validate_catalogues(a,b),1)
        a['products']=[];a['orders_enabled']=False;b['plans']=[]
        self.assertEqual(validate_catalogues(a,b),0)

    def test_source_leak_anywhere_is_rejected(self):
        a,b=sample();a['products'][0]['default_quote']['source_ref']='synthetic-private'
        with self.assertRaises(AssertionError):validate_catalogues(a,b)

    def test_client_price_mismatch_and_invalid_total_are_rejected(self):
        a,b=sample();b['plans'][0]['retail_monthly_cents']+=1
        with self.assertRaises(AssertionError):validate_catalogues(a,b)
        a,b=sample();a['products'][0]['default_quote']['first_invoice_cents']+=1
        with self.assertRaises(AssertionError):validate_catalogues(a,b)

    def test_duplicate_services_are_rejected(self):
        a,b=sample();a['products'].append(copy.deepcopy(a['products'][0]));b['plans'].append(copy.deepcopy(b['plans'][0]))
        with self.assertRaises(AssertionError):validate_catalogues(a,b)

    def test_incomplete_or_unapproved_service_is_rejected(self):
        for key,value in [('allowance',''),('price_status','unverified')]:
            a,b=sample();a['products'][0][key]=value
            with self.assertRaises(AssertionError):validate_catalogues(a,b)
        a,b=sample();a['products'][0]['default_quote']['quote_complete']=False
        with self.assertRaises(AssertionError):validate_catalogues(a,b)

    def test_supplier_ordering_and_live_compatibility_orders_remain_disabled(self):
        a,b=sample();a['supplier_orders_enabled']=True
        with self.assertRaises(AssertionError):validate_catalogues(a,b)
        a,b=sample();b['live_orders_enabled']=True
        with self.assertRaises(AssertionError):validate_catalogues(a,b)


if __name__=='__main__':unittest.main()

