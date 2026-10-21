import os
import uuid
from functools import wraps
import stripe
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from portal.models import AuditEvent
from portal.owner_admin import owner_session
from portal.views import endpoint
from . import gateway, service
from .models import TestAgreement, TestInvoice, TestEvent


def billing_errors(fn):
    @wraps(fn)
    def call(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except TestAgreement.DoesNotExist:
            return JsonResponse({'error': 'Reviewed test agreement not found'}, status=404)
        except (ValueError, TypeError, ValidationError):
            return JsonResponse({'error': 'Invalid billing request'}, status=400)
        except gateway.ReconciliationError:
            return JsonResponse({'error': 'Test billing needs reconciliation; refresh or contact support. Do not repeat with a new agreement.'}, status=409)
        except (gateway.BillingUnavailable, stripe.StripeError):
            return JsonResponse({'error': 'Stripe test billing is unavailable; no live payment was requested.'}, status=503)
    return call


@never_cache
@endpoint(['GET'], authenticated=True)
def summary(request):
    records = TestAgreement.objects.filter(user=request.user, reviewed=True).order_by('-created_at')
    data = []
    for a in records:
        data.append({'id': str(a.pk), 'terms_version': str(a.terms_version), 'label': a.label, 'monthly_cents': a.monthly_cents,
            'setup_cents': a.setup_cents, 'currency': 'NZD', 'status': a.status,
            'cancel_at_period_end': a.cancel_at_period_end,
            'invoices': list(a.invoices.order_by('-created_at').values('id', 'amount_cents', 'status', 'refunded_cents', 'dispute_status', 'created_at'))})
    return JsonResponse({'mode': 'sandbox_only', 'live_payments_enabled': False,
        'test_enabled': gateway.configured() and bool(data), 'agreements': data})


@never_cache
def page(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if not request.user.is_authenticated:
        return redirect('/#signin')
    return render(request, 'payments/billing.html')


@endpoint(['POST'], authenticated=True, throttle='sandbox-checkout')
@billing_errors
def checkout(request):
    if request.data.get('accept_test_recurring') is not True:
        return JsonResponse({'error': 'Confirm test-only recurring billing first'}, status=400)
    identifier = uuid.UUID(str(request.data.get('agreement_id', '')))
    if not TestAgreement.objects.filter(pk=identifier, user=request.user, reviewed=True).exists():
        raise TestAgreement.DoesNotExist
    api = gateway.client()
    expected_version = str(uuid.UUID(str(request.data.get('terms_version', ''))))
    url = service.checkout(request.user, identifier, expected_version, api)
    return JsonResponse({'url': url, 'test_only': True})


@endpoint(['POST'], authenticated=True, throttle='sandbox-cancel')
@billing_errors
def cancel(request):
    if request.data.get('accept_test_cancel') is not True:
        return JsonResponse({'error': 'Confirm test cancellation first'}, status=400)
    identifier = uuid.UUID(str(request.data.get('agreement_id', '')))
    a = TestAgreement.objects.filter(pk=identifier, user=request.user, reviewed=True).first()
    if not a or not a.subscription_id:
        raise TestAgreement.DoesNotExist
    api = gateway.client()
    with transaction.atomic():
        a, _ = service.bind_subscription(api, a.subscription_id)
        if not a or a.user_id != request.user.pk:
            raise gateway.ReconciliationError('Owner mismatch')
        if a.status == 'canceled' or a.cancel_at_period_end:
            return JsonResponse({'message': 'Test cancellation already recorded; no broadband service was changed.'})
        response = gateway.test_object(api.v1.subscriptions.update(a.subscription_id,
            {'cancel_at_period_end': True}, options={'idempotency_key': 'kiwikind-sandbox-cancel-'+str(a.pk)}), 'subscription', a.subscription_id)
        if response.get('cancel_at_period_end') is not True:
            raise gateway.ReconciliationError('Cancellation not confirmed')
        a.cancel_at_period_end = True
        a.save(update_fields=['cancel_at_period_end','updated_at'])
        AuditEvent.objects.create(actor=request.user, action='sandbox_cancel_requested', reference=str(a.pk))
    return JsonResponse({'message': 'Test cancellation requested for period end. No broadband service was changed.'})


@endpoint(['POST'], authenticated=True, throttle='sandbox-refund')
@billing_errors
def refund(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return JsonResponse({'error': 'Not found'}, status=404)
    if request.data.get('accept_test_refund') is not True:
        return JsonResponse({'error': 'Confirm test refund first'}, status=400)
    identifier = uuid.UUID(str(request.data.get('invoice_id','')))
    return JsonResponse(request_refund(request.user, identifier))


def request_refund(actor, identifier):
    with transaction.atomic():
        invoice = TestInvoice.objects.select_for_update().select_related('agreement').filter(pk=identifier, status='paid').first()
        if invoice and invoice.amount_cents > 0 and invoice.refunded_cents == invoice.amount_cents:
            # A successfully reconciled Stripe refund is already final.
            # Repeat submits must not make a new provider request, even when
            # the provider is temporarily unavailable or sandbox is switched off.
            return {'message': 'This TEST invoice is already fully refunded. No second refund was requested.',
                    'status': 'succeeded', 'already_refunded': True}
        if not invoice or not invoice.payment_intent or invoice.refunded_cents or invoice.dispute_status:
            raise gateway.ReconciliationError('Test invoice is not eligible for a full refund')
        api = gateway.client()
        pi = gateway.test_object(api.v1.payment_intents.retrieve(invoice.payment_intent), 'payment_intent', invoice.payment_intent)
        if (pi.get('amount_received') != invoice.amount_cents or pi.get('currency') != 'nzd'
                or pi.get('customer') != invoice.agreement.customer_id or pi.get('status') != 'succeeded'):
            raise gateway.ReconciliationError('Refund binding mismatch')
        # Refunds have no livemode field. The test client and retrieved test intent
        # establish mode; bind the returned refund to that intent and exact amount.
        result = gateway.plain(api.v1.refunds.create({'payment_intent': invoice.payment_intent,
            'amount': invoice.amount_cents}, options={'idempotency_key': 'kiwikind-sandbox-full-refund-'+str(invoice.pk)}))
        if (result.get('object') != 'refund' or not str(result.get('id', '')).startswith('re_')
                or result.get('payment_intent') != invoice.payment_intent
                or result.get('amount') != invoice.amount_cents or result.get('currency') != 'nzd'):
            raise gateway.ReconciliationError('Refund response mismatch')
        AuditEvent.objects.create(actor=actor, action='sandbox_refund_requested', reference=str(invoice.pk))
    return {'message': 'Test refund requested; its final status awaits verified Stripe updates.', 'status': result.get('status')}


@csrf_exempt
@require_POST
def webhook(request):
    if not gateway.configured():
        return JsonResponse({'error':'Sandbox disabled'},status=503)
    if len(request.body) > 1000000:
        return JsonResponse({'error':'Payload too large'},status=413)
    try:
        event = gateway.plain(stripe.Webhook.construct_event(request.body,
            request.headers.get('Stripe-Signature',''), os.environ['STRIPE_TEST_WEBHOOK_SECRET'], tolerance=300))
        if (event.get('livemode') is not False or event.get('api_version') != gateway.API_VERSION
                or not str(event.get('id','')).startswith('evt_')
                or event.get('account') not in (None, os.environ['STRIPE_TEST_ACCOUNT_ID'])):
            return JsonResponse({'error':'Event account, mode or version mismatch'},status=400)
        supported = {'checkout.session.completed','customer.subscription.created','customer.subscription.updated',
            'customer.subscription.deleted','invoice.paid','invoice.payment_failed','invoice.voided',
            'invoice.marked_uncollectible','invoice.finalized','charge.refunded','charge.dispute.created',
            'charge.dispute.updated','charge.dispute.closed'}
        if event.get('type') not in supported:
            return JsonResponse({'received':True,'ignored':True})
        obj = gateway.test_object(event['data']['object'])
        if TestEvent.objects.filter(pk=event['id']).exists():
            return JsonResponse({'received':True,'duplicate':True})
        api = gateway.client()
        with transaction.atomic():
            _, created = TestEvent.objects.get_or_create(id=event['id'],defaults={'kind':event['type']})
            if created:
                service.reconcile(api,event['type'],obj)
        return JsonResponse({'received':True})
    except (ValueError, TypeError, KeyError, ValidationError, stripe.SignatureVerificationError):
        return JsonResponse({'error':'Invalid webhook'},status=400)
    except (stripe.StripeError, gateway.BillingUnavailable, gateway.ReconciliationError):
        # Receipt and ledger roll back together. Provider can safely retry.
        return JsonResponse({'error':'Test reconciliation pending; retry'},status=503)


@never_cache
def readiness(request):
    if not owner_session(request) or not admin.site.has_permission(request):
        return JsonResponse({'error':'Not found'},status=404)
    if request.method != 'GET':
        return JsonResponse({'error':'Method not allowed'},status=405)
    # Only owner+MFA gets these aggregate TEST-only facts. Provider evidence
    # must be present in both the reconciled ledger and signed webhook receipts.
    # These are not claims that renewals, failed payments or signed Android
    # releases have been exercised.
    from django.db.models import F
    verified = TestAgreement.objects.filter(reviewed=True, subscription_id__isnull=False)
    paid = (TestInvoice.objects.filter(agreement__in=verified, status='paid')
            .exclude(payment_intent='').exists()
            and TestEvent.objects.filter(kind='invoice.paid').exists())
    refunded = (TestInvoice.objects.filter(agreement__in=verified, amount_cents__gt=0,
                  refunded_cents=F('amount_cents')).exists()
                and TestEvent.objects.filter(kind='charge.refunded').exists())
    cancellation = (verified.filter(cancel_at_period_end=True).exists()
                    and TestEvent.objects.filter(kind='customer.subscription.updated').exists())
    blockers = []
    if not paid:
        blockers.append('An actual sandbox paid invoice and matching webhook remain unverified')
    if not refunded:
        blockers.append('An actual full sandbox refund webhook remains unverified')
    if not cancellation:
        blockers.append('A real sandbox cancellation update remains unverified')
    blockers.extend([
        'Sandbox renewal, failed card and authentication-required journeys are not yet exercised end to end',
        'Signed Android release on device and Google Play testing require separate verification',
        'Approved retail product, GST treatment, terms and supplier availability required',
        'Live-mode integration, commercial approval and release review required',
        'Supplier ordering remains manual pending verified partner integration'
    ])
    return JsonResponse({'live_payments_enabled': False, 'configuration': gateway.configuration(),
        'api_version': gateway.API_VERSION, 'webhook_path': '/api/billing/webhook',
        'provider_tested': paid, 'sandbox_payment_verified': paid,
        'sandbox_refund_verified': refunded, 'sandbox_cancellation_verified': cancellation,
        'blockers': blockers})


@never_cache
def refund_page(request, invoice_id):
    from django import forms
    from django.shortcuts import get_object_or_404
    from django.template.response import TemplateResponse
    if not owner_session(request) or not admin.site.has_permission(request):
        return JsonResponse({'error':'Not found'}, status=404)
    class Confirmation(forms.Form):
        confirm = forms.BooleanField(label='Request a full TEST refund for this invoice. No actual customer money is refunded.')
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    invoice = get_object_or_404(TestInvoice.objects.select_related('agreement'),pk=invoice_id)
    form = Confirmation(request.POST if request.method == 'POST' else None)
    notice = ''
    if request.method == 'POST' and form.is_valid():
        try:
            notice = request_refund(request.user, invoice.pk)['message']
            form = Confirmation()
        except (gateway.BillingUnavailable, gateway.ReconciliationError, stripe.StripeError):
            form.add_error(None, 'TEST refund not confirmed. Check the verified billing ledger before retrying; a request may already be processing.')
    # A concurrent Stripe webhook can have updated the ledger while the user
    # was submitting the form. Always show fresh state, not a stale invoice.
    invoice.refresh_from_db()
    fully_refunded = (invoice.status == 'paid' and invoice.amount_cents > 0
                      and invoice.refunded_cents == invoice.amount_cents)
    refundable = (invoice.status == 'paid' and bool(invoice.payment_intent)
                  and not invoice.refunded_cents and not invoice.dispute_status)
    return TemplateResponse(request,'admin/payments/refund.html',{
        **admin.site.each_context(request), 'title': 'Test-only full refund',
        'form': form, 'invoice': invoice, 'notice': notice,
        'fully_refunded': fully_refunded, 'can_request_refund': refundable,
        'amount_nzd': f'{invoice.amount_cents // 100}.{invoice.amount_cents % 100:02d}',
        'refunded_nzd': f'{invoice.refunded_cents // 100}.{invoice.refunded_cents % 100:02d}'})
