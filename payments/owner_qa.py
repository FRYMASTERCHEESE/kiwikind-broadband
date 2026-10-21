"""Owner-only, explicit, one-agreement billing QA preparation.

No customer accounts are created. No Stripe resources are created here.
Requires the existing owner Google proof, authenticator MFA, CSRF and an
explicit POST. The one $1/month record belongs only to the owner account.
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from portal.models import AuditEvent
from portal.owner_admin import owner_session
from . import gateway
from .models import TestAgreement


QA_LABEL = "OWNER QA TEST ONLY - NZ$1/month - NO broadband"


def private_context(request, agreement=None, error=""):
    return {
        **admin.site.each_context(request),
        "title": "KiwiKind private Stripe sandbox checkout test",
        "sandbox_ready": gateway.configured(),
        "agreement": agreement,
        "error": error,
        "qa_label": QA_LABEL,
    }


@never_cache
@csrf_protect
def owner_qa(request):
    # Return no information about accounts or Stripe to anonymous users.
    if not owner_session(request) or not admin.site.has_permission(request):
        return HttpResponse(status=404)
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    # No publicly saleable products exist in this flow, including once
    # wholesale plans start being prepared.
    if settings.INTAKE_ENABLED or settings.PLAN_PUBLICATION_ENABLED:
        return HttpResponse("Test preparation unavailable while customer sales are open.", status=503)

    existing = TestAgreement.objects.filter(
        user=request.user, label=QA_LABEL).order_by("created_at").first()

    if request.method == "POST":
        if request.POST.get("ack_sandbox_only") != "yes":
            return render(request, "admin/payments/sandbox_qa.html",
                          private_context(request, existing,
                                          "Confirm the NZ$1/month recurring TEST agreement first."),
                          status=400)
        if not gateway.configured():
            return render(request, "admin/payments/sandbox_qa.html",
                          private_context(request, existing, "Stripe TEST configuration is unavailable."),
                          status=503)

        # One per owner account, not one per HTTP request. Locking the owner
        # row serializes simultaneous requests even before any agreement exists.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            existing = TestAgreement.objects.filter(
                user=request.user, label=QA_LABEL).order_by("created_at").first()
            if existing is None:
                existing = TestAgreement(
                    user=request.user,
                    created_by=request.user,
                    label=QA_LABEL,
                    monthly_cents=100,
                    setup_cents=0,
                    reviewed=True,
                )
                existing.full_clean()
                existing.save()
                AuditEvent.objects.create(
                    actor=request.user,
                    action="sandbox_agreement_review",
                    reference=str(existing.pk),
                )
        return redirect("/billing/")

    return render(request, "admin/payments/sandbox_qa.html",
                  private_context(request, existing))
