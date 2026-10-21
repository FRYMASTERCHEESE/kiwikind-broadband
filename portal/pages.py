"""JSON-only GitHub Pages integration. Uses the existing sessions and owner proof.

No bearer-session alternative, permission shortcut, supplier call or billing write.
"""
import hashlib
import secrets
from base64 import b32encode
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from . import owner_admin
from .catalogue_import import parse_private_quotes, import_private_drafts, QuoteImportError, FIELDS
from .launch_readiness import evidence_snapshot
from .models import AuditEvent, DraftPlan, OwnerAdminChallenge
from .security import limited
from .views import endpoint


@endpoint(['POST'])
def cookie_probe(request):
    # CsrfViewMiddleware must have received the bootstrap cookie before this runs.
    request.session['pages_probe'] = True
    return JsonResponse({'cookies': True})


@endpoint(['GET'])
def session_probe(request):
    return JsonResponse({'session_cookie': request.session.get('pages_probe') is True})


@endpoint(['GET'])
def owner_state(request):
    return JsonResponse({'enabled': owner_admin.enabled(),
        'identity_verified': bool(owner_admin.owner_identity_session(request)),
        'mfa_verified': bool(owner_admin.owner_session(request)),
        'csrfToken': get_token(request)})


@endpoint(['POST'], throttle='owner-pages-challenge')
def owner_challenge(request):
    if not owner_admin.enabled() or not settings.GOOGLE_WEB_CLIENT_ID:
        return JsonResponse({'error': 'Owner sign-in unavailable'}, status=404)
    nonce = secrets.token_urlsafe(32)
    now = timezone.now()
    OwnerAdminChallenge.objects.filter(expires_at__lt=now).delete()
    OwnerAdminChallenge.objects.create(digest=hashlib.sha256(nonce.encode()).hexdigest(),
                                      expires_at=now + timedelta(minutes=5))
    request.session['owner_admin_nonce'] = nonce
    return JsonResponse({'nonce': nonce, 'client_id': settings.GOOGLE_WEB_CLIENT_ID})


@sensitive_post_parameters('credential')
@endpoint(['POST'])
def owner_signin(request):
    # Reuse nonce, issuer/audience/age, pinned subject and dedicated owner checks.
    credential = request.data.get('credential', '')
    if not isinstance(credential, str):
        return JsonResponse({'error': 'Invalid credential'}, status=400)
    request.POST = {'credential': credential}
    response = owner_admin.complete_owner_signin(request, request.session.get('owner_admin_nonce', ''))
    if response.status_code == 200:
        return JsonResponse({'mfa_required': True, 'csrfToken': get_token(request)})
    return response


@sensitive_post_parameters('code')
@sensitive_variables('device', 'setup_key')
@endpoint(['GET', 'POST'])
def owner_mfa(request):
    if not owner_admin.owner_identity_session(request):
        return JsonResponse({'error': 'Owner Google sign-in required'}, status=403)
    if owner_admin.owner_session(request):
        return JsonResponse({'mfa_verified': True, 'csrfToken': get_token(request)})
    if limited(request, 'owner-pages-mfa', limit=20):
        return JsonResponse({'error': 'Try again later'}, status=429)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        device = TOTPDevice.objects.select_for_update().filter(user=request.user, confirmed=True).first()
        if device is None:
            device, _ = TOTPDevice.objects.get_or_create(user=request.user,
                name='Owner authenticator', confirmed=False)
        if request.method == 'POST':
            code = request.data.get('code', '')
            if not (isinstance(code, str) and len(code) == 6 and code.isascii()
                    and code.isdigit() and device.verify_token(code)):
                return JsonResponse({'error': 'Code not accepted. Wait for a new code.'}, status=403)
            enrolling = not device.confirmed
            device.confirmed = True
            device.save(update_fields=['confirmed'])
            request.session.cycle_key()
            otp_login(request, device)
            AuditEvent.objects.create(actor=request.user,
                action='owner_mfa_enrolled' if enrolling else 'owner_mfa_verified', reference='pages')
            return JsonResponse({'mfa_verified': True, 'csrfToken': get_token(request)})
        setup_key = b32encode(device.bin_key).decode('ascii') if not device.confirmed else ''
    return JsonResponse({'enrolling': bool(setup_key), 'setup_key': setup_key})


def private(fn):
    def call(request, *args, **kwargs):
        if not owner_admin.owner_session(request):
            return JsonResponse({'error': 'Owner Google sign-in and MFA required'}, status=403)
        return fn(request, *args, **kwargs)
    return call


@endpoint(['GET'])
@private
def owner_readiness(request):
    # These are stored evidence checks, not a new Stripe provider verification.
    return JsonResponse({**evidence_snapshot(), 'evidence_source': 'stored_test_records',
        'provider_rechecked_now': False})


@endpoint(['POST'], throttle='owner-provider-read', authenticated=True)
@private
def owner_stripe_evidence(request):
    from payments.pages_evidence import verify_owner_evidence
    return JsonResponse(verify_owner_evidence(request.user))


@endpoint(['GET', 'POST'])
@private
def owner_catalogue(request):
    if request.method == 'POST':
        if request.data.get('confirm_draft_only') is not True:
            return JsonResponse({'error': 'Confirm private unverified drafts only'}, status=400)
        raw = request.data.get('csv', '')
        if not isinstance(raw, str):
            return JsonResponse({'error': 'CSV text required'}, status=400)
        try:
            created, existing = import_private_drafts(request.user, parse_private_quotes(raw.encode('utf-8')))
        except QuoteImportError as exc:
            return JsonResponse({'error': str(exc)}, status=exc.status)
        return JsonResponse({'created': created, 'existing': existing,
            'message': 'Private unapproved drafts saved. Nothing published or ordered.'})
    fields = ['id', 'name', 'network', 'download_mbps', 'upload_mbps',
              'wholesale_ex_gst', 'wholesale_inc_gst', 'setup_ex_gst',
              'retail_ex_gst', 'retail_setup_ex_gst', 'review_status',
              'address_specific', 'valid_until', 'source_reference']
    return JsonResponse({'plans': list(DraftPlan.objects.values(*fields)[:200]),
                         'csv_columns': FIELDS, 'publication_allowed': False})
