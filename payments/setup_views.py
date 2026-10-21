"""Owner-only checklist. Secrets stay in Render, not forms, browser JSON or logs."""
from django.contrib import admin
from django.http import HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.cache import never_cache
import stripe
from portal.owner_admin import owner_session
from . import gateway, live_gateway


@never_cache
def setup(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return HttpResponseNotFound()
    if request.method not in ('GET', 'POST'):
        return HttpResponseNotFound()
    check = None
    if request.method == 'POST':
        # Read-only provider verification, never a charge or secret-setting action.
        try:
            live_gateway.client()
            check = 'Live account identity and mode verified with read-only requests. No payment was made. This does not replace checkout/webhook testing.'
        except (live_gateway.BillingUnavailable, stripe.StripeError, ValueError, KeyError):
            check = 'Live account verification is not complete. Check the private environment settings below. No payment was made; provider error details and keys are not displayed.'
    return render(request, 'admin/payments/stripe_setup.html', {
        **admin.site.each_context(request), 'title': 'Stripe setup and payment readiness',
        'sandbox': gateway.configuration(), 'production': live_gateway.configuration(),
        'api_version': gateway.API_VERSION, 'check_result': check,
    })
