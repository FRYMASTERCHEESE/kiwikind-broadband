import json
import time
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import DraftPlan, OwnerIdentity
from .owner_admin import OWNER_USERNAME, OWNER_EMAIL

ORIGIN = 'https://frymastercheese.github.io'


@override_settings(PAGES_ENABLED=True, CSRF_TRUSTED_ORIGINS=[ORIGIN])
class PagesTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get('/api/bootstrap', HTTP_ORIGIN=ORIGIN).json()['csrfToken']

    def post(self, path, data, token=None, origin=ORIGIN):
        return self.client.post('/api/'+path, json.dumps(data), content_type='application/json',
            HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=self.token if token is None else token)

    def test_credentials_cors_and_csrf(self):
        r=self.post('pages/cookie-probe',{})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r['Access-Control-Allow-Origin'],ORIGIN)
        self.assertEqual(r['Access-Control-Allow-Credentials'],'true')
        self.assertEqual(r['Cache-Control'],'no-store')
        self.assertIn('Origin',r['Vary'])
        self.assertTrue(self.client.get('/api/pages/session-probe').json()['session_cookie'])
        self.assertEqual(self.post('pages/cookie-probe',{},token='').status_code,403)
        self.assertEqual(self.post('pages/cookie-probe',{},origin='https://evil.example').status_code,403)
        self.assertEqual(self.post('pages/cookie-probe',{},origin='https://other.github.io').status_code,403)
        self.client.cookies.clear()
        self.assertEqual(self.post('pages/cookie-probe',{}).status_code,403)

    def test_preflight_restricts_methods_headers_origin(self):
        for origin,method,headers,status in [(ORIGIN,'POST','content-type,x-csrftoken',200),
            (ORIGIN,'DELETE','content-type',403),(ORIGIN,'POST','authorization',403),
            ('https://evil.example','POST','content-type',403)]:
            r=self.client.options('/api/owner/catalogue',HTTP_ORIGIN=origin,
                HTTP_ACCESS_CONTROL_REQUEST_METHOD=method,HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headers)
            self.assertEqual(r.status_code,status)

    def test_no_private_data_without_both_factors(self):
        for path in ['owner/readiness','owner/catalogue','owner/mfa']:
            self.assertEqual(self.client.get('/api/'+path).status_code,403)
        customer=get_user_model().objects.create_user('customer',password='A-long-test-password')
        self.client.force_login(customer)
        self.assertEqual(self.client.get('/api/owner/catalogue').status_code,403)
        customer.is_staff=True;customer.is_superuser=True;customer.save()
        self.assertEqual(self.client.get('/api/owner/catalogue').status_code,403)

    def google_owner(self):
        r=self.post('owner/challenge',{})
        self.assertEqual(r.status_code,200)
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':OWNER_EMAIL,
                'sub':'owner-subject','iat':time.time(),'nonce':r.json()['nonce']}
        with patch('portal.owner_admin.id_token.verify_oauth2_token',return_value=claims):
            r=self.post('owner/signin',{'credential':'synthetic-credential-value'})
        self.assertEqual(r.status_code,200)
        self.token=r.json()['csrfToken']
        return get_user_model().objects.get(username=OWNER_USERNAME)

    def test_owner_mfa_and_expiry(self):
        user=self.google_owner()
        self.assertEqual(self.client.get('/api/owner/catalogue').status_code,403)
        enrollment=self.client.get('/api/owner/mfa').json()
        self.assertTrue(enrollment['setup_key'])
        device=TOTPDevice.objects.get(user=user)
        code=f'{totp(device.bin_key,step=device.step,t0=device.t0,digits=device.digits):06d}'
        r=self.post('owner/mfa',{'code':code});self.assertEqual(r.status_code,200)
        self.token=r.json()['csrfToken']
        self.assertEqual(self.client.get('/api/owner/mfa').json().get('setup_key',''),'')
        self.assertEqual(self.client.get('/api/owner/catalogue').status_code,200)
        self.assertFalse(self.client.get('/api/owner/readiness').json()['provider_rechecked_now'])
        raw=('name,download_mbps,upload_mbps,network,wholesale_ex_gst,setup_ex_gst,retail_ex_gst,retail_setup_ex_gst,source_reference\n'
             'Synthetic private quote,100,20,Synthetic network,40.00,,,,Synthetic reference\n')
        self.assertEqual(self.post('owner/catalogue',{'csv':raw,'confirm_draft_only':False}).status_code,400)
        self.assertEqual(self.post('owner/catalogue',{'csv':raw,'confirm_draft_only':True}).status_code,200)
        plan=DraftPlan.objects.get(name='Synthetic private quote');self.assertTrue(plan.address_specific)
        self.assertEqual(plan.review_status,'draft');self.assertIsNone(plan.approved_at)
        self.assertIsNone(plan.setup_ex_gst)
        session=self.client.session;session['owner_admin_verified_at']=time.time()-1801;session.save()
        self.assertEqual(self.client.get('/api/owner/catalogue').status_code,403)

    def test_nonce_replay_wrong_owner_and_missing_csrf(self):
        r=self.post('owner/challenge',{})
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':OWNER_EMAIL,
                'sub':'owner-subject','iat':time.time(),'nonce':r.json()['nonce']}
        with patch('portal.owner_admin.id_token.verify_oauth2_token',return_value={**claims,'email':'customer@example.invalid'}):
            self.assertEqual(self.post('owner/signin',{'credential':'synthetic-credential-value'}).status_code,403)
        with patch('portal.owner_admin.id_token.verify_oauth2_token',return_value=claims):
            self.assertEqual(self.post('owner/signin',{'credential':'synthetic-credential-value'},token='').status_code,403)
            r=self.post('owner/signin',{'credential':'synthetic-credential-value'})
            self.assertEqual(r.status_code,200);self.token=r.json()['csrfToken']
            self.assertEqual(self.post('owner/signin',{'credential':'synthetic-credential-value'}).status_code,403)

    @override_settings(PAGES_API_ONLY=True)
    def test_backend_has_no_visible_pages_or_open_redirect(self):
        for path in ['/', '/admin/', '/admin/mfa/', '/billing/', '/privacy/']:
            r=self.client.get(path+'?next=https://evil.example')
            self.assertEqual(r.status_code,302)
            self.assertTrue(r['Location'].startswith(ORIGIN+'/kiwikind-broadband-website/'))
            self.assertNotIn('evil',r['Location'])
        self.assertEqual(self.client.get('/healthz').status_code,200)
        self.assertEqual(self.client.post('/admin/mfa/').status_code,404)
