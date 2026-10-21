"""Isolated tests for the explicit owner-only Stripe TEST setup path."""
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from portal.models import AuditEvent
from portal.testing import owner_fixture
from .models import TestAgreement
from .owner_qa import QA_LABEL


SANDBOX_ENV = {
    "KIWIKIND_STRIPE_SANDBOX": "1",
    "STRIPE_TEST_SECRET_KEY": "sk_test_notreal",
    "STRIPE_TEST_WEBHOOK_SECRET": "whsec_notreal",
    "STRIPE_TEST_ACCOUNT_ID": "acct_notreal",
}


@override_settings(
    ADMIN_ENABLED=True,
    OWNER_GOOGLE_ADMIN_ENABLED=True,
    PUBLIC_ORIGIN="https://kiwikind.example.invalid",
    INTAKE_ENABLED=False,
    PLAN_PUBLICATION_ENABLED=False,
)
class OwnerQATests(TestCase):
    def setUp(self):
        override = patch.dict(os.environ, SANDBOX_ENV)
        override.start()
        self.addCleanup(override.stop)
        self.owner = get_user_model().objects.create_user(
            username="test-operator", email="test-operator@example.invalid",
            is_staff=True, is_superuser=True
        )

    def owner_login(self):
        owner_fixture(self.client, self.owner)

    def test_anonymous_and_customer_access_get_404_without_records(self):
        self.assertEqual(self.client.get("/admin/billing-qa/").status_code, 404)
        self.assertEqual(self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"}).status_code, 404)
        customer = get_user_model().objects.create_user(
            "ordinary", "ordinary@example.invalid"
        )
        self.client.force_login(customer)
        self.assertEqual(self.client.get("/admin/billing-qa/").status_code, 404)
        self.assertEqual(self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"}).status_code, 404)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_staff_without_owner_identity_or_mfa_cannot_prepare(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/admin/billing-qa/").status_code, 404)
        self.assertEqual(self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"}).status_code, 404)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_owner_get_is_read_only_and_never_returns_credentials(self):
        self.owner_login()
        response = self.client.get("/admin/billing-qa/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NZ$1/month")
        for secret in (
            SANDBOX_ENV["STRIPE_TEST_SECRET_KEY"],
            SANDBOX_ENV["STRIPE_TEST_WEBHOOK_SECRET"],
        ):
            self.assertNotContains(response, secret)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_explicit_consent_creates_exactly_one_owner_only_agreement(self):
        self.owner_login()
        resp = self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/billing/")
        agreement = TestAgreement.objects.get()
        self.assertEqual(agreement.user_id, self.owner.pk)
        self.assertEqual(agreement.created_by_id, self.owner.pk)
        self.assertEqual(agreement.label, QA_LABEL)
        self.assertEqual(agreement.monthly_cents, 100)
        self.assertEqual(agreement.setup_cents, 0)
        self.assertTrue(agreement.reviewed)
        self.assertEqual(agreement.status, "pending")
        self.assertIsNone(agreement.checkout_id)
        self.assertIsNone(agreement.checkout_started_at)
        self.assertEqual(AuditEvent.objects.filter(
            action="sandbox_agreement_review",
            reference=str(agreement.pk),
        ).count(), 1)
        response = self.client.get("/api/billing/summary")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["live_payments_enabled"])
        self.assertTrue(response.json()["test_enabled"])
        self.assertEqual(len(response.json()["agreements"]), 1)
        self.assertEqual(self.client.get("/api/plans").json()["plans"], [])

        # Refreshes and repeated clicks cannot create another subscription.
        second = self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"})
        self.assertEqual(second.status_code, 302)
        self.assertEqual(TestAgreement.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(
            action="sandbox_agreement_review",
            reference=str(agreement.pk),
        ).count(), 1)

    def test_no_consent_rejected_without_writes(self):
        self.owner_login()
        response = self.client.post("/admin/billing-qa/", {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_test_switch_off_rejected_without_writes(self):
        self.owner_login()
        with patch.dict(os.environ, KIWIKIND_STRIPE_SANDBOX="0"):
            response = self.client.post("/admin/billing-qa/", {
                "ack_sandbox_only": "yes"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_publication_or_intake_open_rejects_preparation(self):
        self.owner_login()
        for key in ("INTAKE_ENABLED", "PLAN_PUBLICATION_ENABLED"):
            with self.subTest(key=key), override_settings(**{key: True}):
                self.assertEqual(self.client.post("/admin/billing-qa/", {
                    "ack_sandbox_only": "yes"}).status_code, 503)
        self.assertEqual(TestAgreement.objects.count(), 0)

    def test_csrf_must_be_valid_even_after_owner_mfa(self):
        session_client = Client(enforce_csrf_checks=True)
        owner_fixture(session_client, self.owner)
        response = session_client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TestAgreement.objects.exists())

    def test_owner_mfa_expiry_cannot_prepare(self):
        self.owner_login()
        session = self.client.session
        session.pop("otp_device_id", None)
        session.save()
        self.assertEqual(self.client.post("/admin/billing-qa/", {
            "ack_sandbox_only": "yes"}).status_code, 404)
        self.assertFalse(TestAgreement.objects.exists())
