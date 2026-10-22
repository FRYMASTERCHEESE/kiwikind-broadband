"""Owner-MFA-only, opt-in, one-time NZ$1 verification (no broadband contract)."""
import os
from datetime import timedelta

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from portal.pages import private
from portal.views import endpoint
from . import live_gateway as gateway
from .live_models import OneDollarVerification

CENTS = 100
TAG = 'kiwikind_owner_one_dollar'


def enabled():
    return os.environ.get('KIWIKIND_OWNER_DOLLAR_TEST_ENABLED') == '1' and gateway.credentials_ready()


def verified_session(row, raw):
    s = gateway.live_object(raw, 'checkout.session')
    if (s.get('mode') != 'payment' or s.get('currency') != 'nzd'
            or s.get('amount_total') != CENTS or s.get('subscription') is not None
            or s.get('client_reference_id') != str(row.pk)
            or (s.get('metadata') or {}).get(TAG) != str(row.pk)
            or not str(s.get('id', '')).startswith('cs_live_')
            or (row.checkout_id and row.checkout_id != s['id'])):
        raise gateway.ReconciliationError('Verification amount or identity mismatch')
    return s


@never_cache
@endpoint(['GET'], authenticated=True)
@private
def status(request):
    row = OneDollarVerification.objects.filter(owner=request.user).first()
    return JsonResponse({'mode': 'live', 'currency': 'NZD', 'amount_cents': CENTS,
        'enabled': enabled(), 'state': row.state if row else 'not_started',
        'refunded_cents': row.refunded_cents if row else 0,
        'can_start': enabled() and (row is None or row.state in ('not_started', 'checkout_open'))})


@never_cache
@endpoint(['POST'], authenticated=True, throttle='owner-dollar-checkout')
@private
def checkout(request):
    if request.data != {'confirm_one_time_live_nzd_1': True}:
        return JsonResponse({'error': 'Explicit one-time NZ$1 consent required; no price fields allowed'}, status=400)
    if not enabled():
        return JsonResponse({'error': 'Owner verification is not enabled on the secure server'}, status=503)
    try:
        api = gateway.client()  # validates pinned LIVE Stripe account and balance
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            row, _ = OneDollarVerification.objects.get_or_create(owner=request.user)
            if row.payment_intent_id or row.state in ('paid', 'refunded', 'partially_refunded'):
                raise gateway.ReconciliationError('Payment already completed')
            if row.started_at is None:
                row.started_at = timezone.now()
                row.state = 'checkout_open'
                row.save(update_fields=['started_at', 'state', 'updated_at'])
            if timezone.now() - row.started_at > timedelta(minutes=25) and not row.checkout_id:
                raise gateway.ReconciliationError('Earlier attempt may have reached Stripe')
        if row.checkout_id:
            session = verified_session(row, api.v1.checkout.sessions.retrieve(row.checkout_id))
        else:
            url = (settings.PAGES_URL + 'owner.html' if settings.PAGES_ENABLED
                   else gateway.origin() + '/payments/')
            params = {'mode': 'payment', 'client_reference_id': str(row.pk),
                'line_items': [{'price_data': {'currency': 'nzd', 'unit_amount': CENTS,
                    'product_data': {'name': 'KiwiKind owner-only NZ$1 verification'}}, 'quantity': 1}],
                'metadata': {TAG: str(row.pk)}, 'payment_intent_data': {'metadata': {TAG: str(row.pk)}},
                'automatic_tax': {'enabled': False}, 'allow_promotion_codes': False,
                'success_url': url + '?one_dollar=returned', 'cancel_url': url + '?one_dollar=cancelled',
                'expires_at': int((row.started_at + timedelta(hours=1)).timestamp())}
            session = verified_session(row, api.v1.checkout.sessions.create(
                params, options={'idempotency_key': 'kiwikind-owner-one-dollar-' + str(row.pk)}))
        if session.get('status') != 'open' or not gateway.safe_checkout(session.get('url')):
            raise gateway.ReconciliationError('Verification Checkout not open')
        with transaction.atomic():
            saved = OneDollarVerification.objects.select_for_update().get(pk=row.pk)
            if saved.checkout_id and saved.checkout_id != session['id']:
                raise gateway.ReconciliationError('Conflicting verification Checkout')
            saved.checkout_id = session['id']
            saved.save(update_fields=['checkout_id', 'updated_at'])
        return JsonResponse({'url': session['url'], 'livemode': True, 'mode': 'payment',
            'currency': 'NZD', 'amount_cents': CENTS, 'recurring': False})
    except gateway.ReconciliationError:
        return JsonResponse({'error': 'Verification needs review; do not start another charge'}, status=409)
    except (gateway.BillingUnavailable, stripe.StripeError):
        return JsonResponse({'error': 'Live payment unavailable; refresh before retrying'}, status=503)


def reconcile(api, kind, obj):
    """Called only AFTER the existing live webhook validates the Stripe signature."""
    if kind == 'checkout.session.completed':
        key = (obj.get('metadata') or {}).get(TAG)
        if not key:
            return False
        row = OneDollarVerification.objects.select_for_update().filter(pk=key).first()
        if not row or not row.checkout_id or row.checkout_id != obj.get('id'):
            raise gateway.ReconciliationError('Owner verification checkout not bound yet')
        session = verified_session(row, api.v1.checkout.sessions.retrieve(row.checkout_id))
        intent_id = session.get('payment_intent')
        if (session.get('status') != 'complete' or session.get('payment_status') != 'paid'
                or not isinstance(intent_id, str) or not intent_id.startswith('pi_')):
            raise gateway.ReconciliationError('Owner verification not paid')
        pi = gateway.live_object(api.v1.payment_intents.retrieve(intent_id), 'payment_intent', intent_id)
        if (pi.get('status') != 'succeeded' or pi.get('amount') != CENTS
                or pi.get('amount_received') != CENTS or pi.get('currency') != 'nzd'
                or (pi.get('metadata') or {}).get(TAG) != str(row.pk)
                or (row.payment_intent_id and row.payment_intent_id != intent_id)):
            raise gateway.ReconciliationError('Owner verification payment mismatch')
        row.payment_intent_id = intent_id
        row.state = 'paid' if not row.refunded_cents else row.state
        row.save(update_fields=['payment_intent_id', 'state', 'updated_at'])
        return True
    if kind == 'charge.refunded':
        intent_id = obj.get('payment_intent')
        row = OneDollarVerification.objects.select_for_update().filter(payment_intent_id=intent_id).first()
        if not row:
            return False
        charge = gateway.live_object(api.v1.charges.retrieve(obj['id']), 'charge', obj['id'])
        refund = charge.get('amount_refunded')
        if (charge.get('payment_intent') != intent_id or charge.get('amount') != CENTS
                or charge.get('currency') != 'nzd' or type(refund) is not int
                or refund < 0 or refund > CENTS):
            raise gateway.ReconciliationError('Owner refund mismatch')
        row.refunded_cents = refund
        row.state = 'refunded' if refund == CENTS else 'partially_refunded'
        row.save(update_fields=['refunded_cents', 'state', 'updated_at'])
        return True
    return False
