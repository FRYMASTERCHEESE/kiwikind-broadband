import json
import re
import uuid
from functools import wraps
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.http import JsonResponse, FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest
from .security import limited

User = get_user_model()
CONSENT = 'prelaunch-2026-10-16'

def endpoint(methods, authenticated=False, throttle=None, intake=False):
    def decorate(fn):
        @wraps(fn)
        def call(request, *args, **kwargs):
            if request.method not in methods: return JsonResponse({'error':'Method not allowed'},status=405)
            if authenticated and not request.user.is_authenticated: return JsonResponse({'error':'Sign in first'},status=401)
            if intake and not settings.INTAKE_ENABLED: return JsonResponse({'error':'Customer intake is not open yet'},status=503)
            if throttle and limited(request,throttle): return JsonResponse({'error':'Too many attempts. Try again in 15 minutes.'},status=429)
            try:
                if request.method == 'POST':
                    if len(request.body)>16000: return JsonResponse({'error':'Request too large'},status=413)
                    request.data = json.loads(request.body or b'{}')
                    if not isinstance(request.data,dict): raise ValueError('Expected a JSON object')
                return fn(request,*args,**kwargs)
            except (ValueError, TypeError, ValidationError, KeyError) as e:
                return JsonResponse({'error':'; '.join(e.messages) if isinstance(e,ValidationError) else str(e)},status=400)
        return call
    return decorate

def text(data,key,maximum,minimum=1):
    value=data.get(key,'')
    if not isinstance(value,str) or not minimum <= len(value.strip()) <= maximum: raise ValueError(f'{key}: use {minimum}–{maximum} characters')
    return value.strip()

def audit(request,action,reference=''):
    AuditEvent.objects.create(actor=request.user if request.user.is_authenticated else None,action=action,reference=str(reference))

@require_GET
def home(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'index.html','rb'),content_type='text/html')

@require_GET
def styles(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'styles.css','rb'),content_type='text/css')

@require_GET
def script(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'app.js','rb'),content_type='application/javascript')

@require_GET
def health(request): return JsonResponse({'status':'ok','service':'kiwikind-broadband'})

@endpoint(['GET'])
def status(request):
    return JsonResponse({'mode':'prelaunch','intake_enabled':settings.INTAKE_ENABLED,'live_services':False,
      'availability':'unverified','billing_enabled':False,'legal_entity':settings.LEGAL_ENTITY,
      'business_contact':settings.BUSINESS_CONTACT,'privacy_contact':settings.PRIVACY_CONTACT,'consent_version':CONSENT})

@endpoint(['GET'])
def csrf(request): return JsonResponse({'csrfToken':get_token(request)})

@endpoint(['POST'],throttle='register',intake=True)
def register(request):
    email=text(request.data,'email',254).lower(); validate_email(email)
    password=text(request.data,'password',128,12)
    if request.data.get('consent_version') != CONSENT: raise ValueError('Accept current pre-launch privacy and terms')
    validate_password(password,User(username=email,email=email))
    # Generic response avoids disclosing registered addresses.
    if not User.objects.filter(username=email).exists():
        try:
            with transaction.atomic():
                user=User.objects.create_user(username=email,email=email,password=password,is_active=False)
                token=signing.dumps({'id':user.pk},salt='verify')
                url=f'{settings.PUBLIC_ORIGIN}/#verify={token}'
                send_mail('Verify your KiwiKind Broadband account',f'Confirm your email within 24 hours: {url}\nThis does not order broadband.',settings.DEFAULT_FROM_EMAIL,[email])
        except IntegrityError: pass
    return JsonResponse({'message':'If eligible, a verification email has been sent.'},status=202)

@endpoint(['POST'],throttle='verify')
def verify(request):
    try: payload=signing.loads(text(request.data,'token',1000),salt='verify',max_age=86400)
    except signing.BadSignature: raise ValueError('Invalid or expired verification link')
    user=get_object_or_404(User,pk=payload['id'])
    if payload.get('email',user.email) != user.email: raise ValueError('Email changed; request a fresh verification')
    if user.is_active and not payload.get('owner_verification'): raise ValueError('This verification link has already been used')
    from .models import EmailVerification
    if payload.get('owner_verification') and EmailVerification.objects.filter(user=user,email=user.email).exists():
        raise ValueError('This verification link has already been used')
    user.is_active=True; user.save(update_fields=['is_active'])
    EmailVerification.objects.update_or_create(user=user, defaults={'email':user.email})
    return JsonResponse({'message':'Email verified. You can sign in.'})

@endpoint(['POST'],throttle='login')
def signin(request):
    user=authenticate(request,username=text(request.data,'email',254).lower(),password=text(request.data,'password',128))
    if user is None: return JsonResponse({'error':'Invalid credentials or email not verified'},status=401)
    login(request,user); audit(request,'login')
    return JsonResponse({'email':user.email,'csrfToken':get_token(request)})

@endpoint(['POST'],True)
def signout(request): audit(request,'logout'); logout(request); return JsonResponse({'message':'Signed out'})

@endpoint(['POST'],throttle='reset')
def reset_start(request):
    email=text(request.data,'email',254).lower(); validate_email(email)
    user=User.objects.filter(username=email,is_active=True).first()
    if user:
        token=default_token_generator.make_token(user)
        payload=signing.dumps({'id':user.pk,'token':token},salt='reset')
        send_mail('Reset your KiwiKind password',f'{settings.PUBLIC_ORIGIN}/#reset={payload}',settings.DEFAULT_FROM_EMAIL,[email])
    return JsonResponse({'message':'If the account exists, a reset email has been sent.'},status=202)

@endpoint(['POST'],throttle='reset-confirm')
def reset_confirm(request):
    try: payload=signing.loads(text(request.data,'token',1000),salt='reset',max_age=3600)
    except signing.BadSignature: raise ValueError('Invalid or expired reset link')
    user=get_object_or_404(User,pk=payload['id'])
    if not default_token_generator.check_token(user,payload['token']): raise ValueError('Invalid or used reset link')
    password=text(request.data,'password',128,12); validate_password(password,user)
    user.set_password(password); user.save(update_fields=['password'])
    return JsonResponse({'message':'Password updated. Sign in again.'})

@endpoint(['GET'],True)
def me(request): return JsonResponse({'email':request.user.email,'service_status':'No active service'})

def order_json(o): return {'id':str(o.id),'address':o.address,'postcode':o.postcode,'contact_name':o.contact_name,'phone':o.phone,'status':o.status,'created_at':o.created_at.isoformat(),'consent_version':o.consent_version}

@endpoint(['GET','POST'],True)
def orders(request):
    if request.method=='GET': return JsonResponse({'orders':[order_json(o) for o in Order.objects.filter(user=request.user).order_by('-created_at')[:100]]})
    if not settings.INTAKE_ENABLED: return JsonResponse({'error':'Requests are closed'},status=503)
    if limited(request,'orders',20,3600): return JsonResponse({'error':'Request limit reached'},status=429)
    d=request.data
    if d.get('consent_version')!=CONSENT: raise ValueError('Accept current pre-launch request terms')
    postcode=text(d,'postcode',4,4)
    if not re.fullmatch(r'\d{4}',postcode): raise ValueError('Use a four-digit NZ postcode')
    phone=text(d,'phone',25,0)
    if phone and not re.fullmatch(r'[+\d ()-]{6,25}',phone): raise ValueError('Invalid contact phone')
    key=uuid.UUID(text(d,'idempotency_key',36,36))
    defaults={'address':text(d,'address',300,8),'postcode':postcode,'contact_name':text(d,'contact_name',100),'phone':phone,'consent_version':CONSENT}
    with transaction.atomic():
        o,created=Order.objects.get_or_create(user=request.user,idempotency_key=key,defaults=defaults)
        if not created and any(getattr(o,k)!=v for k,v in defaults.items()): return JsonResponse({'error':'Idempotency key already used for a different request'},status=409)
        if created: audit(request,'order_requested',o.id)
    return JsonResponse({'order':order_json(o),'message':'Request recorded. Availability, price and installation are not confirmed. No charge or supplier order.'},status=201 if created else 200)

@endpoint(['POST'],True)
def cancel_order(request,pk):
    with transaction.atomic():
        o=get_object_or_404(Order,user=request.user,pk=pk)
        o.status='cancelled'; o.save(update_fields=['status']); audit(request,'order_cancelled',o.id)
    return JsonResponse({'order':order_json(o)})

@endpoint(['GET','POST'],True)
def tickets(request):
    if request.method=='GET':
        return JsonResponse({'tickets':list(Ticket.objects.filter(user=request.user).order_by('-created_at').values('id','subject','category','status','created_at')[:100])})
    if limited(request,'tickets',30,3600): return JsonResponse({'error':'Ticket limit reached'},status=429)
    category=text(request.data,'category',20)
    if category not in ['support','fault','complaint','privacy']: raise ValueError('Choose support, fault, complaint or privacy')
    with transaction.atomic():
        ticket=Ticket.objects.create(user=request.user,subject=text(request.data,'subject',150),category=category)
        Message.objects.create(ticket=ticket,author=request.user,body=text(request.data,'body',4000))
        audit(request,'ticket_created',ticket.id)
    return JsonResponse({'id':str(ticket.id),'message':'Recorded. No response time is promised during pre-launch.'},status=201)

@endpoint(['GET','POST'],True)
def messages(request,pk):
    ticket=get_object_or_404(Ticket,pk=pk,user=request.user)
    if request.method=='POST':
        if limited(request,'messages',60,3600): return JsonResponse({'error':'Message limit reached'},status=429)
        Message.objects.create(ticket=ticket,author=request.user,body=text(request.data,'body',4000)); audit(request,'ticket_message',ticket.id)
    return JsonResponse({'messages':[{'body':m.body,'from_support':m.author_id!=request.user.pk,'created_at':m.created_at.isoformat()} for m in ticket.messages.order_by('created_at')[:200]]})

@endpoint(['GET'],True)
def invoices(request):
    from .stripe_staging import configured
    rows=[]
    for invoice in Invoice.objects.filter(user=request.user):
        payment=getattr(invoice,'stripepayment',None)
        rows.append({'id':str(invoice.id),'amount_cents':invoice.amount_cents,'currency':invoice.currency,
            'due_date':invoice.due_date,'status':invoice.status,'sandbox':invoice.sandbox,
            'refunded_cents':payment.refunded_cents if payment else 0})
    return JsonResponse({'billing_enabled':False,'stripe_test_checkout_enabled':configured(),'invoices':rows})

@endpoint(['GET'],True)
def export(request):
    audit(request,'privacy_export')
    ts=Ticket.objects.filter(user=request.user)
    response=JsonResponse({'email':request.user.email,'orders':[order_json(o) for o in Order.objects.filter(user=request.user)],
      'tickets':[{'id':str(t.id),'subject':t.subject,'category':t.category,'status':t.status,'messages':list(t.messages.values('body','created_at'))} for t in ts],
      'invoices':list(Invoice.objects.filter(user=request.user).values('id','supplier_reference','amount_cents','currency','due_date','status')),
      'privacy_requests':list(PrivacyRequest.objects.filter(user=request.user).values('status','created_at'))})
    response['Content-Disposition']='attachment; filename="kiwikind-data.json"'
    return response

@endpoint(['POST'],True)
def deletion(request):
    if not request.user.check_password(text(request.data,'password',128)): return JsonResponse({'error':'Confirm your current password'},status=403)
    if limited(request,'deletion'): return JsonResponse({'error':'Try later'},status=429)
    with transaction.atomic():
        existing=PrivacyRequest.objects.filter(user=request.user).exclude(status='completed').first()
        if not existing: existing=PrivacyRequest.objects.create(user=request.user)
        audit(request,'deletion_requested',existing.pk)
    return JsonResponse({'message':'Deletion request received for review, including any lawful retention requirements.'},status=202)
