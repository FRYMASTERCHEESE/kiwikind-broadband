from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import PricePlan

@require_GET
def plans(request):
    # Explicit projection: wholesale data, source and supplier references never leave admin.
    rows = PricePlan.objects.filter(status='approved', address_specific=False,
        valid_until__gte=timezone.localdate(), approved_by_id=settings.OWNER_USER_ID or None,
        approved_at__isnull=False, retail_monthly_cents__gt=0,
        retail_setup_cents__isnull=False)
    if not settings.PLAN_PUBLICATION_ENABLED or not settings.OWNER_USER_ID:
        rows = rows.none()
    response = JsonResponse({'availability':'unverified','plans':list(rows.values(
        'id','name','network','download_mbps','upload_mbps','retail_monthly_cents',
        'retail_setup_cents','valid_until','updated_at'))})
    response['Access-Control-Allow-Origin'] = '*'
    return response
