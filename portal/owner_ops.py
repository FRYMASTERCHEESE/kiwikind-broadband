"""Allowlisted owner operations for Pages. Never exposes Django's generic admin.

All writes require the existing owner Google/OTP session, CSRF, a signed current
record version and model validation. No deletion, credentials or sales switches.
"""
import hashlib
import json
import uuid
from functools import wraps
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import (Order, Ticket, Message, PrivacyRequest, Provider, DraftPlan,
    AvailabilityEvidence, WholesaleOrder, WholesaleFault, WholesaleEvent, Invoice, AuditEvent)
from .owner_admin import OWNER_EMAIL, OWNER_USERNAME
from .pages import private
from .views import endpoint, text
from .catalogue_forms import CataloguePlanForm, catalogue_readiness
from .wholesale import transition, ORDER_TRANSITIONS, FAULT_TRANSITIONS
from payments.models import TestAgreement, TestInvoice, TestEvent
from payments.admin import TestAgreementForm
from payments.live_models import LiveAgreement, LiveInvoice, LiveEvent
from payments.live_forms import LiveAgreementForm
from payments import live_gateway

User = get_user_model()


def spec(model, fields, display, *, create=False, search=(), readonly=False):
    return dict(model=model,fields=fields,display=display,create=create,search=search,readonly=readonly)


SPECS = {
 'payment-agreements':spec(LiveAgreement,['user','label','service_reference','source_monthly_cents','source_setup_cents','service_terms','bill_from','supplier_confirmed','reviewed'],['id','label','user_id','monthly_cents','setup_cents','reviewed','status','bill_from','terms_version','checkout_started_at'],create=True),
 'payment-invoices':spec(LiveInvoice,[],['id','agreement_id','amount_cents','status','refunded_cents','dispute_status','created_at'],readonly=True),
 'payment-events':spec(LiveEvent,[],['id','kind','received_at'],readonly=True),
 'customers':spec(User,['first_name','last_name','is_active'],['email','first_name','last_name','is_active','date_joined','last_login'],search=['email','first_name','last_name']),
 'requests':spec(Order,['status'],['id','user_id','address','postcode','contact_name','phone','status','created_at'],search=['address','contact_name']),
 'tickets':spec(Ticket,['status'],['id','user_id','subject','category','status','created_at'],search=['subject']),
 'privacy':spec(PrivacyRequest,['status'],['id','user_id','status','created_at']),
 'providers':spec(Provider,['name','website','summary','stage','contact_date','notes'],['id','name','stage','contact_date'],create=True,search=['name']),
 'catalogue':spec(DraftPlan,['name','network','download_mbps','upload_mbps','source_reference','verified_at','valid_until','address_specific','notes','wholesale_ex_gst','wholesale_inc_gst','setup_ex_gst','setup_inc_gst','retail_ex_gst','retail_setup_ex_gst','review_status'],['id','name','review_status','address_specific','updated_at'],create=True,search=['name','source_reference']),
 'availability':spec(AvailabilityEvidence,['address','postcode','result','source_reference','checked_at','valid_until','rehearsal','notes'],['id','address','postcode','result','checked_at','rehearsal'],create=True),
 'preparation':spec(WholesaleOrder,['customer_request','rehearsal','address','postcode','plan','availability'],['id','state','revision','rehearsal','address','updated_at'],create=True),
 'faults':spec(WholesaleFault,['ticket','rehearsal','summary','service_reference','diagnostics'],['id','state','revision','rehearsal','summary','updated_at'],create=True),
 'invoices':spec(Invoice,[],['id','user_id','amount_cents','currency','due_date','status'],readonly=True),
 'audit':spec(AuditEvent,[],['id','actor_id','action','reference','created_at'],readonly=True),
 'history':spec(WholesaleEvent,[],['id','order_id','fault_id','from_state','to_state','reference','note','created_at'],readonly=True),
 'test-agreements':spec(TestAgreement,['user','label','monthly_cents','setup_cents','reviewed'],['id','label','user_id','monthly_cents','setup_cents','reviewed','status','cancel_at_period_end','terms_version','checkout_started_at','created_at'],create=True),
 'test-invoices':spec(TestInvoice,[],['id','agreement_id','amount_cents','status','refunded_cents','dispute_status','created_at'],readonly=True),
 'test-events':spec(TestEvent,[],['id','kind','received_at'],readonly=True),
}


def customers():
    return User.objects.filter(is_staff=False,is_superuser=False).exclude(email__iexact=OWNER_EMAIL).exclude(username=OWNER_USERNAME)


def records(kind):
    return customers() if kind=='customers' else SPECS[kind]['model'].objects.all()


def data_value(value):
    return json.loads(json.dumps(value,cls=DjangoJSONEncoder))


def fingerprint(obj, fields):
    values=model_to_dict(obj,fields=fields)
    for name in ('revision','state','updated_at'):
        if hasattr(obj,name):values['__'+name]=getattr(obj,name)
    return hashlib.sha256(json.dumps(values,cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()


def version(kind,obj):
    return signing.dumps({'kind':kind,'pk':str(obj.pk),'digest':fingerprint(obj,SPECS[kind]['fields'])},salt='owner-ops-version')


def current_version(kind,obj,token):
    try: payload=signing.loads(token,salt='owner-ops-version',max_age=1800)
    except (signing.BadSignature,TypeError):return False
    return payload=={'kind':kind,'pk':str(obj.pk),'digest':fingerprint(obj,SPECS[kind]['fields'])}


def editable(kind,obj):
    if SPECS[kind]['readonly']:return False
    if kind=='availability' and not obj._state.adding:return False
    if kind in ('preparation','faults') and obj.state not in ('draft','triage'):return False
    if kind in ('test-agreements','payment-agreements') and obj.checkout_started_at:return False
    return True


def form_for(kind,obj,data=None):
    base=CataloguePlanForm if kind=='catalogue' else TestAgreementForm if kind=='test-agreements' else LiveAgreementForm if kind=='payment-agreements' else forms.ModelForm
    cls=forms.modelform_factory(SPECS[kind]['model'],form=base,fields=SPECS[kind]['fields'])
    form=cls(data=data,instance=obj)
    for name,field in form.fields.items():
        if isinstance(field,forms.ModelChoiceField):
            if field.queryset.model is User:field.queryset=customers() | User.objects.filter(pk=obj.created_by_id if hasattr(obj,'created_by_id') else None)
            if kind=='test-agreements':field.queryset=User.objects.filter(pk=obj.created_by_id)
        if kind in ('preparation','faults') and not obj._state.adding and name in ('rehearsal','customer_request','ticket'):
            field.disabled=True
    return form


def detail(kind,obj):
    form=form_for(kind,obj)
    fields=[]
    initial=model_to_dict(obj,fields=SPECS[kind]['fields'])
    for name,field in form.fields.items():
        value=initial.get(name,form.initial.get(name,field.initial))
        if callable(value):value=None
        choices=None
        if isinstance(field,forms.ModelChoiceField):
            choices=[['','Unknown / none']]+[[str(x.pk),str(x)[:160]] for x in field.queryset[:200]]
        elif hasattr(field,'choices'):choices=[[str(k),str(v)] for k,v in field.choices]
        fields.append({'name':name,'label':str(field.label or name.replace('_',' ').capitalize()),'required':field.required,
            'value':data_value(value),'disabled':field.disabled,'choices':choices,
            'type':'checkbox' if isinstance(field,forms.BooleanField) else 'textarea' if isinstance(field.widget,forms.Textarea) else 'text',
            'help':str(field.help_text),'max_length':getattr(field,'max_length',None)})
    result={'kind':kind,'id':str(obj.pk) if not obj._state.adding else 'new','editable':editable(kind,obj),
        'version':version(kind,obj),'fields':fields,
        'record':{name:data_value(getattr(obj,name)) for name in SPECS[kind]['display']}}
    if kind=='tickets' and not obj._state.adding:
        result['messages']=list(obj.messages.order_by('created_at').values('id','author_id','body','created_at')[:200])
    if kind=='catalogue':result['checklist']=catalogue_readiness(obj)
    if kind=='requests' and not obj._state.adding and hasattr(obj, 'broadband'):
        from .broadband import public_quote
        result['broadband'] = public_quote(obj.broadband.quote)
        result['payment_agreement_id'] = str(obj.broadband.payment_agreement_id) if obj.broadband.payment_agreement_id else None
    if kind in ('preparation','faults') and not obj._state.adding:
        graph=ORDER_TRANSITIONS if kind=='preparation' else FAULT_TRANSITIONS
        blocked={'submitted','provisioning','active'} if kind=='preparation' else {'escalated','investigating'}
        result['transitions']=[s for s in graph[obj.state] if obj.rehearsal or s not in blocked]
        result['revision']=obj.revision
        result['history']=list(obj.events.order_by('-created_at').values('from_state','to_state','note','reference','created_at')[:50])
    return result


@endpoint(['POST'], throttle='owner-price-preview')
@private
def retail_price_preview(request):
    """Read-only owner+MFA preview; uses the SAME backend policy as Checkout.

    Never saves an agreement, approves a service, creates a payment, or places
    a supplier order. Client-supplied prices are inputs for owner examination
    and are never authoritative customer payment amounts.
    """
    from payments.retail_pricing import order_quote
    from payments.live_models import LiveAgreement, default_price_policy
    source = request.data
    monthly = source.get('source_monthly_cents')
    setup = source.get('source_setup_cents')
    if type(monthly) is not int or type(setup) is not int:
        return JsonResponse({'error': 'Enter supplier monthly and setup amounts as whole cents.'}, status=400)
    if monthly < 0 or monthly > 1000000 or setup < 0 or setup > 1000000:
        return JsonResponse({'error': 'Supplier amounts are outside the valid range.'}, status=400)
    record_id = source.get('agreement_id', 'new')
    if record_id == 'new':
        policy = default_price_policy()
    else:
        try:
            identifier = uuid.UUID(str(record_id))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Agreement reference invalid.'}, status=400)
        agreement = LiveAgreement.objects.filter(pk=identifier).first()
        if agreement is None or agreement.checkout_started_at is not None:
            return JsonResponse({'error': 'Agreement unavailable or prices locked after checkout.'}, status=409)
        policy = agreement.pricing_policy
    if policy not in ('legacy_v1', 'all_in_v2', 'all_in_v3'):
        return JsonResponse({'error': 'Pricing policy unavailable.'}, status=409)
    q = order_quote(monthly, setup, include_processing=policy in ('all_in_v2','all_in_v3'),
        monthly_price_increase_cents=400 if policy == 'all_in_v3' else 0)
    return JsonResponse({
        'monthly_cents': q['monthly_cents'], 'setup_cents': q['setup_cents'],
        'first_invoice_cents': q['first_invoice_cents'], 'currency': 'NZD',
        'gst_included': True, 'pricing_policy': policy, 'saved': False,
        'approved': False, 'checkout_created': False, 'supplier_order_created': False,
    })


@endpoint(['GET'])
@private
def index(request):
    return JsonResponse({'collections':[{'name':key,'label':key.replace('-',' ').capitalize(),
        'create':value['create'],'readonly':value['readonly']} for key,value in SPECS.items()],
        'live_payments':live_gateway.configured(),
        'public_prices':settings.BROADBAND_CATALOGUE_ENABLED,'supplier_orders':False})


@endpoint(['GET','POST'])
@private
def collection(request,kind):
    if kind not in SPECS:return JsonResponse({'error':'Not found'},status=404)
    if request.method=='POST':return save(request,kind,'new')
    query=records(kind)
    term=request.GET.get('q','').strip()[:100]
    if term and SPECS[kind]['search']:
        clause=Q()
        for field in SPECS[kind]['search']:clause|=Q(**{field+'__icontains':term})
        query=query.filter(clause)
    if request.GET.get('customer') and kind in ('requests','tickets','privacy','invoices'):
        query=query.filter(user_id=int(request.GET['customer']))
    page=max(1,min(10000,int(request.GET.get('page','1'))));start=(page-1)*30
    return JsonResponse({'kind':kind,'columns':SPECS[kind]['display'],'total':query.count(),'page':page,
        'rows':[{'id':str(obj.pk),**{key:data_value(getattr(obj,key)) for key in SPECS[kind]['display']}}
            for obj in query.order_by('-pk')[start:start+30]],'create':SPECS[kind]['create']})


@endpoint(['GET','POST'])
@private
def record(request,kind,pk):
    if kind not in SPECS:return JsonResponse({'error':'Not found'},status=404)
    if request.method=='POST':return save(request,kind,pk)
    if pk=='new':
        if not SPECS[kind]['create']:return JsonResponse({'error':'Creation disabled'},status=405)
        obj=SPECS[kind]['model']()
        if hasattr(obj,'created_by_id'):obj.created_by=request.user
        if hasattr(obj,'checked_by_id'):obj.checked_by=request.user
    else:obj=get_object_or_404(records(kind),pk=pk)
    return JsonResponse(detail(kind,obj))


def save(request,kind,pk):
    if pk=='new' and not SPECS[kind]['create']:return JsonResponse({'error':'Creation disabled'},status=405)
    with transaction.atomic():
        obj=SPECS[kind]['model']() if pk=='new' else get_object_or_404(records(kind).select_for_update(),pk=pk)
        if hasattr(obj,'created_by_id') and pk=='new':obj.created_by=request.user
        if hasattr(obj,'checked_by_id'):obj.checked_by=request.user
        if not editable(kind,obj):return JsonResponse({'error':'This record is read-only'},status=409)
        if pk!='new' and not current_version(kind,obj,request.data.get('version')):
            return JsonResponse({'error':'This record changed or the edit expired. Reload before saving.'},status=409)
        values=request.data.get('values')
        if not isinstance(values,dict):raise ValueError('Fields must be an object')
        allowed=set(SPECS[kind]['fields'])|({'expected_updated_at','confirm_current_approval'} if kind=='catalogue' else {'confirm_live_offer'} if kind=='payment-agreements' else set())
        if set(values)-allowed:raise ValueError('Protected or unknown fields cannot be changed')
        if kind=='requests' and values.get('status')=='cancelled' and hasattr(obj,'broadband'):
            agreement_id=obj.broadband.payment_agreement_id
            if agreement_id and LiveAgreement.objects.filter(pk=agreement_id,checkout_started_at__isnull=False).exists():
                return JsonResponse({'error':'Payment has started. Review the customer payment and cancellation terms before cancelling the service.'},status=409)
        if kind=='privacy' and values.get('status')=='completed' and request.data.get('confirm_completed') is not True:
            raise ValueError('Confirm that manual fulfilment and lawful retention review are complete. This only records review status; it does not delete data.')
        form=form_for(kind,obj,values)
        if not form.is_valid():return JsonResponse({'error':'Review the highlighted fields','fields':form.errors.get_json_data()},status=400)
        obj=form.save(commit=False)
        if kind=='catalogue':
            obj.approved_by=request.user if obj.review_status=='approved' else None
            obj.approved_at=timezone.now() if obj.review_status=='approved' else None
        if kind=='test-agreements' and pk!='new':obj.terms_version=uuid.uuid4()
        if kind=='payment-agreements':
            if pk!='new':obj.terms_version=uuid.uuid4()
            obj.approved_by=request.user if obj.reviewed else None
            obj.approved_at=timezone.now() if obj.reviewed else None
        if kind in ('preparation','faults') and pk!='new':obj.revision+=1
        obj.full_clean();obj.save()
        AuditEvent.objects.create(actor=request.user,action='owner_'+kind.replace('-','_')+'_saved',reference=str(obj.pk))
        return JsonResponse({'message':'Private record saved. Sales, publication and supplier ordering remain unchanged.',**detail(kind,obj)})


@endpoint(['POST'])
@private
def reply(request,pk):
    ticket=get_object_or_404(Ticket,pk=pk)
    key=uuid.UUID(text(request.data,'submission_key',36,36));body=text(request.data,'body',4000)
    with transaction.atomic():
        prior,created=Message.objects.get_or_create(submission_key=key,
            defaults={'ticket':ticket,'author':request.user,'body':body})
        if prior.ticket_id!=ticket.pk or prior.author_id!=request.user.pk or prior.body!=body:
            return JsonResponse({'error':'Submission key conflict'},status=409)
        if created:
            AuditEvent.objects.create(actor=request.user,action='support_reply',reference=str(ticket.pk))
    return JsonResponse({'message':'Reply recorded.'})


@endpoint(['POST'])
@private
def case_transition(request,kind,pk):
    if kind not in ('preparation','faults'):return JsonResponse({'error':'Not found'},status=404)
    obj=transition(request,SPECS[kind]['model'],pk,target=text(request.data,'target',30),
        revision=int(request.data['revision']),submission_key=request.data['submission_key'],
        reference=text(request.data,'reference',160,0),note=text(request.data,'note',2000))
    return JsonResponse({'message':'Preparation updated. No supplier call was made.',**detail(kind,obj)})
