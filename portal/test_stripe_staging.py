"""Safety tests for Stripe staging; no network calls or charges."""
import json
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from portal.models import Invoice

class StripeStagingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("stripe-test@example.invalid", password="Test-Only-Safe-Password-349!")
        self.other = get_user_model().objects.create_user("other-stripe@example.invalid", password="Test-Only-Safe-Password-349!")
        self.invoice = Invoice.objects.create(user=self.user, supplier_reference="synthetic-stripe-test", amount_cents=9900, currency="NZD", due_date="2026-12-01", status="unpaid")
        self.url = "/api/billing/stripe/test-checkout"
    def post(self, invoice_id):
        return self.client.post(self.url, json.dumps({"invoice_id": str(invoice_id)}), content_type="application/json")
    def test_requires_login(self):
        self.assertIn(self.post(self.invoice.id).status_code, [302, 401, 403])
    def test_disabled_by_default(self):
        self.client.force_login(self.user)
        self.assertEqual(self.post(self.invoice.id).status_code, 503)
        self.assertFalse(self.client.get("/api/invoices").json()["stripe_test_checkout_enabled"])
    @override_settings(DEBUG=True)
    def test_live_key_cannot_enable_staging(self):
        from unittest.mock import patch
        self.client.force_login(self.user)
        with patch.dict("os.environ", {"STRIPE_TEST_CHECKOUT_ENABLED":"1","STRIPE_TEST_PRICE_REVIEWED":"1","STRIPE_TEST_SECRET_KEY":"sk_live_do_not_use"}):
            self.assertEqual(self.post(self.invoice.id).status_code, 503)
    def test_existing_ledger_is_not_mutated(self):
        self.client.force_login(self.user)
        self.post(self.invoice.id)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "unpaid")
