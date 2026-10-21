"""Owner-only TEST fixtures and clock advancement, never live billing.

Hosted Checkout and signed webhooks exercise the existing app integration. Only
fixed synthetic amounts and a new clock-bound customer are used. No real customer
or original QA subscription is modified. No raw provider objects leave the API.
"""
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from portal.models import AuditEvent
from portal.pages import private
from portal.views import endpoint
from . import gateway, service
from .models import OwnerSandboxRun, TestAgreement, TestInvoice
from .views import billing_errors


def guard():
    if settings.INTAKE_ENABLED or settings.PLAN_PUBLICATION_ENABLED:
        raise gateway.BillingUnavailable('Sandbox exercise requires closed public sales')


def parameters(run):
    a=run.agreement
    if a.user_id!=run.owner_id or a.monthly_cents!=100 or a.setup_cents!=0 or not a.reviewed:
        raise gateway.ReconciliationError('QA fixture changed')
    return a


def projection(run):
    a=parameters(run)
    return {'id':str(run.pk),'scenario':run.scenario,'agreement_id':str(a.pk),
        'terms_version':str(a.terms_version),'status':a.status,'cancel_at_period_end':a.cancel_at_period_end,
        'has_checkout':bool(a.checkout_id),'clock_ready':bool(run.clock_id and run.customer_id),
        'advanced':run.advance_to is not None,'evidence':run.evidence,'checked_at':run.checked_at,
        'invoices':list(a.invoices.values('id','status','amount_cents','refunded_cents'))}


@endpoint(['GET','POST'],throttle='owner-scenario-start')
@private
@billing_errors
def runs(request):
    if request.method=='GET':
        return JsonResponse({'runs':[projection(r) for r in OwnerSandboxRun.objects.filter(owner=request.user).select_related('agreement').order_by('-created_at')[:10]]})
    guard()
    if request.data.get('confirm_test_only') is not True:raise ValueError('Confirm synthetic NZ$1/month TEST only; no broadband or real money')
    scenario=request.data.get('scenario')
    if scenario not in ('renewal','decline-3ds'):raise ValueError('Choose a supported test scenario')
    identifier=uuid.UUID(str(request.data.get('submission_key','')))
    api=gateway.client()
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        run=OwnerSandboxRun.objects.select_for_update().filter(pk=identifier).first()
        if run and (run.owner_id!=request.user.pk or run.scenario!=scenario):raise ValueError('Submission key conflict')
        if not run:
            if OwnerSandboxRun.objects.filter(owner=request.user,created_at__gte=timezone.now()-timedelta(days=1)).count()>=4:
                raise ValueError('Daily synthetic scenario limit reached; resume an existing exercise')
            agreement=TestAgreement.objects.create(user=request.user,created_by=request.user,
                label='OWNER QA '+scenario+' TEST ONLY',monthly_cents=100,setup_cents=0,reviewed=True)
            run=OwnerSandboxRun.objects.create(pk=identifier,owner=request.user,agreement=agreement,scenario=scenario)
            AuditEvent.objects.create(actor=request.user,action='sandbox_scenario_created',reference=str(run.pk))
    # Resume safely after interruption, with provider idempotency and a 23h cap.
    with transaction.atomic():
        run=OwnerSandboxRun.objects.select_for_update().select_related('agreement').get(pk=identifier)
        if timezone.now()-run.created_at>timedelta(hours=23):raise ValueError('Old fixture requires manual reconciliation')
        parameters(run)
        if not run.clock_id:
            clock=gateway.test_object(api.v1.test_helpers.test_clocks.create({'frozen_time':int(run.created_at.timestamp()),
                'name':'KiwiKind synthetic owner QA '+str(run.pk)},options={'idempotency_key':'kiwikind-clock-'+str(run.pk)}),'test_helpers.test_clock')
            run.clock_id=clock['id'];run.save(update_fields=['clock_id'])
        if not run.customer_id:
            customer=gateway.test_object(api.v1.customers.create({'test_clock':run.clock_id,
                'name':'KiwiKind synthetic owner QA','metadata':{'kiwikind_owner_qa':str(run.pk)}},
                options={'idempotency_key':'kiwikind-qa-customer-'+str(run.pk)}),'customer')
            if customer.get('test_clock')!=run.clock_id:raise gateway.ReconciliationError('Clock binding mismatch')
            run.customer_id=customer['id'];run.save(update_fields=['customer_id'])
    return JsonResponse({'message':'Synthetic test fixture ready. No payment attempted.',**projection(run)})


@endpoint(['POST'],throttle='owner-clock-advance')
@private
@billing_errors
def advance(request,pk):
    guard()
    if request.data.get('confirm_advance') is not True:raise ValueError('Confirm advancing only this synthetic TEST clock')
    api=gateway.client()
    with transaction.atomic():
        run=get_object_or_404(OwnerSandboxRun.objects.select_for_update().select_related('agreement'),pk=pk,owner=request.user,scenario='renewal')
        a=parameters(run)
        if not a.subscription_id or not run.customer_id or not run.clock_id:raise ValueError('Complete the initial test Checkout first')
        customer=gateway.test_object(api.v1.customers.retrieve(run.customer_id),'customer',run.customer_id)
        sub=gateway.test_object(api.v1.subscriptions.retrieve(a.subscription_id),'subscription',a.subscription_id)
        if (customer.get('test_clock')!=run.clock_id or sub.get('customer')!=run.customer_id
                or (sub.get('metadata') or {}).get('kiwikind_test_agreement')!=str(a.pk)):
            raise gateway.ReconciliationError('Clock/subscription binding mismatch')
        if not run.advance_to:
            items=(sub.get('items') or {}).get('data') or []
            boundary=items[0].get('current_period_end') if len(items)==1 else None
            if not isinstance(boundary,int):raise gateway.ReconciliationError('Period boundary unavailable')
            run.advance_to=boundary+7200;run.save(update_fields=['advance_to'])
        clock=gateway.test_object(api.v1.test_helpers.test_clocks.retrieve(run.clock_id),'test_helpers.test_clock',run.clock_id)
        if clock.get('status')=='ready' and clock.get('frozen_time',0)<run.advance_to:
            gateway.test_object(api.v1.test_helpers.test_clocks.advance(run.clock_id,{'frozen_time':run.advance_to},
                options={'idempotency_key':'kiwikind-advance-'+str(run.pk)}),'test_helpers.test_clock',run.clock_id)
            AuditEvent.objects.create(actor=request.user,action='sandbox_clock_advanced',reference=str(run.pk))
    return JsonResponse({'message':'TEST clock advancement requested. Refresh evidence after Stripe finishes processing.'})


@endpoint(['POST'],throttle='owner-scenario-check')
@private
@billing_errors
def evidence(request,pk):
    guard();run=get_object_or_404(OwnerSandboxRun.objects.select_related('agreement'),pk=pk,owner=request.user)
    a=parameters(run);api=gateway.client()
    customer=gateway.test_object(api.v1.customers.retrieve(run.customer_id),'customer',run.customer_id)
    if customer.get('test_clock')!=run.clock_id:raise gateway.ReconciliationError('Customer clock changed')
    flags={'initial_paid':False,'renewal_paid':False,'decline_seen':False,'authentication_requested':False,'authentication_completed':False,'ledger_synced':False}
    events=gateway.plain(api.v1.events.list({'created':{'gte':int(run.created_at.timestamp())-5},'limit':100}))
    for value in events.get('data',[]):
        event=gateway.test_object(value,'event');obj=(event.get('data') or {}).get('object') or {}
        if obj.get('customer')!=run.customer_id or obj.get('livemode') is not False:continue
        if event.get('type')=='payment_intent.payment_failed' and (obj.get('last_payment_error') or {}).get('code')=='card_declined':flags['decline_seen']=True
        if event.get('type')=='payment_intent.requires_action':flags['authentication_requested']=True
    if a.subscription_id:
        sub=gateway.test_object(api.v1.subscriptions.retrieve(a.subscription_id),'subscription',a.subscription_id)
        if sub.get('customer')!=run.customer_id:raise gateway.ReconciliationError('Subscription customer changed')
        invoices=gateway.plain(api.v1.invoices.list({'subscription':a.subscription_id,'limit':10}))
        for value in invoices.get('data',[]):
            invoice=gateway.test_object(value,'invoice')
            if (invoice.get('customer')!=run.customer_id or invoice.get('currency')!='nzd'
                    or service.invoice_subscription(invoice)!=a.subscription_id or invoice.get('total')!=100
                    or invoice.get('status')!='paid' or invoice.get('amount_paid')!=100):continue
            ledger=TestInvoice.objects.filter(agreement=a,provider_id=invoice['id'],status='paid',amount_cents=100).first()
            if ledger:
                if invoice.get('billing_reason')=='subscription_create':flags['initial_paid']=True
                if invoice.get('billing_reason')=='subscription_cycle':flags['renewal_paid']=True
                flags['ledger_synced']=True
                if ledger.payment_intent:
                    intent=gateway.test_object(api.v1.payment_intents.retrieve(ledger.payment_intent),'payment_intent',ledger.payment_intent)
                    if (intent.get('customer')!=run.customer_id or intent.get('currency')!='nzd'
                            or intent.get('amount')!=100 or intent.get('status')!='succeeded'):
                        raise gateway.ReconciliationError('Intent binding changed')
                    if intent.get('latest_charge'):
                        charge=gateway.test_object(api.v1.charges.retrieve(intent['latest_charge']),'charge',intent['latest_charge'])
                        card=(charge.get('payment_method_details') or {}).get('card') or {}
                        if (charge.get('customer')==run.customer_id and charge.get('payment_intent')==ledger.payment_intent
                                and charge.get('currency')=='nzd' and charge.get('amount')==100 and charge.get('paid') is True
                                and (card.get('three_d_secure') or {}).get('result')=='authenticated'):
                            flags['authentication_completed']=True
    run.evidence=flags;run.checked_at=timezone.now();run.save(update_fields=['evidence','checked_at'])
    return JsonResponse({'test_only':True,'flags':flags,'event_scan_complete':not events.get('has_more',False),
        'message':'Current Stripe TEST records compared with the application ledger. Missing flags are not a pass.'})
