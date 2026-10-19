import json
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from .models import ReferralCode, Referral, AccountPreferences, PrivacyRequest, Order

User=get_user_model()
@override_settings(INTAKE_ENABLED=False, REGISTRATION_ENABLED=False,REFERRALS_ENABLED=False)
class ReadinessTests(TestCase):
    def setUp(self):
        self.a=User.objects.create_user('ready-a@example.invalid',email='ready-a@example.invalid',password='Synthetic-Kowhai-River-751!')
        self.b=User.objects.create_user('ready-b@example.invalid',email='ready-b@example.invalid',password=None)
        self.web=Client(enforce_csrf_checks=True);self.phone=Client(enforce_csrf_checks=True)
        self.web.force_login(self.a);self.phone.force_login(self.a)
    def post(self,c,path,body):
        token=c.get('/api/bootstrap').json()['csrfToken']
        return c.post('/api/'+path,json.dumps(body),content_type='application/json',HTTP_X_CSRFTOKEN=token)
    def test_bootstrap_combines_verified_identity_status_and_csrf(self):
        anonymous=Client().get('/api/bootstrap')
        self.assertIsNone(anonymous.json()['account']);self.assertIn('csrfToken',anonymous.json());self.assertFalse(anonymous.json()['intake_enabled'])
        self.assertEqual(self.phone.get('/api/bootstrap').json()['account']['email'],self.a.email)
        self.assertEqual(anonymous['Cache-Control'],'no-store')
    def test_shared_code_history_and_preferences_do_not_expose_other_accounts(self):
        self.assertIsNone(self.web.get('/api/referrals').json()['code'])
        result=self.post(self.web,'referrals',{}).json()
        self.assertEqual(len(result['code']),24);self.assertFalse(result['accepting_referrals']);self.assertFalse(result['rewards_enabled'])
        self.assertEqual(self.phone.get('/api/referrals').json()['code'],result['code'])
        self.post(self.web,'preferences',{'account_notifications':True})
        self.assertTrue(self.phone.get('/api/preferences').json()['account_notifications'])
        self.phone.force_login(self.b)
        self.assertIsNone(self.phone.get('/api/referrals').json()['code'])
        self.assertFalse(self.phone.get('/api/preferences').json()['account_notifications'])
        self.assertEqual(len(AccountPreferences.objects.all()),1)
    def test_csrf_auth_and_boolean_validation(self):
        for path in ['referrals','preferences']:
            self.assertEqual(Client().get('/api/'+path).status_code,401)
            self.assertEqual(self.web.post('/api/'+path,'{}',content_type='application/json').status_code,403)
        for value in ['true',1,None,{},[]]:
            self.assertEqual(self.post(self.web,'preferences',{'account_notifications':value}).status_code,400)
    def test_code_issuance_is_idempotent_and_not_client_selected(self):
        first=self.post(self.web,'referrals',{'code':'attacker-choice'}).json()['code']
        self.assertEqual(self.post(self.web,'referrals',{}).json()['code'],first)
        self.assertNotEqual(first,'attacker-choice');self.assertEqual(ReferralCode.objects.count(),1)
    def test_intake_and_rewards_remain_closed(self):
        for path in ['register','orders']:
            self.assertEqual(self.post(self.web,path,{}).status_code,503)
        self.assertEqual(Order.objects.count(),0)
    @override_settings(INTAKE_ENABLED=True, REGISTRATION_ENABLED=True,REFERRALS_ENABLED=True)
    def test_future_registration_verification_attribution_and_history(self):
        code=ReferralCode.objects.create(user=self.a)
        anonymous=Client(enforce_csrf_checks=True)
        body={'email':'invited@example.invalid','password':'Synthetic-Totara-Mountain-937!','consent_version':'prelaunch-2026-10-16','referral_code':code.code}
        self.assertEqual(self.post(anonymous,'register',body).status_code,202)
        referral=Referral.objects.get();self.assertEqual(referral.status,'pending')
        token=mail.outbox[-1].body.split('#verify=')[1].split()[0]
        self.assertEqual(self.post(anonymous,'verify',{'token':token}).status_code,200)
        referral.refresh_from_db();self.assertEqual(referral.status,'verified')
        self.assertEqual(self.post(anonymous,'register',body).status_code,202)
        self.assertEqual(Referral.objects.count(),1)
        history=self.phone.get('/api/referrals').json()['history']
        self.assertEqual(history[0]['status'],'verified');self.assertNotIn('email',str(history));self.assertEqual(Order.objects.count(),0)
    @override_settings(INTAKE_ENABLED=True, REGISTRATION_ENABLED=True,REFERRALS_ENABLED=True)
    def test_invalid_code_rolls_back_user_and_sends_no_mail(self):
        count=User.objects.count()
        self.assertEqual(self.post(Client(),'register',{'email':'badref@example.invalid','password':'Synthetic-Totara-Mountain-937!','consent_version':'prelaunch-2026-10-16','referral_code':'x'*24}).status_code,400)
        self.assertEqual(User.objects.count(),count);self.assertEqual(len(mail.outbox),0)
        self.assertEqual(self.post(Client(),'register',{'email':self.a.email,'password':'Synthetic-Totara-Mountain-937!','consent_version':'prelaunch-2026-10-16','referral_code':'x'*24}).status_code,400)
    def test_database_prevents_self_and_duplicate_referral(self):
        with self.assertRaises(IntegrityError),transaction.atomic():Referral.objects.create(referrer=self.a,invitee=self.a)
        Referral.objects.create(referrer=self.a,invitee=self.b)
        with self.assertRaises(IntegrityError),transaction.atomic():Referral.objects.create(referrer=self.a,invitee=self.b)
    def test_google_only_native_deletion_needs_explicit_confirmation(self):
        self.phone.force_login(self.b)
        self.assertEqual(self.post(self.phone,'privacy/deletion',{}).status_code,403)
        self.assertEqual(self.post(self.phone,'privacy/deletion',{'confirm':True}).status_code,202)
        self.assertEqual(PrivacyRequest.objects.get().user_id,self.b.pk)
        self.assertTrue(User.objects.filter(pk=self.b.pk).exists())
        self.assertEqual(self.post(self.web,'privacy/deletion',{'confirm':True,'password':'wrong'}).status_code,403)
    def test_export_contains_own_preferences_and_no_invitee_identity(self):
        Referral.objects.create(referrer=self.a,invitee=self.b)
        result=self.web.get('/api/privacy/export').json()
        self.assertEqual(len(result['referrals']),1);self.assertNotIn(self.b.email,str(result))
    def test_policy_asset_and_script_are_public_without_enabling_ads(self):
        response=self.client.get('/readiness.js');self.assertEqual(response.status_code,200)
        body=b''.join(self.client.get('/privacy/').streaming_content).decode()
        self.assertIn('Referral preview',body);self.assertIn('NZBN 9429054036550',body);self.assertIn('incorporated on 19 October 2026',body)
