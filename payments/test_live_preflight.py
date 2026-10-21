"""Only read-only live-account diagnostics, not the unfinished billing candidate."""
import os
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from portal.testing import owner_fixture
from . import live_preflight


TEST_ENV = {
    "STRIPE_LIVE_SECRET_KEY": "sk_live_syntheticNeverUse",
    "STRIPE_LIVE_ACCOUNT_ID": "acct_syntheticNeverUse",
    "STRIPE_LIVE_WEBHOOK_SECRET": "whsec_syntheticNeverUse",
}


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True)
class LiveAccountReadOnlyTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            "preflight-owner", "synthetic@example.invalid",
            is_staff=True, is_superuser=True
        )

    def test_rejects_test_keys_without_network_calls(self):
        with patch.dict(os.environ, {
            **TEST_ENV, "STRIPE_LIVE_SECRET_KEY": "sk_test_badmode"
        }), patch("payments.live_preflight.stripe.StripeClient") as factory:
            flags = live_preflight.settings_status()
            self.assertFalse(flags["live_api_key_present"])
            result = live_preflight.verify_account()
            self.assertFalse(result["checked"])
            factory.assert_not_called()

    def test_read_only_live_account_verification_and_capabilities(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"],
            "charges_enabled": True, "payouts_enabled": True,
            "details_submitted": True,
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": True
        }
        with patch.dict(os.environ, TEST_ENV), patch(
            "payments.live_preflight.stripe.StripeClient", return_value=client
        ) as factory:
            status = live_preflight.verify_account()
            self.assertTrue(status["checked"])
            self.assertTrue(status["account_matches_live_mode"])
            self.assertTrue(status["charges_enabled"])
            self.assertTrue(status["payouts_enabled"])
            self.assertFalse(live_preflight.settings_status()["live_checkout_enabled"])
            client.v1.checkout.sessions.create.assert_not_called()
            client.v1.refunds.create.assert_not_called()
            client.v1.subscriptions.create.assert_not_called()
            factory.assert_called_once()

    def test_wrong_account_or_test_balance_rejected(self):
        for account_id, mode in (("acct_other", True),
                                  (TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"], False)):
            with self.subTest(account_id=account_id, mode=mode):
                client = MagicMock()
                client.v1.accounts.retrieve_current.return_value = {
                    "object": "account", "id": account_id, "charges_enabled": True
                }
                client.v1.balance.retrieve.return_value = {
                    "object": "balance", "livemode": mode
                }
                with patch.dict(os.environ, TEST_ENV), patch(
                    "payments.live_preflight.stripe.StripeClient",
                    return_value=client
                ):
                    response = live_preflight.verify_account()
                self.assertEqual(response["result"], "ACCOUNT_OR_MODE_MISMATCH")
                self.assertFalse(response["account_matches_live_mode"])

    def test_live_account_with_disabled_charges_is_not_claimed_active(self):
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"],
            "charges_enabled": False, "payouts_enabled": False,
            "details_submitted": True,
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": True
        }
        with patch.dict(os.environ, TEST_ENV), patch(
            "payments.live_preflight.stripe.StripeClient", return_value=client
        ):
            status = live_preflight.verify_account()
        self.assertTrue(status["account_matches_live_mode"])
        self.assertFalse(status["charges_enabled"])
        self.assertFalse(status["payouts_enabled"])

    def test_sanitizes_stripe_exceptions(self):
        with patch.dict(os.environ, TEST_ENV), patch(
            "payments.live_preflight.stripe.StripeClient",
            side_effect=ValueError("SECRET_ACCOUNT_BILLING_DO_NOT_LEAK"),
        ):
            status = live_preflight.verify_account()
        self.assertEqual(status["result"], "READ_ONLY_VERIFICATION_UNAVAILABLE")
        self.assertNotIn("SECRET_ACCOUNT_BILLING_DO_NOT_LEAK", str(status))

    def test_private_admin_requires_verified_owner_google_and_mfa(self):
        path = "/admin/live-stripe-readiness/"
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(path).status_code, 404)
        owner_fixture(self.client, self.owner)
        with patch.dict(os.environ, TEST_ENV):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stripe live account readiness")
        self.assertContains(response, "Actual customer billing implementation")
        self.assertNotContains(response, TEST_ENV["STRIPE_LIVE_SECRET_KEY"])
        self.assertNotContains(response, TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"])
        self.assertNotContains(response, TEST_ENV["STRIPE_LIVE_WEBHOOK_SECRET"])
        self.assertEqual(self.client.post(path).status_code, 405)
        session = self.client.session
        session.pop("otp_device_id")
        session.save()
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_command_reports_status_not_keys_and_does_not_open_checkout(self):
        output = StringIO()
        client = MagicMock()
        client.v1.accounts.retrieve_current.return_value = {
            "object": "account", "id": TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"],
            "charges_enabled": True, "payouts_enabled": False
        }
        client.v1.balance.retrieve.return_value = {
            "object": "balance", "livemode": True
        }
        with patch.dict(os.environ, TEST_ENV), patch(
            "payments.live_preflight.stripe.StripeClient", return_value=client
        ):
            call_command("check_live_stripe_account", "--verify-provider",
                         stdout=output)
        report = output.getvalue()
        self.assertIn("Stripe live identity: LIVE_ACCOUNT_READ_ONLY_VERIFIED", report)
        self.assertIn("Stripe live charges_enabled: yes", report)
        self.assertIn("Stripe live payouts_enabled: no", report)
        self.assertIn("Stripe live checkout: DISABLED", report)
        self.assertNotIn(TEST_ENV["STRIPE_LIVE_SECRET_KEY"], report)
        self.assertNotIn(TEST_ENV["STRIPE_LIVE_ACCOUNT_ID"], report)
        self.assertNotIn(TEST_ENV["STRIPE_LIVE_WEBHOOK_SECRET"], report)
        client.v1.checkout.sessions.create.assert_not_called()
        client.v1.refunds.create.assert_not_called()
