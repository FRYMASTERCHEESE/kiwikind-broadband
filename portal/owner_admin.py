"""Dedicated owner administration, independent of customer account sign-in."""
import hashlib
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from .models import AuditEvent, OwnerAdminChallenge
from .security import limited

OWNER_EMAIL = 'kiwikindbroadband@gmail.com'
OWNER_USERNAME = 'kiwikind-owner-admin'
PROOF_SECONDS = 1800


def enabled():
    return settings.ADMIN_ENABLED and settings.OWNER_GOOGLE_ADMIN_ENABLED


def owner_session(request):
    verified = request.session.get('owner_admin_verified_at', 0)
    return (request.user.username == OWNER_USERNAME
            and isinstance(verified, (int, float))
            and 0 <= time.time() - verified < PROOF_SECONDS)


@never_cache
def owner_login(request, extra_context=None):
    if not enabled():
        return HttpResponse(status=404)
    if admin.site.has_permission(request):
        return HttpResponseRedirect('/admin/')
    if request.method != 'GET':
        return HttpResponse(status=405)
    if not settings.GOOGLE_WEB_CLIENT_ID:
        return HttpResponse('Owner Google sign-in is unavailable.', status=503)
    if limited(request, 'owner-admin-page', limit=40):
        return HttpResponse('Too many sign-in page requests. Try again later.', status=429)
    nonce = secrets.token_urlsafe(32)
    now = timezone.now()
    OwnerAdminChallenge.objects.filter(expires_at__lt=now).delete()
    OwnerAdminChallenge.objects.create(
        digest=hashlib.sha256(nonce.encode()).hexdigest(),
        expires_at=now + timedelta(minutes=5))
    request.session['owner_admin_nonce'] = nonce
    response = render(request, 'admin/owner_login.html', {
        **admin.site.each_context(request), 'title': 'Owner sign-in',
        'client_id': settings.GOOGLE_WEB_CLIENT_ID, 'nonce': nonce,
        'owner_email': OWNER_EMAIL,
        'google_callback': settings.PUBLIC_ORIGIN + '/api/google-callback',
    })
    # A cross-site Google POST does not carry the normal SameSite=Lax session.
    # Bind that callback to a short-lived signed, HttpOnly challenge cookie only.
    response.set_signed_cookie('owner_admin_challenge', nonce, salt='owner-admin-redirect',
                               max_age=300, secure=not settings.DEBUG, httponly=True,
                               samesite='None', path='/api/google-callback')
    return response


@never_cache
@sensitive_post_parameters('credential')
@require_POST
def owner_signin(request):
    return complete_owner_signin(request, request.session.get('owner_admin_nonce', ''))


def owner_redirect_signin(request):
    """Called only after google_callback validates Google's double-submit CSRF."""
    nonce = request.get_signed_cookie('owner_admin_challenge', default='',
                                      salt='owner-admin-redirect', max_age=300)
    response = complete_owner_signin(request, nonce)
    if response.status_code == 200:
        response = HttpResponseRedirect('/admin/')
    response.delete_cookie('owner_admin_challenge', path='/api/google-callback', samesite='None')
    response['Cache-Control'] = 'no-store'
    return response


def complete_owner_signin(request, nonce):
    if not enabled():
        return HttpResponse(status=404)
    if limited(request, 'owner-google-admin', limit=10):
        return JsonResponse({'error': 'Too many attempts. Try again later.'}, status=429)
    credential = request.POST.get('credential', '')
    if not nonce or not 20 <= len(credential) <= 8192:
        return JsonResponse({'error': 'Reload the admin page and try again.'}, status=403)
    try:
        claims = id_token.verify_oauth2_token(
            credential, Request(), settings.GOOGLE_WEB_CLIENT_ID)
    except Exception:
        return JsonResponse({'error': 'Google sign-in could not be verified.'}, status=403)
    issued = claims.get('iat')
    if (claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
            or claims.get('email_verified') is not True
            or str(claims.get('email', '')).casefold() != OWNER_EMAIL
            or not isinstance(claims.get('sub'), str) or not claims['sub']
            or not isinstance(issued, (int, float)) or not 0 <= time.time() - issued <= 300
            or not secrets.compare_digest(str(claims.get('nonce', '')), nonce)):
        return JsonResponse({'error': 'Use the authorised KiwiKind owner Google account.'}, status=403)
    User = get_user_model()
    with transaction.atomic():
        consumed = OwnerAdminChallenge.objects.filter(
            digest=hashlib.sha256(nonce.encode()).hexdigest(),
            expires_at__gt=timezone.now(), used=False).update(used=True)
        if consumed != 1:
            return JsonResponse({'error': 'This sign-in expired. Reload the admin page.'}, status=403)
        # Never elevate or relink an existing customer account by its email.
        user, created = User.objects.get_or_create(username=OWNER_USERNAME, defaults={
            'email': OWNER_EMAIL, 'is_staff': True, 'is_superuser': True,
            'is_active': True, 'password': '!',
        })
        if (not user.is_active or not user.is_staff or not user.is_superuser
                or user.email.casefold() != OWNER_EMAIL or user.has_usable_password()):
            return JsonResponse({'error': 'Owner administration is unavailable.'}, status=403)
        AuditEvent.objects.create(actor=user, action='owner_google_admin_login', reference='admin')
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.pop('owner_admin_nonce', None)
    request.session['owner_admin_verified_at'] = time.time()
    request.session.set_expiry(PROOF_SECONDS)
    return JsonResponse({'redirect': '/admin/'})


@never_cache
def owner_script(request):
    from pathlib import Path
    if not enabled():
        return HttpResponse(status=404)
    return HttpResponse((Path(__file__).parent / 'owner_admin.js').read_text(encoding='utf-8'),
                        content_type='application/javascript')
