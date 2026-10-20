"""Isolated synthetic Stripe billing. No live payments or supplier activation."""
import os
import stripe
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import BillingAgreement, Invoice, StripePayment, StripeEvent, AuditEvent
from .stripe_staging import configured, gateway_options, safe_url, plain
from .views import endpoint
from .admin_site import is_owner

@endpoint(['GET'],True)
def agreements(request):
    return JsonResponse({'test_enabled':configured(),'gocardless_status':'pending_approval',
        'agreements':list(BillingAgreement.objects.filter(user=request.user).values(
            'id','monthly_cents','setup_cents','status','synthetic_reviewed'))})

@endpoint(['POST'],True,throttle='subscription')
def subscribe(request):
    if not configured():return JsonResponse({'error':'Sandbox billing disabled'},status=503)
    if not settings.PUBLIC_ORIGIN.startswith('https://') and not settings.DEBUG:
        return JsonResponse({'error':'HTTPS required'},status=503)
    if request.data.get('accept_test_recurring') is not True:
        return JsonResponse({'error':'Explicit synthetic recurring billing consent required'},status=400)
    with transaction.atomic():
        a=BillingAgreement.objects.select_for_update().filter(pk=request.data.get('agreement_id'),user=request.user,synthetic_reviewed=True).first()
        if not a:return JsonResponse({'error':'Reviewed synthetic agreement not found'},status=404)
        if a.status!='pending' or a.subscription_id:return JsonResponse({'error':'Agreement already submitted'},status=409)
        if not a.checkout_id and timezone.now()-a.created_at > timedelta(hours=23):
            return JsonResponse({'error':'Old agreement requires reconciliation and a new reviewed agreement'},status=409)
        if not 50 <= a.monthly_cents <= 1000000 or a.setup_cents > 1000000:
            return JsonResponse({'error':'Amounts require owner review'},status=400)
        try:
            if a.checkout_id:
                result=stripe.checkout.Session.retrieve(a.checkout_id,**gateway_options())
                result=plain(result)
                if result.get('status')!='open':return JsonResponse({'error':'Checkout requires reconciliation'},status=409)
            else:
                items=[{'price_data':{'currency':'nzd','unit_amount':a.monthly_cents,'recurring':{'interval':'month'},'product_data':{'name':'KiwiKind synthetic monthly test'}},'quantity':1}]
                if a.setup_cents:items.append({'price_data':{'currency':'nzd','unit_amount':a.setup_cents,'product_data':{'name':'KiwiKind synthetic setup test'}},'quantity':1})
                result=stripe.checkout.Session.create(mode='subscription',payment_method_types=['card'],
                    success_url=settings.PUBLIC_ORIGIN+'/?checkout=returned',cancel_url=settings.PUBLIC_ORIGIN+'/?checkout=cancelled',
                    customer_email=request.user.email,line_items=items,metadata={'agreement_id':str(a.id)},
                    subscription_data={'metadata':{'agreement_id':str(a.id)}},
                    idempotency_key='kiwikind-test-agreement-'+str(a.id),**gateway_options())
            result=plain(result)
            if result.get('livemode') is not False or not safe_url(result.get('url')):
                return JsonResponse({'error':'Invalid test checkout response'},status=502)
            a.checkout_id=result['id'];a.checkout_url=result['url'];a.consent_at=timezone.now();a.save()
            AuditEvent.objects.create(actor=request.user,action='test_recurring_consent',reference=str(a.id))
            return JsonResponse({'url':result['url']})
        except stripe.StripeError:return JsonResponse({'error':'Stripe unavailable'},status=502)

class ReconciliationError(Exception):pass

@endpoint(['POST'],True,throttle='cancel-subscription')
def cancel_subscription(request):
    if not configured():return JsonResponse({'error':'Sandbox billing disabled'},status=503)
    a=BillingAgreement.objects.filter(pk=request.data.get('agreement_id'),user=request.user,synthetic_reviewed=True).first()
    if not a or not a.subscription_id:return JsonResponse({'error':'Synthetic subscription not found'},status=404)
    try:
        stripe.Subscription.modify(a.subscription_id,cancel_at_period_end=True,
            idempotency_key='kiwikind-test-cancel-'+str(a.id),**gateway_options())
        AuditEvent.objects.create(actor=request.user,action='test_cancel_requested',reference=str(a.id))
        return JsonResponse({'message':'Test cancellation submitted for period end; awaiting provider reconciliation.'})
    except stripe.StripeError:return JsonResponse({'error':'Cancellation unavailable'},status=502)

def reconcile(event):
    kind=event['type'];obj=event['data']['object']
    if obj.get('livemode') is not False:raise ReconciliationError('Live object rejected')
    if kind=='checkout.session.completed' and obj.get('mode')=='payment':
        p=StripePayment.objects.select_for_update().filter(session_id=obj['id']).select_related('invoice').first()
        if not p:return
        if not p.invoice.sandbox or obj.get('currency')!='nzd' or obj.get('amount_total')!=p.amount_cents or p.invoice.amount_cents!=p.amount_cents:
            raise ReconciliationError('Payment amount or currency mismatch')
        if obj.get('payment_status')!='paid':return
        p.payment_intent=obj.get('payment_intent') or '';p.paid=True;p.save()
        p.invoice.status='paid';p.invoice.save(update_fields=['status'])
    elif kind=='checkout.session.completed' and obj.get('mode')=='subscription':
        a=BillingAgreement.objects.select_for_update().filter(checkout_id=obj['id']).first()
        if a and a.synthetic_reviewed and a.consent_at:
            sub=obj.get('subscription')
            if not sub:raise ReconciliationError('Missing subscription')
            if a.subscription_id and a.subscription_id!=sub:raise ReconciliationError('Subscription mismatch')
            a.subscription_id=sub;a.save(update_fields=['subscription_id'])
    elif kind.startswith('customer.subscription.'):
        aid=obj.get('metadata',{}).get('agreement_id')
        if not aid:return
        a=BillingAgreement.objects.select_for_update().filter(pk=aid,synthetic_reviewed=True,consent_at__isnull=False).first()
        if not a:return
        if a.subscription_id and a.subscription_id!=obj['id']:raise ReconciliationError('Subscription mismatch')
        # Retrieve current state: old events must not revive a cancelled subscription.
        current=plain(stripe.Subscription.retrieve(obj['id'],**gateway_options()))
        if current.get('livemode') is not False:raise ReconciliationError('Live subscription rejected')
        a.subscription_id=obj['id'];a.status=current['status'];a.save(update_fields=['subscription_id','status'])
    elif kind in ['invoice.paid','invoice.payment_failed','invoice.voided']:
        details=(obj.get('parent') or {}).get('subscription_details') or {}
        sub=details.get('subscription') or obj.get('subscription')
        if not sub:return
        a=BillingAgreement.objects.select_for_update().filter(subscription_id=sub).first()
        if not a:
            # Stripe does not guarantee event ordering. Retry after the subscription event.
            raise ReconciliationError('Subscription not reconciled yet')
        if not a.synthetic_reviewed or not a.consent_at:raise ReconciliationError('Unreviewed agreement')
        current=plain(stripe.Invoice.retrieve(obj['id'],**gateway_options()))
        expected=a.monthly_cents+(a.setup_cents if current.get('billing_reason')=='subscription_create' else 0)
        if current.get('livemode') is not False or current.get('currency')!='nzd' or current.get('total')!=expected:
            raise ReconciliationError('Invoice amount or currency mismatch')
        paid=current.get('status')=='paid'
        ledger,_=Invoice.objects.get_or_create(supplier_reference='stripe-test:'+obj['id'],defaults={
            'user':a.user,'amount_cents':expected,'currency':'NZD','due_date':timezone.localdate(),'status':'unpaid','sandbox':True})
        if not ledger.sandbox or ledger.user_id!=a.user_id or ledger.amount_cents!=expected:raise ReconciliationError('Ledger mismatch')
        ledger.status='paid' if paid else ('void' if current.get('status')=='void' else 'unpaid');ledger.save(update_fields=['status'])
        p,_=StripePayment.objects.get_or_create(provider_invoice_id=obj['id'],defaults={'invoice':ledger,'agreement':a,'amount_cents':expected})
        p.paid=paid
        # Current Stripe Invoice uses a payments collection; refunds use the charge event mapping too.
        intent=current.get('payment_intent')
        if not intent and paid:
            payments=plain(stripe.InvoicePayment.list(invoice=obj['id'],**gateway_options()))
            for entry in payments.get('data',[]):
                if entry.get('status')=='paid':intent=(entry.get('payment') or {}).get('payment_intent');break
        p.payment_intent=intent or p.payment_intent;p.save()
    elif kind=='charge.refunded':
        p=StripePayment.objects.select_for_update().filter(payment_intent=obj.get('payment_intent')).first()
        if not p:return
        current=plain(stripe.Charge.retrieve(obj['id'],**gateway_options()))
        if current.get('livemode') is not False or current.get('payment_intent')!=p.payment_intent or current.get('currency')!='nzd' or current.get('amount')!=p.amount_cents:
            raise ReconciliationError('Refund mismatch')
        amount=current.get('amount_refunded',0)
        if not 0<=amount<=p.amount_cents:raise ReconciliationError('Invalid refund amount')
        p.refunded_cents=amount;p.save(update_fields=['refunded_cents'])

@csrf_exempt
@require_POST
def webhook(request):
    if not configured():return JsonResponse({'error':'Sandbox billing disabled'},status=503)
    if len(request.body)>1000000:return JsonResponse({'error':'Payload too large'},status=413)
    try:
        event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),os.environ['STRIPE_TEST_WEBHOOK_SECRET'],tolerance=300)
    except (ValueError,stripe.SignatureVerificationError):return JsonResponse({'error':'Invalid signature'},status=400)
    event=plain(event)
    if event.get('livemode') is not False:return JsonResponse({'error':'Live event rejected'},status=400)
    try:
        with transaction.atomic():
            _,created=StripeEvent.objects.get_or_create(id=event['id'],defaults={'kind':event['type']})
            if created:reconcile(event)
        return JsonResponse({'received':True})
    except (ReconciliationError,stripe.StripeError):
        # Roll back the receipt as well so Stripe can retry safely.
        return JsonResponse({'error':'Reconciliation pending owner review or retry'},status=503)
    except (KeyError,ValueError,TypeError):return JsonResponse({'error':'Invalid event'},status=400)

@endpoint(['POST'],True,throttle='refund')
def refund(request):
    if not is_owner(request.user) or not request.user.is_verified():return JsonResponse({'error':'Not found'},status=404)
    if not settings.ADMIN_ENABLED or not configured():return JsonResponse({'error':'Sandbox billing disabled'},status=503)
    with transaction.atomic():
        p=StripePayment.objects.select_for_update().filter(pk=request.data.get('payment_id'),paid=True,invoice__sandbox=True).first()
        if not p or not p.payment_intent:return JsonResponse({'error':'Synthetic payment not found'},status=404)
        try:
            # Full refund only. No client-supplied amount, deterministic retry key.
            result=stripe.Refund.create(payment_intent=p.payment_intent,idempotency_key='kiwikind-test-refund-'+str(p.pk),**gateway_options())
            AuditEvent.objects.create(actor=request.user,action='test_refund_requested',reference=str(p.pk))
            return JsonResponse({'id':result['id'],'status':result['status'],'message':'Refund submitted; settlement requires reconciliation.'})
        except stripe.StripeError:return JsonResponse({'error':'Refund unavailable'},status=502)
