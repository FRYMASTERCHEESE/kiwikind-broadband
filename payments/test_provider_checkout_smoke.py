"""Synthetic tests of the provider-only, no-customer Checkout smoke."""
import os
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase


MODULE = "payments.management.commands.stripe_checkout_provider_smoke"


class ProviderCheckoutSmokeTests(SimpleTestCase):
    def run_smoke(self, client, flag="2026-10-21-v2", configured=True):
        out = StringIO()
        env = {"KIWIKIND_STRIPE_PROVIDER_SMOKE_RUN": flag}
        with patch.dict(os.environ, env), patch(MODULE + ".gateway.configured", return_value=configured), patch(
            MODULE + ".gateway.client", return_value=client
        ), patch(MODULE + ".gateway.origin", return_value="https://kiwikind-backend.onrender.com"), patch(
            MODULE + ".datetime"
        ) as clock:
            clock.now.return_value = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
            call_command("stripe_checkout_provider_smoke", stdout=out)
        return out.getvalue()

    def session(self):
        return {
            "id": "cs_test_synthetic_smoke",
            "object": "checkout.session",
            "livemode": False,
            "mode": "subscription",
            "currency": "nzd",
            "amount_total": 100,
            "subscription": None,
            "customer": None,
            "status": "open",
            "url": "https://checkout.stripe.com/c/pay/cs_test_synthetic_smoke",
        }

    def test_ignored_by_default(self):
        client = MagicMock()
        msg = self.run_smoke(client, flag="off")
        self.assertIn("SKIPPED", msg)
        client.v1.checkout.sessions.create.assert_not_called()
        client.v1.checkout.sessions.expire.assert_not_called()

    def test_creates_only_one_sandbox_checkout_and_expires_it(self):
        client = MagicMock()
        client.v1.checkout.sessions.create.return_value = self.session()
        client.v1.checkout.sessions.expire.return_value = {
            **self.session(), "status": "expired"
        }
        msg = self.run_smoke(client)
        self.assertIn("PASS", msg)
        args, kwargs = client.v1.checkout.sessions.create.call_args
        self.assertEqual(args[0]["line_items"][0]["price_data"]["unit_amount"], 100)
        self.assertEqual(args[0]["mode"], "subscription")
        self.assertEqual(args[0]["allowed_payment_method_types"], ["card"])
        self.assertNotIn("payment_method_types", args[0])
        self.assertIn("idempotency_key", kwargs["options"])
        client.v1.checkout.sessions.expire.assert_called_once_with(
            "cs_test_synthetic_smoke"
        )
        client.v1.customers.create.assert_not_called()
        client.v1.refunds.create.assert_not_called()
        self.assertNotIn("cs_test_", msg)

    def test_live_mode_or_bad_amount_never_passes(self):
        for change in ({"livemode": True}, {"amount_total": 10000}, {"customer": "cus_fake"}):
            with self.subTest(change=change):
                client = MagicMock()
                client.v1.checkout.sessions.create.return_value = {
                    **self.session(), **change
                }
                client.v1.checkout.sessions.expire.return_value = {
                    **self.session(), "status": "expired"
                }
                msg = self.run_smoke(client)
                self.assertIn("FAILED", msg)

    def test_transport_failure_never_claims_pass(self):
        client = MagicMock()
        client.v1.checkout.sessions.create.side_effect = ValueError("secret must not appear")
        msg = self.run_smoke(client)
        self.assertIn("FAILED", msg)
        self.assertNotIn("secret", msg)

    def test_missing_config_does_not_contact_stripe(self):
        client = MagicMock()
        msg = self.run_smoke(client, configured=False)
        self.assertIn("FAILED", msg)
        client.v1.checkout.sessions.create.assert_not_called()

    def test_expired_response_is_idempotently_accepted(self):
        client = MagicMock()
        client.v1.checkout.sessions.create.return_value = {
            **self.session(), "status": "expired"
        }
        msg = self.run_smoke(client)
        self.assertIn("PASS", msg)
        client.v1.checkout.sessions.expire.assert_not_called()

    def test_expiry_window_prevents_later_runs(self):
        out = StringIO()
        with patch.dict(os.environ, {"KIWIKIND_STRIPE_PROVIDER_SMOKE_RUN": "2026-10-21-v2"}), patch(
            MODULE + ".datetime"
        ) as clock, patch(MODULE + ".gateway.client") as client:
            clock.now.return_value = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)
            call_command("stripe_checkout_provider_smoke", stdout=out)
        self.assertIn("SKIPPED", out.getvalue())
        client.assert_not_called()
