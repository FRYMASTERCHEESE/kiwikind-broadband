import hashlib
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import AuditEvent, OwnerAdminChallenge
from .owner_admin import OWNER_EMAIL, OWNER_USERNAME
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True,
                   GOOGLE_WEB_CLIENT_ID='test-client.apps.googleusercontent.com')
class OwnerAdminTests(TestCase):
    def challenge(self, client=None):
        client = client or self.client
        client.logout()
        response = client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)
        return client.session['owner_admin_nonce']

    def signin(self, **overrides):
        nonce = self.challenge()
        claims = {'iss': 'https://accounts.google.com', 'email': OWNER_EMAIL,
                  'email_verified': True, 'sub': 'synthetic-owner-subject',
                  'nonce': nonce, 'iat': time.time()}
        claims.update(overrides)
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims) as verify:
            response = self.client.post('/admin/owner-signin/', {'credential': 'synthetic-token-not-real'})
            self.assertEqual(verify.call_args.args[2], 'test-client.apps.googleusercontent.com')
        if response.status_code == 200:
            self.client.get('/admin/mfa/')
            device = TOTPDevice.objects.get()
            # Repeated sign-ins in this synthetic fixture need a fresh time step.
            device.last_t = -1
            device.save(update_fields=['last_t'])
            code = f'{totp(device.bin_key):06d}'
            self.client.post('/admin/mfa/', {'code': code})
        return response, claims

    def test_owner_can_login_without_modifying_customer_account(self):
        User = get_user_model()
        customer = User.objects.create_user(OWNER_EMAIL, OWNER_EMAIL, 'synthetic-password')
        response, _ = self.signin()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(self.client.get('/admin/')['Cross-Origin-Opener-Policy'], 'same-origin')
        owner = User.objects.get(username=OWNER_USERNAME)
        self.assertFalse(owner.has_usable_password())
        customer.refresh_from_db()
        self.assertFalse(customer.is_staff)
        self.assertFalse(customer.is_superuser)
        self.assertTrue(AuditEvent.objects.filter(actor=owner, action='owner_google_admin_login').exists())
        self.assertLessEqual(self.client.session.get_expiry_age(), 1800)

    def test_rejects_other_account_unverified_issuer_nonce_and_stale_token(self):
        for changes in [{'email': 'someone@gmail.com'}, {'email_verified': False},
                        {'iss': 'https://attacker.invalid'}, {'nonce': 'wrong'},
                        {'iat': time.time() - 301}, {'iat': time.time() + 60}, {'sub': ''}]:
            with self.subTest(changes=changes):
                response, _ = self.signin(**changes)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(get_user_model().objects.filter(username=OWNER_USERNAME).exists())

    def test_invalid_signature_is_rejected(self):
        self.challenge()
        with patch('portal.owner_admin.id_token.verify_oauth2_token', side_effect=ValueError):
            self.assertEqual(self.client.post('/admin/owner-signin/', {'credential': 'synthetic-token-not-real'}).status_code, 403)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.challenge(client)
        self.assertEqual(client.post('/admin/owner-signin/', {'credential': 'synthetic-token-not-real'}).status_code, 403)

    def test_nonce_is_single_use(self):
        response, claims = self.signin()
        self.assertEqual(response.status_code, 200)
        session = self.client.session
        session['owner_admin_nonce'] = claims['nonce']
        session.save()
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims):
            self.assertEqual(self.client.post('/admin/owner-signin/', {'credential': 'synthetic-token-not-real'}).status_code, 403)

    def test_valid_csrf_and_cross_browser_nonce_binding(self):
        client = Client(enforce_csrf_checks=True)
        nonce = self.challenge(client)
        claims = {'iss': 'accounts.google.com', 'email': OWNER_EMAIL, 'email_verified': True,
                  'sub': 'synthetic', 'iat': time.time(), 'nonce': nonce}
        other = Client(enforce_csrf_checks=True)
        self.challenge(other)
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims):
            self.assertEqual(other.post('/admin/owner-signin/', {
                'credential': 'synthetic-token-not-real',
                'csrfmiddlewaretoken': other.cookies['csrftoken'].value}).status_code, 403)
            self.assertEqual(client.post('/admin/owner-signin/', {
                'credential': 'synthetic-token-not-real',
                'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 200)

    def test_throttle(self):
        self.challenge()
        for _ in range(10):
            self.assertEqual(self.client.post('/admin/owner-signin/', {}).status_code, 403)
        self.assertEqual(self.client.post('/admin/owner-signin/', {}).status_code, 429)

    def test_redirect_login_without_lax_session_cookie(self):
        nonce = self.challenge()
        cookie = self.client.cookies['owner_admin_challenge']
        self.assertEqual(cookie['samesite'], 'None')
        self.assertTrue(cookie['httponly'])
        # Simulate Google's cross-site POST: challenge cookie present, no session cookie.
        client = Client(enforce_csrf_checks=True)
        client.cookies['owner_admin_challenge'] = cookie.value
        client.cookies['g_csrf_token'] = 'synthetic-double-submit'
        claims = {'iss': 'accounts.google.com', 'email': OWNER_EMAIL, 'email_verified': True,
                  'sub': 'synthetic', 'iat': time.time(), 'nonce': nonce}
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims):
            response = client.post('/api/google-callback', {
                'credential': 'synthetic-token-not-real', 'state': 'kiwikind-owner-admin',
                'g_csrf_token': 'synthetic-double-submit'})
        self.assertRedirects(response, '/admin/mfa/')
        self.assertEqual(client.get('/admin/').status_code, 302)

    def test_redirect_rejects_missing_or_forged_cookie_and_google_csrf(self):
        self.challenge()
        for cookie, csrf in [('', 'synthetic'), ('forged-cookie', 'synthetic'),
                             (self.client.cookies['owner_admin_challenge'].value, 'wrong')]:
            client = Client(enforce_csrf_checks=True)
            client.cookies['owner_admin_challenge'] = cookie
            client.cookies['g_csrf_token'] = 'synthetic'
            response = client.post('/api/google-callback', {
                'credential': 'synthetic-token-not-real', 'state': 'kiwikind-owner-admin',
                'g_csrf_token': csrf})
            self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username=OWNER_USERNAME).exists())

    def test_expired_challenge_is_rejected(self):
        nonce = self.challenge()
        OwnerAdminChallenge.objects.filter(digest=hashlib.sha256(nonce.encode()).hexdigest()).update(expires_at=timezone.now())
        claims = {'iss': 'accounts.google.com', 'email': OWNER_EMAIL, 'email_verified': True,
                  'sub': 'synthetic', 'iat': time.time(), 'nonce': nonce}
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims):
            self.assertEqual(self.client.post('/admin/owner-signin/', {'credential': 'synthetic-token-not-real'}).status_code, 403)

    def test_existing_inactive_admin_is_not_reenabled(self):
        get_user_model().objects.create_user(OWNER_USERNAME, OWNER_EMAIL, is_active=False)
        response, _ = self.signin()
        self.assertEqual(response.status_code, 403)

    def test_password_session_cannot_enter_admin(self):
        user = get_user_model().objects.create_superuser('another-admin', OWNER_EMAIL, 'synthetic-password')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_proof_expiry_and_logout(self):
        self.signin()
        session = self.client.session
        session['owner_admin_verified_at'] = time.time() - 1801
        session.save()
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.signin()
        self.assertEqual(self.client.post('/admin/logout/').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_ledger_is_read_only(self):
        self.signin()
        for model in ['invoice', 'auditevent']:
            self.assertEqual(self.client.get(f'/admin/portal/{model}/add/').status_code, 403)

    def test_flags_disable_all_admin_routes(self):
        with override_settings(ADMIN_ENABLED=False):
            for path in ['/admin/', '/admin/login/', '/admin/owner-signin/', '/admin/owner.js']:
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_page_has_no_password_field_and_is_not_cached(self):
        response = self.client.get('/admin/login/')
        self.assertContains(response, OWNER_EMAIL)
        self.assertContains(response, 'data-ux_mode="redirect"')
        self.assertContains(response, 'data-state="kiwikind-owner-admin"')
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin')
        self.assertNotContains(response, 'type="password"')
        self.assertIn('no-store', response['Cache-Control'])
        script = self.client.get('/admin/owner.js')
        self.assertEqual(script.status_code, 200)
        self.assertIn('no-store', script['Cache-Control'])
