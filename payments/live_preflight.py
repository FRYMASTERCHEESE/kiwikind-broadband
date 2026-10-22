"""Read-only Stripe live-account capability checks.

This module only reads provider readiness; production checkout is implemented
separately in live_gateway/live_service/live_views. Sandbox records stay separate.
Never return provider IDs, secret values, Stripe error bodies or customer data.
"""
import os
import re

import stripe
from . import live_gateway
from django.contrib import admin
from django.http import HttpResponse, HttpResponseNotAllowed
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache

from portal.owner_admin import owner_session
from . import gateway


def settings_status():
    key = os.environ.get("STRIPE_LIVE_SECRET_KEY", "").strip()
    account = os.environ.get("STRIPE_LIVE_ACCOUNT_ID", "").strip()
    webhook = os.environ.get("STRIPE_LIVE_WEBHOOK_SECRET", "").strip()
    return {
        "live_api_key_present": bool(re.fullmatch(r"(?:sk|rk)_live_[A-Za-z0-9]+", key)),
        "live_account_id_present": bool(re.fullmatch(r"acct_[A-Za-z0-9]+", account)),
        "live_webhook_secret_present": bool(re.fullmatch(r"whsec_[A-Za-z0-9]+", webhook)),
        "production_billing_implemented": True,
        "live_checkout_enabled": live_gateway.configured(),
    }


def verify_account():
    """Stripe account and balance read only. No provider mutation under any condition."""
    config = settings_status()
    if not (config["live_api_key_present"] and config["live_account_id_present"]):
        return {"checked": False, "account_matches_live_mode": False,
                "charges_enabled": False, "payouts_enabled": False,
                "details_submitted": False, "result": "LIVE_KEY_OR_ACCOUNT_NOT_CONFIGURED"}

    try:
        client = stripe.StripeClient(
            os.environ["STRIPE_LIVE_SECRET_KEY"].strip(),
            stripe_version=gateway.API_VERSION,
            max_network_retries=0,
            http_client=stripe.RequestsClient(timeout=6),
        )
        account = gateway.plain(client.v1.accounts.retrieve_current())
        balance = gateway.plain(client.v1.balance.retrieve())
        if (not isinstance(account, dict) or not isinstance(balance, dict)
                or account.get("object") != "account"
                or account.get("id") != os.environ["STRIPE_LIVE_ACCOUNT_ID"].strip()
                or balance.get("object") != "balance"
                or balance.get("livemode") is not True):
            return {"checked": True, "account_matches_live_mode": False,
                    "charges_enabled": False, "payouts_enabled": False,
                    "details_submitted": False, "result": "ACCOUNT_OR_MODE_MISMATCH"}
        return {
            "checked": True,
            "account_matches_live_mode": True,
            "charges_enabled": account.get("charges_enabled") is True,
            "payouts_enabled": account.get("payouts_enabled") is True,
            "details_submitted": account.get("details_submitted") is True,
            "result": "LIVE_ACCOUNT_READ_ONLY_VERIFIED",
        }
    except Exception:
        # Provider exception messages can include request or configuration details.
        # Never return or log such exceptions, API key material or account IDs.
        return {"checked": True, "account_matches_live_mode": False,
                "charges_enabled": False, "payouts_enabled": False,
                "details_submitted": False, "result": "READ_ONLY_VERIFICATION_UNAVAILABLE"}


@never_cache
def owner_live_status(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return HttpResponse(status=404)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    config = settings_status()
    provider = verify_account() if request.GET.get("verify") == "1" else None
    return TemplateResponse(request, "admin/payments/live_preflight.html", {
        **admin.site.each_context(request),
        "title": "Stripe live account readiness — read only",
        "config": config,
        "provider": provider,
    })
