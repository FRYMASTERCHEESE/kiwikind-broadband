"""Stripe test-mode checkout staging. Never creates invoices or provisions broadband."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import Invoice

def configured():
    key = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
    return os.environ.get("STRIPE_TEST_CHECKOUT_ENABLED") == "1" and key.startswith("sk_test_") and bool(os.environ.get("STRIPE_TEST_PRICE_REVIEWED") == "1")

@login_required
@require_POST
def checkout(request):
    if not configured():
        return JsonResponse({"error": "Test checkout is disabled"}, status=503)
    try:
        data = json.loads(request.body)
        invoice = Invoice.objects.get(pk=data["invoice_id"], user=request.user, status="unpaid", currency="NZD")
    except (ValueError, KeyError, TypeError, Invoice.DoesNotExist):
        return JsonResponse({"error": "Unpaid invoice not found"}, status=404)
    if invoice.amount_cents < 50 or invoice.amount_cents > 1000000:
        return JsonResponse({"error": "Invoice amount requires staff review"}, status=400)
    origin = settings.PUBLIC_ORIGIN
    if not origin.startswith("https://") and not settings.DEBUG:
        return JsonResponse({"error": "HTTPS required"}, status=503)
    params = {
        "mode": "payment",
        "success_url": origin + "/?checkout=returned",
        "cancel_url": origin + "/?checkout=cancelled",
        "client_reference_id": str(invoice.id),
        "customer_email": request.user.email,
        "line_items[0][price_data][currency]": "nzd",
        "line_items[0][price_data][unit_amount]": str(invoice.amount_cents),
        "line_items[0][price_data][product_data][name]": "KiwiKind test invoice",
        "line_items[0][quantity]": "1",
        "metadata[invoice_id]": str(invoice.id),
    }
    req = Request("https://api.stripe.com/v1/checkout/sessions",
                  data=urlencode(params).encode(),
                  headers={"Authorization": "Bearer " + os.environ["STRIPE_TEST_SECRET_KEY"],
                           "Content-Type": "application/x-www-form-urlencoded",
                           "Idempotency-Key": "kiwikind-test-invoice-" + str(invoice.id)}, method="POST")
    try:
        with urlopen(req, timeout=10) as response:
            result = json.load(response)
        url = result.get("url", "")
        if not url.startswith("https://checkout.stripe.com/"):
            return JsonResponse({"error": "Invalid checkout destination"}, status=502)
        return JsonResponse({"url": url})
    except (HTTPError, URLError, TimeoutError, ValueError):
        return JsonResponse({"error": "Stripe test checkout unavailable"}, status=502)
