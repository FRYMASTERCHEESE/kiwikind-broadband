"""One-time sandbox-only Stripe Checkout API smoke test.

Never uses or modifies customer accounts, app database, live keys or billing.
Creates and expires an unpayable Stripe TEST Checkout Session.
"""
import os
from datetime import datetime, timezone, timedelta

from django.core.management.base import BaseCommand

from payments import gateway

FLAG = "KIWIKIND_STRIPE_PROVIDER_SMOKE_RUN"
RUN = "2026-10-21-v1"
EXPIRES = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
IDEMPOTENCY = "kiwikind-provider-checkout-smoke-20261021-v1"


class Command(BaseCommand):
    help = "Create/expire one $1 TEST Checkout Session; no card entry, customer, invoice or payment."

    def handle(self, *args, **options):
        if os.environ.get(FLAG) != RUN:
            self.stdout.write("Stripe provider Checkout: SKIPPED (one-shot switch off).")
            return

        # A time limit protects against accidental reruns after Stripe's 24-hour
        # idempotency window. The operator must disable the switch after the run.
        if datetime.now(timezone.utc) >= EXPIRES - timedelta(minutes=35):
            self.stdout.write("Stripe provider Checkout: SKIPPED (test window expired).")
            return

        if not gateway.configured():
            self.stdout.write("Stripe provider Checkout: FAILED (test-only configuration unavailable).")
            return

        session_id = None
        cleanup_ok = False
        verified = False
        phase = "identity"
        try:
            api = gateway.client()  # verifies pinned Stripe account AND test mode.
            params = {
                "mode": "subscription",
                "payment_method_types": ["card"],
                "line_items": [{
                    "price_data": {
                        "currency": "nzd",
                        "unit_amount": 100,
                        "recurring": {"interval": "month"},
                        "product_data": {"name": "KiwiKind SANDBOX API QA - no service"},
                    },
                    "quantity": 1,
                }],
                # Only a synthetic test marker. No real user email or supplier data.
                "metadata": {"kiwikind_qa": "provider_api_smoke_no_customer"},
                "success_url": gateway.origin() + "/billing/?qa_only=1",
                "cancel_url": gateway.origin() + "/billing/?qa_cancel=1",
                "expires_at": int(EXPIRES.timestamp()),
            }
            phase = "session_create"
            obj = gateway.plain(api.v1.checkout.sessions.create(
                params, options={"idempotency_key": IDEMPOTENCY}
            ))
            phase = "session_validate"
            # Determine an expiry target only from a valid Stripe test identifier.
            if isinstance(obj, dict) and str(obj.get("id", "")).startswith("cs_test_"):
                session_id = obj["id"]

            valid_common = (
                isinstance(obj, dict)
                and obj.get("object") == "checkout.session"
                and obj.get("livemode") is False
                and obj.get("mode") == "subscription"
                and obj.get("currency") == "nzd"
                and obj.get("amount_total") == 100
                and obj.get("subscription") is None
                and obj.get("customer") is None
                and obj.get("status") in ("open", "expired")
            )
            if not valid_common or (obj["status"] == "open" and not gateway.safe_checkout(obj.get("url"))):
                raise ValueError("Unexpected sandbox Checkout response")

            if obj["status"] == "open":
                phase = "session_expire"
                expired = gateway.test_object(
                    api.v1.checkout.sessions.expire(session_id),
                    "checkout.session", session_id
                )
                if expired.get("status") != "expired":
                    raise ValueError("Test session did not expire")
            cleanup_ok = True
            verified = True
        except Exception as exc:
            # Fixed categories only. Never emit Stripe exception messages, request
            # identifiers, API key fragments, account details or object IDs.
            categories = {
                "PermissionError": "permissions",
                "AuthenticationError": "authentication",
                "InvalidRequestError": "invalid_request",
                "IdempotencyError": "idempotency",
                "RateLimitError": "rate_limit",
                "APIConnectionError": "connection",
                "APIError": "provider_error",
                "BillingUnavailable": "configuration",
                "ReconciliationError": "verification",
                "ValueError": "unexpected_response",
                "AttributeError": "sdk_usage",
                "TypeError": "sdk_usage",
            }
            category = categories.get(type(exc).__name__, "unexpected_failure")
            safe_params = {"expires_at", "success_url", "cancel_url",
                           "payment_method_types", "line_items", "mode", "currency"}
            param = getattr(exc, "param", None)
            detail = (" field=" + param) if param in safe_params else ""
            self.stdout.write(
                f"Stripe provider Checkout: FAILED at {phase} ({category}{detail})."
            )
        finally:
            if session_id and not cleanup_ok:
                try:
                    # Fails safely if the session was already expired.
                    api.v1.checkout.sessions.expire(session_id)
                    cleanup_ok = True
                except Exception:
                    pass
            if verified and cleanup_ok:
                self.stdout.write(
                    "Stripe provider Checkout: PASS (Stripe TEST recurring Checkout "
                    "created and expired; no customer payment, app database write or service order)."
                )
            elif session_id:
                self.stdout.write(
                    "Stripe provider Checkout: ATTENTION (test-only session status needs manual review)."
                )
