"""Owner-only evidence-based launch action centre; never authorises public sales."""
from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from payments import gateway
from payments.models import TestAgreement, TestEvent, TestInvoice
from .models import AuditEvent, DraftPlan, Provider, WholesaleOrder
from .owner_admin import owner_session

def permitted(request):
    return owner_session(request) and admin.site.has_permission(request)

def evidence_snapshot():
    vetta = Provider.objects.filter(name__iexact='Vetta').first()
    reviewed = TestAgreement.objects.filter(reviewed=True, subscription_id__isnull=False)
    paid = (TestInvoice.objects.filter(agreement__in=reviewed,status='paid')
            .exclude(payment_intent='').exists() and
            TestEvent.objects.filter(kind='invoice.paid').exists())
    refunded = (TestInvoice.objects.filter(agreement__in=reviewed,status='paid',
                amount_cents__gt=0,refunded_cents=F('amount_cents')).exists()
                and TestEvent.objects.filter(kind='charge.refunded').exists())
    cancel = (reviewed.filter(cancel_at_period_end=True).exists()
              and TestEvent.objects.filter(kind='customer.subscription.updated').exists())
    approved = DraftPlan.objects.filter(review_status='approved',address_specific=False,
                approved_at__isnull=False,valid_until__gte=timezone.localdate()).count()
    private = DraftPlan.objects.count()
    closed = not settings.INTAKE_ENABLED and not settings.PLAN_PUBLICATION_ENABLED
    checks = [
      dict(label='Owner Google and authenticator MFA',done=True,
        detail='This report is visible only after the verified owner proof and MFA.'),
      dict(label='Public sales safeguards',done=closed,
        detail=('Intake and plan publication are off.' if closed else
                'WARNING: a sales or publication switch is enabled. Investigate before launch.')),
      dict(label='Stripe sandbox credentials',done=gateway.configured(),
        detail='Test configuration is present; no live Stripe keys or checkout are enabled.'),
      dict(label='Stripe real TEST invoice and webhook',done=paid,
        detail='Provider-bound TEST invoice and invoice.paid receipt recorded.' if paid else
               'A paid TEST invoice and signed receipt are not yet both present.'),
      dict(label='Stripe TEST full refund',done=refunded,
        detail='Fully refunded TEST invoice and charge.refunded receipt recorded.' if refunded else
               'The full TEST refund is not yet recorded.'),
      dict(label='Stripe TEST cancellation update',done=cancel,
        detail='Cancel-at-period-end and subscription.updated receipt recorded.' if cancel else
               'A verified subscription cancellation update is outstanding.'),
      dict(label='Supplier master framework recorded',done=bool(vetta and vetta.stage=='agreement_recorded'),
        detail='Owner-attested framework stage only; Product Terms and actual account/order rights are separate.'
            if vetta and vetta.stage=='agreement_recorded' else
            'Owner has not yet attested review of the signed framework in the private supplier register.'),
      dict(label='Approved general retail catalogue',done=approved>0,
        detail=f'{approved} reviewed general plan records. {private} total private records. No approval to publish is implied.'),
      dict(label='Supplier Product Terms and authenticated order integration',done=False,
        detail='Service-specific Product Terms, valid general price schedule, API documentation, address qualifications and real supplier order tests are not verified.'),
      dict(label='Stripe real renewal, declined card and authentication challenge',done=False,
        detail='Mock tests passed; these separate real sandbox lifecycle scenarios remain unverified.'),
      dict(label='Signed Android release and Play test on device',done=False,
        detail='Debug Android CI passed. A current signed APK/AAB and real-device test have not been independently verified.'),
      dict(label='Consumer contracts, GST, support, recovery and launch sign-off',done=False,
        detail='Business decisions and evidence remain required before opening orders, plans or live billing.')
    ]
    return {'checks':checks,'check_count':len(checks),
      'verified_count':sum(int(x['done']) for x in checks),
      'framework_recorded':bool(vetta and vetta.stage=='agreement_recorded'),
      'vetta_exists':vetta is not None,
      'private_plans':private,'approved_plans':approved,
      'live_supplier_orders':WholesaleOrder.objects.filter(rehearsal=False).count(),
      'public_sales_closed':closed,'production_ready':False}

@never_cache
@csrf_protect
def launch_readiness(request):
    if not permitted(request):
        return HttpResponse(status=404)
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    return TemplateResponse(request,'admin/launch_readiness.html',{
       **admin.site.each_context(request),'title':'Private launch readiness',**evidence_snapshot()})

@never_cache
@csrf_protect
def record_framework_review(request):
    if not permitted(request):
        return HttpResponse(status=404)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if request.POST.get('ack_framework_review') != 'yes':
        return HttpResponse('Confirm review of both framework signatures first.',status=400)
    with transaction.atomic():
        vetta=Provider.objects.select_for_update().filter(name__iexact='Vetta').first()
        if not vetta:
            return HttpResponse('Private supplier record missing. No agreement was invented.',status=409)
        if vetta.stage!='agreement_recorded':
            vetta.stage='agreement_recorded'
            vetta.save(update_fields=['stage'])
            AuditEvent.objects.create(actor=request.user,
                action='supplier_framework_attested',reference=f'provider:{vetta.pk}')
    messages.success(request,'Framework review recorded privately. Product Terms, ordering, plans and payments remain unapproved.')
    return redirect('private-launch-readiness')
