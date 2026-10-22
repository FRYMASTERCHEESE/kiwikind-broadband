"""The owner's screenshot catalogue. Supplier ordering is never invoked here."""
import hashlib
import json
import re
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from payments.retail_pricing import order_quote, _including_gst

ORDER_CONSENT = 'broadband-review-2026-10-22'


@lru_cache(maxsize=1)
def catalogue_source():
    raw = (Path(__file__).parent / 'data' / 'broadband_catalogue.json').read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()[:24]



# Only plan descriptions/option identifiers live in this public repository.
# Actual supplier rates from the user's authenticated Vetta portal are stored
# in VerifiedSupplierOption in the private Neon database, never here.
UFB_INSTALL_LABELS = (
    ('unknown', 'Not sure — KiwiKind will confirm the install type'),
    ('churn', 'Switching from another provider (churn)'),
    ('existing_ont', 'New service — fibre box (ONT) already exists'),
    ('new_ont', 'New fibre installation — no ONT yet'),
    ('additional_ont', 'Additional fibre box (ONT) needed'),
)


def effective_catalogue():
    """Per-request private rate projection for BOTH website and Android.

    Missing or unverified UFB speed prices are hidden, never silently replaced
    with stale snapshot values or zero. Installation defaults to unknown;
    addresses and final charges always require owner confirmation.
    """
    from .models import VerifiedSupplierOption
    source, legacy_revision = catalogue_source()
    records = {
        (r.group_id, r.option_id): r
        for r in VerifiedSupplierOption.objects.filter(
            product_id='ufb', verified=True, verified_on__isnull=False)
    }
    products = []
    for base in source:
        if base['id'] != 'ufb':
            item = dict(base)
            item['price_status'] = ('screen_checked' if item['id'] == 'adsl' else 'needs_supplier_confirmation')
            products.append(item)
            continue

        # Deliberately ignore every outdated wholesale value in the original
        # snapshot for UFB. No fallback to the old public JSON rates.
        base_speeds = {option['id']: option for option in base['groups'][0]['options']}
        speeds = []
        for (group_id, option_id), rate in sorted(records.items(),
                key=lambda item: (item[1].sort_order, item[0][1])):
            if group_id != 'speed':
                continue
            if (not rate.label.strip() or not 0 <= rate.monthly_ex_gst_cents <= 1000000
                    or rate.setup_ex_gst_cents is None or rate.setup_ex_gst_cents > 1000000):
                continue
            old = base_speeds.get(option_id, {})
            speeds.append({
                'id': option_id,
                'name': rate.label.strip(),
                'monthly': f'{rate.monthly_ex_gst_cents / 100:.2f}',
                'setup': f'{rate.setup_ex_gst_cents / 100:.2f}',
                'unknown': False,
                'usage': old.get('usage'),
            })
        if not speeds:
            # No private verified prices yet: fail CLOSED instead of selling
            # stale or falsely-free UFB; other catalogue categories remain.
            continue
        installs = [{
            'id': 'unknown',
            'name': UFB_INSTALL_LABELS[0][1],
            'monthly': '0.00', 'setup': '0.00', 'unknown': True, 'usage': None,
        }]
        for key, label in UFB_INSTALL_LABELS[1:]:
            rate = records.get(('install', key))
            known = bool(rate is not None and rate.monthly_ex_gst_cents == 0
                         and rate.setup_ex_gst_cents is not None
                         and 0 <= rate.setup_ex_gst_cents <= 1000000)
            installs.append({
                'id': key,
                'name': label,
                'monthly': '0.00',
                'setup': f'{rate.setup_ex_gst_cents / 100:.2f}' if known else '0.00',
                'unknown': not known,
                'usage': None,
            })
        item = dict(base)
        item['headline'] = f'{min(cents(o["monthly"]) for o in speeds) / 100:.2f}'
        item['description'] = ('Home fibre where your address is eligible. Choose the speed and '
            'installation type; the final setup charge is confirmed before payment.')
        item['groups'] = [
            {'id': '0', 'label': 'Choose your fibre speed', 'options': speeds},
            {'id': 'install', 'label': 'Installation / switching type (confirmed by KiwiKind)', 'options': installs},
        ]
        item['price_status'] = 'verified_speed_address_review_required'
        products.append(item)
    private_version = hashlib.sha256(json.dumps(
        products, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
    return products, hashlib.sha256(
        f'{legacy_revision}:{private_version}'.encode()).hexdigest()[:24]

def cents(value):
    return int(Decimal(value) * 100)


def quote(product_id, selections):
    products, revision = effective_catalogue()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        raise ValueError('This plan has no fully verified rate yet; contact KiwiKind for an address-specific quote.')
    if not isinstance(selections, list) or len(selections) != len(product['groups']):
        raise ValueError('Choose one option from each group.')
    monthly, setup = cents(product['base']), cents(product['baseSetup'])
    unknown = bool(product.get('setupUnknown'))
    options, usage = [], []
    for group, selection in zip(product['groups'], selections):
        option = next((o for o in group['options'] if type(selection) is str and o['id'] == selection), None)
        if not option:
            raise ValueError('A selected option is no longer available. Choose it again.')
        monthly += cents(option['monthly'])
        setup += cents(option['setup'])
        unknown = unknown or option['unknown']
        options.append({'group': group['label'], 'name': option['name']})
        if option.get('usage'):
            rate = Decimal(option['usage']['rate']) * Decimal('1.15')
            usage.append(f"Additional usage: NZ${rate:f}/{option['usage']['unit']} including GST"
                         + (' at the 95th percentile.' if option['usage']['unit'] == 'Mbps' else '.'))
    if product_id == 'mobile-4g':
        usage.append('Additional data: NZ$11.50/GB including GST.')
    if product_id == 'ufb':
        usage.append('Your exact installation/switching fee requires confirmation before payment; a speed-only setup of $0 does not guarantee free installation.')
    else:
        usage.append('These supplier rates require current confirmation, along with any address-specific fees, before payment.')
    result = {**order_quote(monthly, None if unknown else setup),
              'product_id': product_id, 'name': product['name'], 'selections': selections,
              'options': options, 'usage': usage, 'catalogue_version': revision,
              'price_status': product['price_status'],
              'price_confirmation_required': True,
              'source_monthly_cents': monthly, 'source_setup_cents': None if unknown else setup}
    fingerprint = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
    result['quote_version'] = hashlib.sha256(fingerprint).hexdigest()
    return result


def public_quote(value):
    return {key: item for key, item in value.items() if not key.startswith('source_')}


def catalogue_enabled():
    return settings.BROADBAND_CATALOGUE_ENABLED


@never_cache
@require_GET
def catalogue(request):
    products = []
    if catalogue_enabled():
        source, version = effective_catalogue()
        for p in source:
            groups = []
            for group in p['groups']:
                groups.append({'id': group['id'], 'label': group['label'], 'options': [
                    {'id': o['id'], 'name': o['name'],
                     'monthly_component_cents': _including_gst(cents(o['monthly'])),
                     'setup_component_cents': None if o['unknown'] else _including_gst(cents(o['setup'])),
                     'usage_based': bool(o.get('usage'))}
                    for o in group['options']]})
            products.append({'id': p['id'], 'name': p['name'], 'description': p['description'],
                             'headline_monthly_cents': _including_gst(cents(p['headline'])) + 300,
                             'headline_note': 'Lowest tier is 128Kbps; choose a normal home speed for streaming.' if p['id'] == 'ufb' else
                                 '5Mbps / 2Mbps uncapped' if p['id'] == 'fixed-wireless' else '',
                             'price_status': p['price_status'],
                             'price_confirmation_required': True,
                             'groups': groups,
                             'default_quote': public_quote(quote(p['id'], ['0'] * len(groups)))})
    if not catalogue_enabled():
        _, version = catalogue_source()
    return JsonResponse({'products': products, 'catalogue_version': version,
                         'currency': 'NZD', 'gst_included': True,
                         'monthly_addition_cents': 300, 'setup_addition_cents': 1000,
                         'supplier_orders_enabled': False,
                         'orders_enabled': catalogue_enabled(),
                         'payment_timing': 'after_connection_confirmation',
                         'consent_version': ORDER_CONSENT})


@never_cache
@require_GET
def quote_view(request):
    if not catalogue_enabled():
        return JsonResponse({'error': 'Broadband catalogue is temporarily unavailable.'}, status=503)
    try:
        value = quote(request.GET.get('product', ''), request.GET.get('options', '').split(','))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse(public_quote(value))


# Imported after pure catalogue functions to avoid the portal views import cycle.
from .views import endpoint, text, audit
from .security import limited
from .models import Order, BroadbandOrder
from .pages import private


@endpoint(['POST'], authenticated=True)
def submit_order(request):
    if not catalogue_enabled():
        return JsonResponse({'error': 'Broadband orders are temporarily unavailable.'}, status=503)
    if limited(request, 'broadband-orders', 20, 3600):
        return JsonResponse({'error': 'Order limit reached. Try again later.'}, status=429)
    data = request.data
    if data.get('consent_version') != ORDER_CONSENT or data.get('accept_review') is not True:
        raise ValueError('Confirm that availability and connection details must be checked before payment.')
    value = quote(data.get('product_id'), data.get('selections'))
    if data.get('quote_version') != value['quote_version']:
        return JsonResponse({'error': 'Prices changed. Refresh the quote before sending your order.'}, status=409)
    postcode = text(data, 'postcode', 4, 4)
    if not re.fullmatch(r'[0-9]{4}', postcode):
        raise ValueError('Use a four-digit NZ postcode.')
    phone = text(data, 'phone', 25, 0)
    if phone and not re.fullmatch(r'[+\d ()-]{6,25}', phone):
        raise ValueError('Enter a valid contact phone number.')
    key = uuid.UUID(text(data, 'idempotency_key', 36, 36))
    defaults = {'address': text(data, 'address', 300, 8), 'postcode': postcode,
                'contact_name': text(data, 'contact_name', 100), 'phone': phone,
                'consent_version': ORDER_CONSENT}
    with transaction.atomic():
        order, created = Order.objects.get_or_create(user=request.user, idempotency_key=key, defaults=defaults)
        if created:
            BroadbandOrder.objects.create(order=order, quote=value)
            audit(request, 'broadband_order_requested', order.pk)
        elif (any(getattr(order, k) != v for k, v in defaults.items())
              or not BroadbandOrder.objects.filter(order=order, quote=value).exists()):
            return JsonResponse({'error': 'This submission key belongs to a different order.'}, status=409)
    return JsonResponse({'id': str(order.pk), 'quote': public_quote(value),
                         'message': 'Order received for an address and connection check. Nothing has been charged. Once confirmed, your final offer will appear under Billing.'},
                        status=201 if created else 200)


@endpoint(['POST'])
@private
def prepare_offer(request, pk):
    """Prepare an unapproved draft. Existing owner review/MFA/payment gates remain."""
    from payments.live_models import LiveAgreement
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
        detail = get_object_or_404(BroadbandOrder.objects.select_for_update(), order=order)
        if order.status == 'cancelled':
            return JsonResponse({'error': 'This order was cancelled.'}, status=409)
        if detail.payment_agreement_id:
            return JsonResponse({'agreement_id': str(detail.payment_agreement_id)})
        value = detail.quote
        # Never turn a historical UFB quote into a payable offer after the
        # verified supplier rate or installation selection has changed.
        if value.get('product_id') == 'ufb':
            try:
                current = quote(value.get('product_id'), value.get('selections'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'The supplier fibre prices/options changed. Ask the customer to submit a fresh address request before preparing an offer.'}, status=409)
            if current['quote_version'] != value.get('quote_version'):
                return JsonResponse({'error': 'This fibre quote is outdated. A new reviewed quote is required before any payment offer.'}, status=409)
        # Unknown source setup stays unknown. It must be confirmed before review.
        terms = value['name'] + '\n' + '\n'.join(o['group']+': '+o['name'] for o in value['options'])
        if value['usage']:
            terms += '\n' + '\n'.join(value['usage'])
        terms += '\n\nComplete the confirmed connection, billing-start, contract, cancellation and refund terms before approving this offer.'
        agreement = LiveAgreement.objects.create(user=order.user, created_by=request.user,
            label=value['name'], service_reference='order-'+str(order.pk),
            source_monthly_cents=value['source_monthly_cents'], source_setup_cents=value['source_setup_cents'],
            service_terms=terms, supplier_confirmed=False, reviewed=False)
        detail.payment_agreement = agreement
        detail.save(update_fields=['payment_agreement'])
        order.status = 'reviewing'
        order.save(update_fields=['status'])
        audit(request, 'broadband_offer_drafted', order.pk)
    return JsonResponse({'agreement_id': str(agreement.pk),
                         'message': 'Draft prepared. Confirm supply, setup fees, payment date and written terms, then approve the offer.'}, status=201)
