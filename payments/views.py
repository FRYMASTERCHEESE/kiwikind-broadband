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
    api = gateway.client()
    with transaction.atomic():
        invoice = TestInvoice.objects.select_for_update().select_related('agreement').filter(pk=identifier, status='paid').first()
        if not invoice or not invoice.payment_intent or invoice.refunded_cents or invoice.dispute_status:
            raise gateway.ReconciliationError('Test invoice is not eligible for a full refund')
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
    return JsonResponse({'live_payments_enabled':False, 'configuration':gateway.configuration(),
        'api_version':gateway.API_VERSION,'webhook_path':'/api/billing/webhook',
        'provider_tested':False,
        'blockers':['Real Stripe sandbox exercises not completed','Approved retail product and terms required',
            'Live-mode integration and release approval required','Supplier ordering remains manual']})


@never_cache
def refund_page(request, invoice_id):
    from django import forms
    from django.shortcuts import get_object_or_404
    from django.template.response import TemplateResponse
    if not owner_session(request) or not admin.site.has_permission(request):
        return JsonResponse({'error':'Not found'}, status=404)
    class Confirmation(forms.Form):
        confirm = forms.BooleanField(label='Request a full TEST refund for this invoice. No actual customer money is refunded.')
    invoice = get_object_or_404(TestInvoice.objects.select_related('agreement'),pk=invoice_id)
    form = Confirmation(request.POST if request.method == 'POST' else None)
    notice = ''
    if request.method == 'POST' and form.is_valid():
        try:
            notice = request_refund(request.user, invoice.pk)['message']
            form = Confirmation()
        except (gateway.BillingUnavailable,gateway.ReconciliationError,stripe.StripeError):
            form.add_error(None,'Test refund unavailable or pending reconciliation. No live refund was requested.')
    elif request.method not in ('GET','POST'):
        return JsonResponse({'error':'Method not allowed'},status=405)
    return TemplateResponse(request,'admin/payments/refund.html',{
        **admin.site.each_context(request),'title':'Test-only full refund','form':form,'invoice':invoice,'notice':notice})
