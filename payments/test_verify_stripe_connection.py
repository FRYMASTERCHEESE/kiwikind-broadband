"""Tests for a read-only Stripe verification independent of checkout release."""
import os
from io import StringIO
from unittest.mock import MagicMock, patch
from django.core.management import call_command
from django.test import SimpleTestCase


class StripeSandboxIdentityTests(SimpleTestCase):
    env = {
        "STRIPE_TEST_SECRET_KEY": "sk_test_syntheticNeverUse",
        "STRIPE_TEST_ACCOUNT_ID": "acct_syntheticNeverUse",
        "STRIPE_TEST_WEBHOOK_SECRET": "whsec_syntheticNeverUse",
        "KIWIKIND_STRIPE_SANDBOX": "0",
    }

    def verify(self, client):
        output = StringIO()
        with patch.dict(os.environ, self.env), patch(
            "payments.management.commands.verify_stripe_test_connection.stripe.StripeClient",
            return_value=client,
        ) as factory:
            call_command("verify_stripe_test_connection", stdout=output)
            self.assertEqual(os.environ["KIWIKIND_STRIPE_SANDBOX"], "0")
            return output.getvalue(), factory

    def test_valid_account_and_test_balance_pass_without_writes(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": self.env["STRIPE_TEST_ACCOUNT_ID"]
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": False
        }
        message, factory = self.verify(client)
        self.assertIn("PASS", message)
        self.assertNotIn(self.env["STRIPE_TEST_SECRET_KEY"], message)
        self.assertNotIn(self.env["STRIPE_TEST_ACCOUNT_ID"], message)
        client.v1.checkout.sessions.create.assert_not_called()
        client.v1.refunds.create.assert_not_called()
        factory.assert_called_once()

    def test_wrong_account_fails_closed(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": "acct_other"
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": False
        }
        message, _ = self.verify(client)
        self.assertIn("FAILED", message)
        self.assertNotIn("acct_other", message)

    def test_live_balance_rejected(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": self.env["STRIPE_TEST_ACCOUNT_ID"]
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": True
        }
        message, _ = self.verify(client)
        self.assertIn("FAILED", message)

    def test_transport_error_sanitized(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.side_effect = ValueError("sensitive test token")
        message, _ = self.verify(client)
        self.assertIn("FAILED", message)
        self.assertNotIn("sensitive", message)

    def test_missing_secret_skips_without_api_call(self):
        output = StringIO()
        missing = dict(self.env, STRIPE_TEST_WEBHOOK_SECRET="")
        with patch.dict(os.environ, missing), patch(
            "payments.management.commands.verify_stripe_test_connection.stripe.StripeClient"
        ) as factory:
            call_command("verify_stripe_test_connection", stdout=output)
            factory.assert_not_called()
        self.assertIn("WAITING", output.getvalue())
