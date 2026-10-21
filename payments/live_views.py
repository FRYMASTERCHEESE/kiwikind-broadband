"""Account-scoped live billing. Card details stay on Stripe-hosted pages."""
import os
import uuid
from functools import wraps
import stripe
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from portal.models import AuditEvent
from portal.owner_admin import owner_session
from portal.views import endpoint
from . import live_gateway as gateway, live_service as service
from .live_models import LiveAgreement, LiveInvoice, LiveEvent, approved_agreements


def errors(fn):
    @wraps(fn)
    def call(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except LiveAgreement.DoesNotExist:
            return JsonResponse({'error': 'Reviewed payment agreement not found'}, status=404)
        except (ValueError, TypeError, ValidationError):
            return JsonResponse({'error': 'Invalid payment request or payment-start date'}, status=400)
        except gateway.ReconciliationError:
            return JsonResponse({'error': 'Payment status needs review. Refresh or contact KiwiKind; do not create another payment.'}, status=409)
        except (gateway.BillingUnavailable, stripe.StripeError):
            return JsonResponse({'error': 'Payment service unavailable. A previous request may still have completed; refresh before trying again.'}, status=503)
    return call


@never_cache
def page(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return render(request, 'payments/customer_payments.html')


@never_cache
@endpoint(['GET'], authenticated=True)
def summary(request):
    data = []
    from django.utils import timezone
    for a in approved_agreements().filter(user=request.user).prefetch_related('invoices').order_by('-created_at'):
        data.append({'id': str(a.pk), 'terms_version': str(a.terms_version), 'label': a.label,
            'monthly_cents': a.monthly_cents, 'setup_cents': a.setup_cents, 'currency': 'NZD',
            'tax_treatment': a.get_tax_treatment_display(), 'service_terms': a.service_terms,
            'bill_from': a.bill_from.isoformat() if a.bill_from else None,
            'ready_to_pay': bool(a.supplier_confirmed and a.bill_from and a.bill_from <= timezone.localdate()),
            'status': a.status, 'cancel_at_period_end': a.cancel_at_period_end,
            'can_manage': bool(a.subscription_id and gateway.credentials_ready()),
            'invoices': list(a.invoices.order_by('-created_at').values('id', 'amount_cents', 'status', 'refunded_cents', 'dispute_status', 'created_at'))})
    return JsonResponse({'mode': 'live', 'live_payments_enabled': gateway.configured(),
        'portal_available': bool(os.environ.get('STRIPE_LIVE_PORTAL_CONFIG_ID')), 'agreements': data})


@endpoint(['POST'], authenticated=True, throttle='live-checkout')
@errors
def checkout(request):
    if request.data.get('accept_live_recurring') is not True:
        return JsonResponse({'error': 'Explicit agreement to the displayed recurring payment terms is required'}, status=400)
    identifier = uuid.UUID(str(request.data.get('agreement_id', '')))
    if not approved_agreements().filter(pk=identifier, user=request.user).exists():
        raise LiveAgreement.DoesNotExist
    version = str(uuid.UUID(str(request.data.get('terms_version', ''))))
    api = gateway.client(for_checkout=True)
    return JsonResponse({'url': service.checkout(request.user, identifier, version, api), 'livemode': True})


@endpoint(['POST'], authenticated=True, throttle='live-cancel')
@errors
def cancel(request):
    if request.data.get('accept_live_cancel') is not True:
        return JsonResponse({'error': 'Confirm cancellation of future subscription billing'}, status=400)
    identifier = uuid.UUID(str(request.data.get('agreement_id', '')))
    a = approved_agreements().filter(pk=identifier, user=request.user).first()
    if not a or not a.subscription_id:
        raise LiveAgreement.DoesNotExist
    api = gateway.client()
    with transaction.atomic():
        a, _ = service.bind_subscription(api, a.subscription_id)
        if not a or a.user_id != request.user.pk:
            raise gateway.ReconciliationError('Ownership mismatch')
        if a.status != 'canceled' and not a.cancel_at_period_end:
            result = gateway.live_object(api.v1.subscriptions.update(a.subscription_id,
                {'cancel_at_period_end': True}, options={'idempotency_key': 'kiwikind-live-cancel-'+str(a.pk)}), 'subscription', a.subscription_id)
            if result.get('cancel_at_period_end') is not True:
                raise gateway.ReconciliationError('Cancellation not confirmed')
            a.cancel_at_period_end = True
            a.save(update_fields=['cancel_at_period_end', 'updated_at'])
            AuditEvent.objects.create(actor=request.user, action='live_billing_cancel_requested', reference=str(a.pk))
    return JsonResponse({'message': 'Future subscription billing will stop at the period end. Contact KiwiKind to confirm your broadband-service cancellation separately.'})


@endpoint(['POST'], authenticated=True, throttle='live-portal')
@errors
def portal(request):
    identifier = uuid.UUID(str(request.data.get('agreement_id', '')))
    a = approved_agreements().filter(pk=identifier, user=request.user).first()
    if not a or not a.customer_id:
        raise LiveAgreement.DoesNotExist
    config_id = os.environ.get('STRIPE_LIVE_PORTAL_CONFIG_ID', '')
    if not config_id.startswith('bpc_'):
        raise gateway.BillingUnavailable('Customer portal not configured')
    api = gateway.client()
    configuration = gateway.plain(api.v1.billing_portal.configurations.retrieve(config_id))
    features = configuration.get('features') or {}
    cancellation = features.get('subscription_cancel') or {}
    if (configuration.get('active') is not True or configuration.get('livemode') is not True
            or (features.get('subscription_update') or {}).get('enabled')
            or (cancellation.get('enabled') and cancellation.get('mode') != 'at_period_end')):
        raise gateway.BillingUnavailable('Portal must not change agreed plans or cancel immediately')
    customer = gateway.live_object(api.v1.customers.retrieve(a.customer_id), 'customer', a.customer_id)
    if customer.get('deleted'):
        raise gateway.ReconciliationError('Customer unavailable')
    result = gateway.plain(api.v1.billing_portal.sessions.create({'customer': a.customer_id,
        'configuration': config_id, 'return_url': gateway.origin()+'/payments/'}))
    if result.get('customer') != a.customer_id or not gateway.safe_portal(result.get('url')):
        raise gateway.ReconciliationError('Portal binding mismatch')
    return JsonResponse({'url': result['url'], 'livemode': True})


@csrf_exempt
@require_POST
def webhook(request):
    # Checkout can be paused without discarding updates for existing payments.
    if not gateway.credentials_ready():
        return JsonResponse({'error': 'Live webhook unavailable'}, status=503)
    if len(request.body) > 1000000:
        return JsonResponse({'error': 'Payload too large'}, status=413)
    try:
        event = gateway.plain(stripe.Webhook.construct_event(request.body,
            request.headers.get('Stripe-Signature', ''), os.environ['STRIPE_LIVE_WEBHOOK_SECRET'], tolerance=300))
        if (event.get('livemode') is not True or event.get('api_version') != gateway.API_VERSION
                or not str(event.get('id', '')).startswith('evt_')
                or event.get('account') not in (None, os.environ['STRIPE_LIVE_ACCOUNT_ID'])):
            return JsonResponse({'error': 'Event account, mode or version mismatch'}, status=400)
        supported = {'checkout.session.completed', 'customer.subscription.created', 'customer.subscription.updated',
            'customer.subscription.deleted', 'invoice.paid', 'invoice.payment_failed', 'invoice.voided',
            'invoice.marked_uncollectible', 'invoice.finalized', 'charge.refunded',
            'charge.dispute.created', 'charge.dispute.updated', 'charge.dispute.closed'}
        if event.get('type') not in supported:
            return JsonResponse({'received': True, 'ignored': True})
        obj = gateway.live_object(event['data']['object'])
        if LiveEvent.objects.filter(pk=event['id']).exists():
            return JsonResponse({'received': True, 'duplicate': True})
        api = gateway.client()
        with transaction.atomic():
            _, created = LiveEvent.objects.get_or_create(id=event['id'], defaults={'kind': event['type']})
            if created:
                service.reconcile(api, event['type'], obj)
        return JsonResponse({'received': True})
    except (ValueError, TypeError, KeyError, ValidationError, stripe.SignatureVerificationError):
        return JsonResponse({'error': 'Invalid webhook'}, status=400)
    except (stripe.StripeError, gateway.BillingUnavailable, gateway.ReconciliationError):
        return JsonResponse({'error': 'Reconciliation pending; retry'}, status=503)


@endpoint(['POST'], authenticated=True, throttle='live-refund')
@errors
def refund(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return JsonResponse({'error': 'Not found'}, status=404)
    if request.data.get('accept_live_refund') is not True:
        return JsonResponse({'error': 'Confirm the full real-money refund'}, status=400)
    identifier = uuid.UUID(str(request.data.get('invoice_id', '')))
    api = gateway.client()
    with transaction.atomic():
        invoice = LiveInvoice.objects.select_for_update().select_related('agreement').filter(pk=identifier, status='paid').first()
        if not invoice or not invoice.payment_intent or invoice.refunded_cents or invoice.dispute_status:
            raise gateway.ReconciliationError('Invoice is not eligible for a full refund')
        pi = gateway.live_object(api.v1.payment_intents.retrieve(invoice.payment_intent), 'payment_intent', invoice.payment_intent)
        if (pi.get('amount_received') != invoice.amount_cents or pi.get('currency') != 'nzd'
                or pi.get('customer') != invoice.agreement.customer_id or pi.get('status') != 'succeeded'):
            raise gateway.ReconciliationError('Refund binding mismatch')
        result = gateway.plain(api.v1.refunds.create({'payment_intent': invoice.payment_intent,
            'amount': invoice.amount_cents}, options={'idempotency_key': 'kiwikind-live-full-refund-'+str(invoice.pk)}))
        if (result.get('object') != 'refund' or not str(result.get('id', '')).startswith('re_')
                or result.get('payment_intent') != invoice.payment_intent
                or result.get('amount') != invoice.amount_cents or result.get('currency') != 'nzd'):
            raise gateway.ReconciliationError('Refund response mismatch')
        AuditEvent.objects.create(actor=request.user, action='live_full_refund_requested', reference=str(invoice.pk))
    return JsonResponse({'message': 'Full refund requested; final status will update after Stripe confirmation. Subscription and broadband cancellation are separate.', 'status': result.get('status')})
