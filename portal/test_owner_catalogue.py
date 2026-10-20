from datetime import timedelta
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.oath import totp
from .models import EmailVerification, PricePlan

class OwnerSecurityTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('kiwikindbroadband@gmail.com','kiwikindbroadband@gmail.com','Owner-Synthetic-Password-123!')
        self.enterContext(override_settings(OWNER_USER_ID=str(self.owner.pk)))
        EmailVerification.objects.create(user=self.owner,email=self.owner.email)
        self.device=TOTPDevice.objects.create(user=self.owner,confirmed=True)
    def test_owner_password_session_cannot_read_admin(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/admin/portal/order/').status_code,302)
    def test_actual_mfa_login_and_replay_rejected(self):
        data={'username':self.owner.username,'password':'Owner-Synthetic-Password-123!','otp_device':self.device.persistent_id,'otp_token':str(totp(self.device.bin_key))}
        response=self.client.post('/admin/login/',data)
        self.assertEqual(response.status_code,302, str(response.context['form'].errors) if response.context else '')
        r=self.client.get('/admin/')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r['Cache-Control'].find('no-store')>=0,True)
        other=Client()
        self.assertEqual(other.post('/admin/login/',data).status_code,200)
        self.assertEqual(other.get('/admin/').status_code,302)
    def test_forged_email_superuser_and_unverified_owner_denied(self):
        for name in ['customer@example.invalid','impostor']:
            u=get_user_model().objects.create_superuser(name,self.owner.email,'Synthetic-Password-123!')
            self.client.force_login(u)
            for path in ['/admin/','/admin/portal/order/','/admin/portal/priceplan/','/admin/auth/user/']:
                self.assertEqual(self.client.get(path).status_code,404)
        EmailVerification.objects.all().delete()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/admin/').status_code,404)
    def test_registration_never_accepts_role_fields(self):
        self.client.post('/api/register',{'email':'attack@example.invalid','password':'Synthetic-Password-123!',
            'consent_version':'prelaunch-2026-10-16','is_staff':True,'is_superuser':True},content_type='application/json')
        u=get_user_model().objects.get(username='attack@example.invalid')
        self.assertFalse(u.is_staff);self.assertFalse(u.is_superuser)
    def test_csrf_admin_login(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/admin/login/',{}).status_code,403)
    @override_settings(OWNER_USER_ID='')
    def test_missing_identity_binding_denies_all(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/admin/').status_code,404)

class CatalogueTests(TestCase):
    def test_draft_quote_is_private_and_cannot_be_approved(self):
        call_command('prepare_vetta_quote',verbosity=0)
        p=PricePlan.objects.get()
        self.assertEqual(str(p.wholesale_incl_gst),'80.41')
        self.assertIsNone(p.retail_monthly_cents)
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
        p.status='approved'
        with self.assertRaises(ValidationError):p.full_clean()
    @override_settings(PLAN_PUBLICATION_ENABLED=True)
    def test_only_current_owner_approved_retail_fields_public(self):
        u=get_user_model().objects.create_user('owner-test')
        self.enterContext(override_settings(OWNER_USER_ID=str(u.pk)))
        call_command('prepare_vetta_quote',verbosity=0)
        p=PricePlan.objects.get();p.address_specific=False;p.status='approved'
        p.valid_until=timezone.localdate()+timedelta(days=2)
        p.retail_monthly_cents=9990;p.retail_setup_cents=0;p.approved_by=u;p.approved_at=timezone.now();p.save()
        data=self.client.get('/api/plans').json()
        self.assertEqual(len(data['plans']),1)
        self.assertNotIn('wholesale',str(data));self.assertNotIn('source',data['plans'][0])
        p.valid_until=timezone.localdate()-timedelta(days=1);p.save()
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
