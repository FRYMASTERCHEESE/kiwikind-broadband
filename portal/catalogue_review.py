"""Read-only, owner+MFA review of private immutable catalogue releases."""
from copy import deepcopy
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import PrivateCatalogueRelease
from .pages import private
from .private_catalogue import validate_payload
from .views import endpoint
from payments.retail_pricing import order_quote


def summary(release):
    return {'id': release.pk, 'checksum': release.checksum,
        'created_at': release.created_at, 'products': len(release.payload),
        'active': release.active, 'approved': bool(release.approved_at and
            release.approved_digest == release.checksum),
        'verified_on': release.verified_on, 'valid_until': release.valid_until}


@endpoint(['GET'])
@private
def releases(request):
    return JsonResponse({'releases': [summary(r) for r in
        PrivateCatalogueRelease.objects.order_by('-created_at')[:100]],
        'review_only': True})


@endpoint(['GET'])
@private
def detail(request, pk):
    release = get_object_or_404(PrivateCatalogueRelease, pk=pk)
    products = validate_payload(deepcopy(release.payload))
    rows = []
    for product in products:
        monthly = Decimal(product['base'])
        setup = Decimal(product['baseSetup'])
        unknown = product['setupUnknown']
        selections = []
        for group in product['groups']:
            option = group['options'][0]
            monthly += Decimal(option['monthly'])
            setup += Decimal(option['setup'])
            unknown = unknown or option['unknown']
            selections.append({'group': group['label'], 'option': option['name']})
        totals = order_quote(int(monthly * 100), None if unknown else int(setup * 100),
            include_processing=settings.KIWIKIND_ALL_IN_RETAIL_ENABLED,
            monthly_price_increase_cents=400 if settings.KIWIKIND_ALL_IN_RETAIL_ENABLED else 0)
        rows.append({'source': product, 'default_selections': selections,
            'retail_preview': {key: value for key, value in totals.items()
                if key not in ('monthly_addition_cents', 'setup_addition_cents')}})
    return JsonResponse({'release': summary(release), 'products': rows,
        'review_only': True, 'can_publish': False})
