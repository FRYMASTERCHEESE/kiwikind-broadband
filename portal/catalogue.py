"""Compatibility projection of the same private broadband release."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .broadband import catalogue_enabled, effective_catalogue, quote, public_quote


@require_GET
def plans(request):
    items = []
    if catalogue_enabled():
        for plan in effective_catalogue()[0]:
            value = public_quote(quote(plan['id'], [g['options'][0]['id'] for g in plan['groups']]))
            items.append({'id': plan['id'], 'name': plan['name'],
                'retail_monthly_cents': value['monthly_cents'],
                'retail_setup_cents': value['setup_cents'],
                'first_invoice_cents': value['first_invoice_cents'],
                'allowance': plan['allowance'], 'terms': plan['terms'],
                'currency': 'NZD', 'gst_included': True, 'address_availability': 'unverified'})
    response = JsonResponse({'plans': items, 'live_orders_enabled': False})
    response['Cache-Control'] = 'no-store'
    response['Access-Control-Allow-Origin'] = '*'
    return response
