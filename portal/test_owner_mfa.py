import time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import OwnerIdentity, AuditEvent
from .owner_admin import OWNER_EMAIL, OWNER_USERNAME


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True, GOOGLE_WEB_CLIENT_ID='synthetic-client')
class OwnerMFATests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(OWNER_USERNAME, OWNER_EMAIL, is_staff=True, is_superuser=True)
        OwnerIdentity.objects.create(user=self.owner, verified_email=OWNER_EMAIL, subject='synthetic-sub')
        self.client.force_login(self.owner)
        session = self.client.session
        session['owner_google_subject'] = 'synthetic-sub'
        session['owner_admin_verified_at'] = time.time()
        session.save()

    def code(self, device):
        return f'{totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits):06d}'

    def test_enrolment_required_then_unlocks_only_with_code(self):
        self.assertEqual(self.client.get('/admin/portal/draftplan/').status_code, 302)
        response = self.client.get('/admin/mfa/')
        self.assertContains(response, 'Private setup key')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn('accounts.google.com', response['Content-Security-Policy'])
        device = TOTPDevice.objects.get(user=self.owner)
        self.assertFalse(device.confirmed)
        self.assertEqual(self.client.post('/admin/mfa/', {'code': self.code(device)}).status_code, 302)
        self.assertEqual(self.client.get('/admin/portal/draftplan/').status_code, 200)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertTrue(AuditEvent.objects.filter(action='owner_mfa_enrolled').exists())
        self.assertEqual(self.client.get('/admin/mfa/').status_code, 302)

    def test_existing_device_secret_hidden_and_code_cannot_replay(self):
        device = TOTPDevice.objects.create(user=self.owner, confirmed=True)
        self.assertNotContains(self.client.get('/admin/mfa/'), 'Private setup key')
        code = self.code(device)
        self.client.post('/admin/mfa/', {'code': code})
        session = self.client.session
        session.pop('otp_device_id')
        session.save()
        self.assertContains(self.client.post('/admin/mfa/', {'code': code}), 'Code not accepted')
        self.assertEqual(self.client.get('/admin/portal/draftplan/').status_code, 302)

    def test_other_accounts_and_forged_email_roles_cannot_enrol(self):
        for username in ['other-admin', OWNER_EMAIL]:
            user = get_user_model().objects.create_user(username, OWNER_EMAIL, is_staff=True, is_superuser=True)
            self.client.force_login(user)
            session = self.client.session
            session['owner_google_subject'] = 'synthetic-sub'
            session['owner_admin_verified_at'] = time.time()
            session.save()
            self.assertEqual(self.client.get('/admin/mfa/').status_code, 302)
            self.assertEqual(self.client.get('/admin/portal/draftplan/').status_code, 302)
        self.assertFalse(TOTPDevice.objects.exists())

    def test_invalid_codes_throttle_and_csrf_is_required(self):
        # RateBucket uses fixed 15-minute windows. A slow CI job can cross a
        # boundary between attempts, correctly resetting the live limiter.
        # Freeze only the clock during this deterministic boundary-free test.
        with patch('portal.security.time.time', return_value=time.time()):
            self.client.get('/admin/mfa/')
            for _ in range(10):
                self.client.post('/admin/mfa/', {'code': 'invalid'})
            self.assertEqual(self.client.post('/admin/mfa/', {'code': 'invalid'}).status_code, 429)
        browser = Client(enforce_csrf_checks=True)
        browser.cookies = self.client.cookies
        self.assertEqual(browser.post('/admin/mfa/', {'code': '123456'}).status_code, 403)
        self.assertFalse(TOTPDevice.objects.get().confirmed)

    def test_revoked_device_and_expired_google_proof_deny_access(self):
        self.client.get('/admin/mfa/')
        device = TOTPDevice.objects.get()
        self.client.post('/admin/mfa/', {'code': self.code(device)})
        device.refresh_from_db()
        device.confirmed = False
        device.save()
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        session = self.client.session
        session['owner_admin_verified_at'] = time.time() - 1801
        session.save()
        self.assertEqual(self.client.get('/admin/mfa/').status_code, 302)

    def test_changed_google_subject_rejected(self):
        nonce = self.client.get('/admin/login/')  # existing proof redirects to MFA
        self.client.logout()
        self.client.get('/admin/login/')
        claims = dict(iss='https://accounts.google.com', email=OWNER_EMAIL, email_verified=True,
                      sub='changed-subject', nonce=self.client.session['owner_admin_nonce'], iat=time.time())
        with patch('portal.owner_admin.id_token.verify_oauth2_token', return_value=claims):
            response = self.client.post('/admin/owner-signin/', {'credential': 'synthetic-token-only-123'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OwnerIdentity.objects.get().subject, 'synthetic-sub')
