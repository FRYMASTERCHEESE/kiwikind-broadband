import json
import uuid
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core import mail, signing
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest
from .suppliers import UnconfiguredSupplier, SupplierNotConfigured

User=get_user_model()
class PlatformTests(TestCase):
    def setUp(self):
        self.alice=User.objects.create_user('alice@example.invalid',email='alice@example.invalid',password='Safe-Wattle-River-524!')
        self.bob=User.objects.create_user('bob@example.invalid',email='bob@example.invalid',password='Safe-Wattle-River-524!')
        self.client.force_login(self.alice)
    def post(self,path,data,client=None): return (client or self.client).post('/api/'+path,json.dumps(data),content_type='application/json')
    def order(self,**extra):
        data={'address':'12 Test Street, Wellington','postcode':'6011','contact_name':'Test Customer','phone':'','idempotency_key':str(uuid.uuid4()),'consent_version':'prelaunch-2026-10-16'}
        data.update(extra);return data
    def test_request_is_not_live_order(self):
        r=self.post('orders',self.order());self.assertEqual(r.status_code,201)
        self.assertEqual(r.json()['order']['status'],'requested');self.assertEqual(Invoice.objects.count(),0)
        self.assertEqual(AuditEvent.objects.get().action,'order_requested')
    def test_idempotent_request(self):
        data=self.order();a=self.post('orders',data);b=self.post('orders',data)
        self.assertEqual(a.json()['order']['id'],b.json()['order']['id']);self.assertEqual(Order.objects.count(),1)
        data['address']='99 Another Street';self.assertEqual(self.post('orders',data).status_code,409)
    def test_order_ownership_and_cancellation(self):
        oid=self.post('orders',self.order()).json()['order']['id'];self.client.force_login(self.bob)
        self.assertEqual(self.client.get('/api/orders').json()['orders'],[])
        self.assertEqual(self.post(f'orders/{oid}/cancel',{}).status_code,404)
        self.client.force_login(self.alice);self.assertEqual(self.post(f'orders/{oid}/cancel',{}).json()['order']['status'],'cancelled')
    def test_invalid_inputs(self):
        for data in [self.order(postcode='abcd'),self.order(consent_version='old'),self.order(idempotency_key='x'*36),self.order(phone='not a phone')]:
            self.assertEqual(self.post('orders',data).status_code,400)
    def test_auth_required_every_customer_endpoint(self):
        c=Client()
        for path in ['me','orders','tickets','invoices','privacy/export']:
            self.assertEqual(c.get('/api/'+path).status_code,401)
        for path in ['orders','tickets','logout','privacy/deletion']:
            self.assertEqual(self.post(path,{},c).status_code,401)
    def test_csrf_enforced_for_login_and_customer_writes(self):
        c=Client(enforce_csrf_checks=True)
        self.assertEqual(self.post('login',{'email':self.alice.email,'password':'Safe-Wattle-River-524!'},c).status_code,403)
        token=c.get('/api/csrf').json()['csrfToken']
        r=c.post('/api/login',json.dumps({'email':self.alice.email,'password':'Safe-Wattle-River-524!'}),content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.post('orders',self.order(),c).status_code,403)
    def test_verification_and_password_reset(self):
        c=Client();r=self.post('register',{'email':'new@example.invalid','password':'Careful-Kowhai-Cloud-602!','consent_version':'prelaunch-2026-10-16'},c)
        self.assertEqual(r.status_code,202);u=User.objects.get(username='new@example.invalid');self.assertFalse(u.is_active)
        token=mail.outbox[-1].body.split('#verify=')[1].split()[0]
        self.assertEqual(self.post('verify',{'token':token},c).status_code,200)
        self.assertEqual(self.post('verify',{'token':token},c).status_code,400)
        self.post('password-reset',{'email':u.email},c);token=mail.outbox[-1].body.split('#reset=')[1].strip()
        self.assertEqual(self.post('password-reset/confirm',{'token':token,'password':'Another-Kowhai-Cloud-903!'},c).status_code,200)
        self.assertEqual(self.post('password-reset/confirm',{'token':token,'password':'Another-Kowhai-Cloud-903!'},c).status_code,400)
    def test_weak_password_rejected(self):
        self.assertEqual(self.post('register',{'email':'bad@example.invalid','password':'123456789012','consent_version':'prelaunch-2026-10-16'}).status_code,400)
    def test_ticket_messages_isolated(self):
        tid=self.post('tickets',{'subject':'Question','category':'complaint','body':'Please review'}).json()['id']
        self.assertEqual(self.post(f'tickets/{tid}/messages',{'body':'More details'}).status_code,200)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(f'/api/tickets/{tid}/messages').status_code,404)
        self.assertEqual(self.post(f'tickets/{tid}/messages',{'body':'Intrusion'}).status_code,404)
        self.assertEqual(Message.objects.count(),2)
    def test_export_and_deletion(self):
        self.post('orders',self.order());r=self.client.get('/api/privacy/export')
        self.assertEqual(len(r.json()['orders']),1);self.assertNotIn('password',r.json())
        self.assertEqual(self.post('privacy/deletion',{'password':'wrong'}).status_code,403)
        for _ in range(2):self.assertEqual(self.post('privacy/deletion',{'password':'Safe-Wattle-River-524!'}).status_code,202)
        self.assertEqual(PrivacyRequest.objects.count(),1)
        self.client.force_login(self.bob);self.assertEqual(self.client.get('/api/privacy/export').json()['orders'],[])
    def test_billing_is_readonly_and_isolated(self):
        Invoice.objects.create(user=self.bob,supplier_reference='test-only',amount_cents=100,currency='NZD',due_date='2026-10-16',status='unpaid')
        self.assertEqual(self.client.get('/api/invoices').json()['invoices'],[])
        self.assertEqual(self.post('invoices',{'amount_cents':1}).status_code,405)
    @override_settings(INTAKE_ENABLED=False)
    def test_intake_gate(self):
        self.assertEqual(self.post('register',{}).status_code,503)
        self.assertEqual(self.post('orders',self.order()).status_code,503)
    @override_settings(ADMIN_ENABLED=False)
    def test_admin_disabled_by_default(self):self.assertEqual(self.client.get('/admin/').status_code,404)
    def test_rate_limit_login(self):
        c=Client()
        for _ in range(10):self.post('login',{'email':'unknown@example.invalid','password':'bad'},c)
        self.assertEqual(self.post('login',{'email':'unknown@example.invalid','password':'bad'},c).status_code,429)
    def test_security_headers(self):
        r=self.client.get('/api/me');self.assertEqual(r['Cache-Control'],'no-store');self.assertEqual(r['X-Frame-Options'],'DENY')
        self.assertIn("frame-ancestors 'none'",r['Content-Security-Policy'])
    def test_malformed_requests(self):
        self.assertEqual(self.client.post('/api/orders','[]',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post('/api/orders','{'+'x'*17000,content_type='application/json').status_code,413)
    def test_supplier_fails_closed(self):
        s=UnconfiguredSupplier();self.assertIsNone(s.check_address('test','6011').available)
        for method in [s.submit_order,s.get_order,s.cancel_order,s.report_fault]:
            with self.assertRaises(SupplierNotConfigured):method('test')
    def test_logout_revokes_session(self):
        self.assertEqual(self.post('logout',{}).status_code,200);self.assertEqual(self.client.get('/api/me').status_code,401)
    def test_admin_permissions_and_ledger_protection(self):
        self.assertEqual(self.client.get('/admin/portal/order/').status_code,302)
        staff=User.objects.create_user('support@example.invalid',password='Staff-Kowhai-Planet-123!',is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/portal/order/').status_code,403)
        superuser=User.objects.create_superuser('operator@example.invalid','operator@example.invalid','Staff-Kowhai-Planet-123!')
        self.client.force_login(superuser)
        self.assertEqual(self.client.get('/admin/portal/invoice/add/').status_code,403)
        self.assertEqual(self.client.get('/admin/portal/auditevent/add/').status_code,403)
    def test_admin_support_reply_and_audit(self):
        t=Ticket.objects.create(user=self.alice,subject='Synthetic complaint',category='complaint')
        original=Message.objects.create(ticket=t,author=self.alice,body='Please help')
        operator=User.objects.create_superuser('operator@example.invalid','operator@example.invalid','Staff-Kowhai-Planet-123!')
        self.client.force_login(operator)
        r=self.client.post(f'/admin/portal/ticket/{t.pk}/change/',{
            'status':'open','messages-TOTAL_FORMS':'2','messages-INITIAL_FORMS':'1',
            'messages-MIN_NUM_FORMS':'0','messages-MAX_NUM_FORMS':'1000',
            'messages-0-id':str(original.pk),'messages-0-ticket':str(t.pk),
            'messages-1-ticket':str(t.pk),'messages-1-body':'We have received your concern.','_save':'Save'})
        self.assertEqual(r.status_code,302)
        reply=t.messages.exclude(pk=original.pk).get();self.assertEqual(reply.author,operator)
        self.assertTrue(AuditEvent.objects.filter(action='support_reply',reference=str(t.pk)).exists())


class GoogleAuthenticationTests(TestCase):
    def post_google(self, token='synthetic-google-id-token-for-tests'):
        return self.client.post('/api/google-login', json.dumps({'id_token': token}), content_type='application/json')

    @override_settings(INTAKE_ENABLED=False)
    def test_closed_intake_rejects_google_registration(self):
        from unittest.mock import patch
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':'new@example.invalid','sub':'new-google-subject'}
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
                self.assertEqual(self.post_google().status_code, 503)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(INTAKE_ENABLED=True)
    def test_invalid_google_token_does_not_create_user(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', side_effect=ValueError('bad token')):
                self.assertEqual(self.post_google().status_code, 401)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(INTAKE_ENABLED=True)
    def test_google_email_collision_cannot_take_over_password_account(self):
        from unittest.mock import patch
        User.objects.create_user('same@example.invalid', email='same@example.invalid', password='Secure-Passphrase-1203!')
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':'same@example.invalid','sub':'unique-google-subject'}
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
                self.assertEqual(self.post_google().status_code, 409)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    @override_settings(INTAKE_ENABLED=True)
    def test_verified_google_account_can_sign_in_again_without_duplicate(self):
        from unittest.mock import patch
        from .models import GoogleIdentity
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':'new-google@example.invalid','sub':'stable-google-subject'}
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
                self.assertEqual(self.post_google().status_code, 200)
                self.assertEqual(self.client.get('/api/me').status_code, 200)
                self.assertEqual(self.post_google().status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(GoogleIdentity.objects.count(), 1)

    @override_settings(INTAKE_ENABLED=True)
    def test_unverified_google_email_rejected(self):
        from unittest.mock import patch
        claims={'iss':'https://accounts.google.com','email_verified':False,'email':'bad@example.invalid','sub':'unverified-google-subject'}
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
                self.assertEqual(self.post_google().status_code, 401)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(INTAKE_ENABLED=False)
    def test_existing_google_identity_can_login_when_registration_closed(self):
        from unittest.mock import patch
        from .models import GoogleIdentity
        user=User.objects.create_user('returning@example.invalid',email='returning@example.invalid',password=None)
        GoogleIdentity.objects.create(user=user,subject='known-google-subject')
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':'returning@example.invalid','sub':'known-google-subject'}
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'test-client'}):
            with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
                self.assertEqual(self.post_google().status_code, 200)
        self.assertEqual(User.objects.count(),1)


class WebsiteAndroidSharedDataTests(TestCase):
    """Two separate authenticated clients simulate website and Android devices."""
    def setUp(self):
        self.user=User.objects.create_user('shared@example.invalid',email='shared@example.invalid',password='Test-Shared-Login-392!')
        self.other=User.objects.create_user('other@example.invalid',email='other@example.invalid',password='Test-Shared-Login-392!')
        self.website=Client();self.android=Client();self.stranger=Client()
        self.website.force_login(self.user);self.android.force_login(self.user);self.stranger.force_login(self.other)

    def post_from(self,client,path,data):
        return client.post('/api/'+path,json.dumps(data),content_type='application/json')

    def test_website_support_ticket_appears_on_android(self):
        response=self.post_from(self.website,'tickets',{'subject':'Website support question','category':'support','body':'Hello from website'})
        self.assertEqual(response.status_code,201)
        android=self.android.get('/api/tickets')
        self.assertEqual(android.status_code,200)
        self.assertEqual(android.json()['tickets'][0]['subject'],'Website support question')
        self.assertEqual(self.stranger.get('/api/tickets').json()['tickets'],[])

    def test_android_reply_appears_on_website(self):
        response=self.post_from(self.website,'tickets',{'subject':'Shared conversation','category':'support','body':'Original website message'})
        self.assertEqual(response.status_code,201)
        ticket=response.json()['id']
        self.assertEqual(self.post_from(self.android,f'tickets/{ticket}/messages',{'body':'Reply from Android'}).status_code,200)
        messages=self.website.get(f'/api/tickets/{ticket}/messages').json()['messages']
        self.assertEqual([m['body'] for m in messages],['Original website message','Reply from Android'])
        self.assertEqual(self.stranger.get(f'/api/tickets/{ticket}/messages').status_code,404)

    def test_account_and_billing_are_consistent_across_clients(self):
        self.assertEqual(self.website.get('/api/me').json()['email'],self.android.get('/api/me').json()['email'])
        self.assertEqual(self.website.get('/api/invoices').json(),self.android.get('/api/invoices').json())
        self.assertFalse(self.android.get('/api/invoices').json()['billing_enabled'])

    @override_settings(INTAKE_ENABLED=False)
    def test_closed_intake_is_consistent_on_both_platforms(self):
        self.assertFalse(self.website.get('/api/status').json()['intake_enabled'])
        self.assertFalse(self.android.get('/api/status').json()['intake_enabled'])
        self.assertEqual(self.post_from(self.website,'orders',{}).status_code,503)
        self.assertEqual(self.post_from(self.android,'orders',{}).status_code,503)
