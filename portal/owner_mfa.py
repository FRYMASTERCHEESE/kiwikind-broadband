"""Owner-only authenticator setup and challenge; no password or email bypass."""
from base64 import b32encode

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import AuditEvent
from .owner_admin import enabled, owner_identity_session, owner_session
from .security import limited


@never_cache
@sensitive_post_parameters('code')
@sensitive_variables('device', 'setup_key')
@require_http_methods(['GET', 'POST'])
def challenge(request):
    if not enabled():
        return HttpResponse(status=404)
    if not owner_identity_session(request):
        return redirect('/admin/login/')
    if owner_session(request):
        return redirect('/admin/')
    error = ''
    if request.method == 'POST' and limited(request, 'owner-mfa', limit=10):
        return HttpResponse('Too many attempts. Try again later.', status=429)
    with transaction.atomic():
        # One device per owner, including simultaneous first setup requests.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        device = TOTPDevice.objects.select_for_update().filter(user=request.user, confirmed=True).first()
        if device is None:
            device, _ = TOTPDevice.objects.get_or_create(
                user=request.user, name='Owner authenticator', confirmed=False)
        if request.method == 'POST':
            code = request.POST.get('code', '')
            if len(code) == 6 and code.isascii() and code.isdigit() and device.verify_token(code):
                enrolling = not device.confirmed
                device.confirmed = True
                device.save(update_fields=['confirmed'])
                request.session.cycle_key()
                otp_login(request, device)
                AuditEvent.objects.create(actor=request.user,
                    action='owner_mfa_enrolled' if enrolling else 'owner_mfa_verified', reference='admin')
                return redirect('/admin/')
            error = 'Code not accepted. Wait for a new code and try again.'
        # Never display an enrolled key, and never send it to an external QR service.
        setup_key = b32encode(device.bin_key).decode('ascii') if not device.confirmed else ''
    return render(request, 'admin/owner_mfa.html', {
        **admin.site.each_context(request),
        'title': 'Set up your authenticator' if setup_key else 'Authenticator verification',
        'setup_key': setup_key, 'error': error,
    })
