"""Public retail projection; private wholesale data never leaves the owner admin."""
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import DraftPlan
from .owner_admin import OWNER_EMAIL, OWNER_USERNAME
from .wholesale import price_breakdown


@require_GET
def plans(request):
    items = []
    if settings.PLAN_PUBLICATION_ENABLED:
        candidates = DraftPlan.objects.filter(
            review_status='approved', address_specific=False, approved_at__isnull=False,
            valid_until__gte=timezone.localdate(), approved_by__username=OWNER_USERNAME,
            approved_by__email=OWNER_EMAIL, approved_by__is_active=True,
            approved_by__is_staff=True, approved_by__is_superuser=True,
            approved_by__owneridentity__verified_email=OWNER_EMAIL)
        for plan in candidates:
            # Fail closed even when a record was altered outside admin validation.
            try:
                plan.full_clean()
            except (ValidationError, ValueError, TypeError):
                continue
            items.append({
                'id': plan.pk, 'name': plan.name, 'network': plan.network,
                'download_mbps': plan.download_mbps, 'upload_mbps': plan.upload_mbps,
                'retail_monthly_cents': int(Decimal(price_breakdown(plan.retail_ex_gst)['inc_gst']) * 100),
                'retail_setup_cents': int(Decimal(price_breakdown(plan.retail_setup_ex_gst)['inc_gst']) * 100),
                'currency': 'NZD', 'gst_included': True, 'valid_until': plan.valid_until.isoformat(),
                'address_availability': 'unverified',
            })
    response = JsonResponse({'plans': items, 'live_orders_enabled': False})
    response['Cache-Control'] = 'no-store'
    response['Access-Control-Allow-Origin'] = '*'
    return response
