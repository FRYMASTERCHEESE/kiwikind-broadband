import json
import re
import uuid
import logging
from smtplib import SMTPException
from functools import wraps
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.mail import send_mail, get_connection
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.http import JsonResponse, FileResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest, ReferralCode, Referral, AccountPreferences
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
                    try:
                        request.data = json.loads(request.body or b'{}')
                    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
                        return JsonResponse({'error':'Invalid JSON request'},status=400)
                    if not isinstance(request.data,dict): raise ValueError('Expected a JSON object')
                return fn(request,*args,**kwargs)
            except (ValueError, TypeError, ValidationError, KeyError) as e:
                return JsonResponse({'error':'; '.join(e.messages) if isinstance(e,ValidationError) else str(e)},status=400)
        return call
    return decorate

def text(data,key,maximum,minimum=1):
    value=data.get(key,'')
    if not isinstance(value,str) or not minimum <= len(value.strip()) <= maximum: raise ValueError(f'{key}: use {minimum}–{maximum} characters')
    # PostgreSQL cannot store NUL or unpaired UTF-16 surrogates. Reject them
    # before database/identity/mail calls, consistently on both database engines.
    if '\x00' in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f'{key}: use valid text without null characters')
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
def readiness_script(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'readiness.js','rb'),content_type='application/javascript')

@require_GET
def privacy_policy(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'privacy.html','rb'),content_type='text/html')

@require_GET
def account_deletion_info(request): return FileResponse(open(settings.BASE_DIR/'site'/'dist'/'account-deletion.html','rb'),content_type='text/html')

@require_GET
def health(request): return JsonResponse({'status':'ok','service':'kiwikind-broadband'})

@endpoint(['GET'])
def status(request):
    return JsonResponse({'mode':'prelaunch','intake_enabled':settings.INTAKE_ENABLED,'live_services':False,
      'availability':'unverified','billing_enabled':False,'legal_entity':settings.LEGAL_ENTITY,
      'business_contact':settings.BUSINESS_CONTACT,'privacy_contact':settings.PRIVACY_CONTACT,'consent_version':CONSENT})

@endpoint(['GET'])
def csrf(request): return JsonResponse({'csrfToken':get_token(request)})

def account_json(user):
    return {'email':user.email, 'service_status':'No active service', 'has_password':user.has_usable_password()}

@endpoint(['GET'])
def bootstrap(request):
    return JsonResponse({'csrfToken':get_token(request), 'intake_enabled':settings.INTAKE_ENABLED,
        'billing_enabled':False, 'live_services':False,
        'account':account_json(request.user) if request.user.is_authenticated else None})

def attach_referral(user, code):
    if not code: return
    if not settings.REFERRALS_ENABLED: raise ValueError('Referral registration is not open yet')
    owner = ReferralCode.objects.select_related('user').filter(code=code, user__is_active=True).first()
    if not owner or owner.user_id == user.pk: raise ValueError('Invalid referral code')
    Referral.objects.create(referrer=owner.user, invitee=user)

@endpoint(['POST'],throttle='register',intake=True)
def register(request):
    email=text(request.data,'email',254).lower(); validate_email(email)
    password=text(request.data,'password',128,12)
    referral=text(request.data,'referral_code',24,0)
    # Validate equally for existing and new addresses; invalid codes must not
    # turn the generic registration response into an account-existence probe.
    if referral:
        if not settings.REFERRALS_ENABLED: raise ValueError('Referral registration is not open yet')
        if not ReferralCode.objects.filter(code=referral,user__is_active=True).exists(): raise ValueError('Invalid referral code')
    if request.data.get('consent_version') != CONSENT: raise ValueError('Accept current pre-launch privacy and terms')
    validate_password(password,User(username=email,email=email))
    # Generic response avoids disclosing registered addresses.
    if not User.objects.filter(username=email).exists():
        try:
            with transaction.atomic():
                user=User.objects.create_user(username=email,email=email,password=password,is_active=False)
                attach_referral(user,referral)
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
    if user.is_active: raise ValueError('This verification link has already been used')
    user.is_active=True; user.save(update_fields=['is_active'])
    Referral.objects.filter(invitee=user,status='pending').update(status='verified')
    return JsonResponse({'message':'Email verified. You can sign in.'})

@endpoint(['POST'],throttle='login')
def signin(request):
    user=authenticate(request,username=text(request.data,'email',254).lower(),password=text(request.data,'password',128))
    if user is None: return JsonResponse({'error':'Invalid credentials or email not verified'},status=401)
    login(request,user); audit(request,'login')
    return JsonResponse({**account_json(user),'csrfToken':get_token(request),'intake_enabled':settings.INTAKE_ENABLED})

@endpoint(['POST'],True)
def signout(request): audit(request,'logout'); logout(request); return JsonResponse({'message':'Signed out'})

@endpoint(['POST'],throttle='reset')
def reset_start(request):
    email=text(request.data,'email',254).lower(); validate_email(email)
    unavailable = {'error':'Password reset email is temporarily unavailable. Try again later or use Google sign-in if already linked to your account.'}
    # Check transport before account lookup: outages must not identify registered addresses.
    if settings.RESET_EMAIL_UNAVAILABLE:
        return JsonResponse(unavailable, status=503)
    try:
        connection = get_connection()
        connection.open()
    except (OSError, SMTPException, ImproperlyConfigured):
        logging.getLogger(__name__).warning('Password reset mail transport unavailable')
        return JsonResponse(unavailable, status=503)
    try:
        user=User.objects.filter(username=email,is_active=True).first()
        if user:
            token=default_token_generator.make_token(user)
            payload=signing.dumps({'id':user.pk,'token':token},salt='reset')
            try:
                sent=send_mail('Reset your KiwiKind password',f'{settings.PUBLIC_ORIGIN}/#reset={payload}',settings.DEFAULT_FROM_EMAIL,[email],connection=connection)
                if sent != 1: logging.getLogger(__name__).warning('Password reset email not accepted')
            except (OSError, SMTPException, ImproperlyConfigured):
                # Recipient-specific failures cannot produce a different public response.
                logging.getLogger(__name__).warning('Password reset email not accepted')
    finally:
        try: connection.close()
        except (OSError, SMTPException): pass
    return JsonResponse({'message':'If the account is eligible, a reset email has been requested. Check your inbox and spam. If it does not arrive, try again later or use your linked Google sign-in.'},status=202)

@endpoint(['POST'],throttle='reset-confirm')
def reset_confirm(request):
    try: payload=signing.loads(text(request.data,'token',1000),salt='reset',max_age=3600)
    except signing.BadSignature: raise ValueError('Invalid or expired reset link')
    with transaction.atomic():
        user=get_object_or_404(User.objects.select_for_update(),pk=payload['id'])
        if not default_token_generator.check_token(user,payload['token']): raise ValueError('Invalid or used reset link')
        password=text(request.data,'password',128,12); validate_password(password,user)
        user.set_password(password); user.save(update_fields=['password'])
    return JsonResponse({'message':'Password updated. Sign in again.'})

@endpoint(['GET'],True)
def me(request): return JsonResponse(account_json(request.user))

@endpoint(['GET','POST'],True,throttle='referrals')
def referrals(request):
    code = ReferralCode.objects.filter(user=request.user).first()
    if request.method == 'POST':
        code,_ = ReferralCode.objects.get_or_create(user=request.user)
    return JsonResponse({'code':code.code if code else None,
        'share_url':f'{settings.PUBLIC_ORIGIN}/?ref={code.code}#signup' if code else None,
        'accepting_referrals':settings.REFERRALS_ENABLED and settings.INTAKE_ENABLED,
        'rewards_enabled':False,
        'history':list(Referral.objects.filter(referrer=request.user).order_by('-created_at').values('id','status','created_at')[:100])})

@endpoint(['GET','POST'],True)
def preferences(request):
    pref = AccountPreferences.objects.filter(user=request.user).first()
    if request.method == 'POST':
        value=request.data.get('account_notifications')
        if type(value) is not bool: raise ValueError('Choose a notification preference')
        pref,_=AccountPreferences.objects.update_or_create(user=request.user,defaults={'account_notifications':value})
    return JsonResponse({'account_notifications':pref.account_notifications if pref else False,
        'delivery_enabled':False,'marketing_enabled':False})

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
    if category not in ['support','complaint','privacy']: raise ValueError('Choose support, complaint or privacy')
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
    return JsonResponse({'billing_enabled':False,'invoices':list(Invoice.objects.filter(user=request.user).values('id','amount_cents','currency','due_date','status'))})

@endpoint(['GET'],True)
def export(request):
    audit(request,'privacy_export')
    ts=Ticket.objects.filter(user=request.user)
    response=JsonResponse({'email':request.user.email,'orders':[order_json(o) for o in Order.objects.filter(user=request.user)],
      'tickets':[{'id':str(t.id),'subject':t.subject,'category':t.category,'status':t.status,'messages':list(t.messages.values('body','created_at'))} for t in ts],
      'invoices':list(Invoice.objects.filter(user=request.user).values('id','supplier_reference','amount_cents','currency','due_date','status')),
      'privacy_requests':list(PrivacyRequest.objects.filter(user=request.user).values('status','created_at'))})
    # Never include invited people's addresses or identity details in this export.
    data=json.loads(response.content)
    data['referrals']=list(Referral.objects.filter(referrer=request.user).values('id','status','created_at'))
    data['account_preferences']={'account_notifications':AccountPreferences.objects.filter(user=request.user,account_notifications=True).exists()}
    response=JsonResponse(data)
    response['Content-Disposition']='attachment; filename="kiwikind-data.json"'
    return response

@endpoint(['POST'],True)
def deletion(request):
    if request.user.has_usable_password():
        if not request.user.check_password(text(request.data,'password',128)): return JsonResponse({'error':'Confirm your current password'},status=403)
    elif request.data.get('confirm') is not True:
        return JsonResponse({'error':'Confirm the deletion review request'},status=403)
    if limited(request,'deletion'): return JsonResponse({'error':'Try later'},status=429)
    with transaction.atomic():
        # Lock the parent even when no queue item exists yet.
        User.objects.select_for_update().get(pk=request.user.pk)
        existing=PrivacyRequest.objects.filter(user=request.user).exclude(status='completed').first()
        if not existing: existing=PrivacyRequest.objects.create(user=request.user)
        audit(request,'deletion_requested',existing.pk)
    return JsonResponse({'message':'Deletion request received for review, including any lawful retention requirements.'},status=202)


def _verified_google_signin(request, token):
    """Server-side verified Google ID token. Never trust client-supplied emails."""
    import os
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    client_id = os.getenv('GOOGLE_WEB_CLIENT_ID', '').strip()
    if not client_id:
        return JsonResponse({'error': 'Google sign-in is not configured yet'}, status=503)
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except Exception:
        return JsonResponse({'error': 'Google identity could not be verified'}, status=401)
    if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com') or claims.get('email_verified') is not True:
        return JsonResponse({'error': 'A verified Google email is required'}, status=401)
    email = str(claims.get('email', '')).strip().lower()
    subject = str(claims.get('sub', '')).strip()
    if not email or not subject:
        return JsonResponse({'error': 'Invalid Google account'}, status=401)
    from .models import GoogleIdentity
    try:
        with transaction.atomic():
            identity = GoogleIdentity.objects.select_related('user').filter(subject=subject).first()
            if identity:
                user = identity.user
            else:
                # Existing password identities are NEVER automatically linked by email.
                if User.objects.filter(username=email).exists():
                    return JsonResponse({'error': 'This email already has an account. Sign in with your password first to link Google.'}, status=409)
                if not settings.INTAKE_ENABLED:
                    return JsonResponse({'error':'New account registration is closed during prelaunch. Existing linked Google accounts can still sign in.'},status=503)
                user = User.objects.create_user(username=email, email=email, password=None, is_active=True)
                GoogleIdentity.objects.create(user=user, subject=subject)
    except IntegrityError:
        # A concurrent first login may have committed the same verified subject.
        # Recover outside the rolled-back transaction; never link by email.
        identity = GoogleIdentity.objects.select_related('user').filter(subject=subject).first()
        if not identity:
            return JsonResponse({'error': 'Account changed during sign-in. Try again or sign in with your password.'}, status=409)
        user = identity.user
    if not user.is_active:
        return JsonResponse({'error': 'Account unavailable'}, status=403)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    audit(request, 'google_login')
    return JsonResponse({**account_json(user), 'csrfToken': get_token(request),'intake_enabled':settings.INTAKE_ENABLED})


@endpoint(['POST'], throttle='google-login')
def google_signin(request):
    return _verified_google_signin(request, text(request.data, 'id_token', 8192, 20))


@csrf_exempt
def google_callback(request):
    """Google Identity Services redirect flow for mobile/in-app browsers.
    Google posts the credential directly, with double-submit CSRF protection.
    """
    if request.method != 'POST':
        return HttpResponseRedirect('/#portal')
    if limited(request, 'google-login'):
        return JsonResponse({'error': 'Too many attempts'}, status=429)
    csrf_cookie = request.COOKIES.get('g_csrf_token', '')
    csrf_form = request.POST.get('g_csrf_token', '')
    if not csrf_cookie or not csrf_form or csrf_cookie != csrf_form:
        return JsonResponse({'error': 'Invalid Google login request'}, status=403)
    credential = request.POST.get('credential', '')
    if not 20 <= len(credential) <= 8192:
        return JsonResponse({'error': 'Invalid Google credential'}, status=400)
    response = _verified_google_signin(request, credential)
    if response.status_code == 200:
        return HttpResponseRedirect('/#portal')
    return response


@endpoint(['POST'], True, throttle='google-link')
def google_link(request):
    """Link a Google identity only after an existing password/session login."""
    import os
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    client_id = os.getenv('GOOGLE_WEB_CLIENT_ID', '').strip()
    if not client_id:
        return JsonResponse({'error': 'Google sign-in is not configured yet'}, status=503)
    token = text(request.data, 'id_token', 8192, 20)
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except Exception:
        return JsonResponse({'error': 'Google identity could not be verified'}, status=401)
    if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com') or claims.get('email_verified') is not True:
        return JsonResponse({'error': 'A verified Google email is required'}, status=401)
    email = str(claims.get('email', '')).strip().lower()
    subject = str(claims.get('sub', '')).strip()
    if not subject or not email or email != request.user.email.strip().lower():
        return JsonResponse({'error': 'Use the verified Google account matching your signed-in email'}, status=403)
    from .models import GoogleIdentity
    with transaction.atomic():
        existing = GoogleIdentity.objects.select_for_update().filter(subject=subject).first()
        if existing and existing.user_id != request.user.pk:
            return JsonResponse({'error': 'Google account is already linked to another user'}, status=409)
        if not existing:
            if GoogleIdentity.objects.filter(user=request.user).exists():
                return JsonResponse({'error': 'This account already has a different Google identity linked'}, status=409)
            GoogleIdentity.objects.create(user=request.user, subject=subject)
    audit(request, 'google_link')
    return JsonResponse({'message': 'Google account linked. You can now sign in with Google.'})
