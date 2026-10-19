"""Account-only launch: synthetic identities and in-memory mail, no supplier calls."""
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from .models import GoogleIdentity, Order, Invoice


@override_settings(REGISTRATION_ENABLED=True, INTAKE_ENABLED=False, REFERRALS_ENABLED=False,
                   RESET_EMAIL_UNAVAILABLE=False, ADMIN_ENABLED=True)
class AccountLaunchTests(TestCase):
    def post(self, client, route, data):
        csrf = client.get('/api/bootstrap').json()['csrfToken']
        return client.post('/api/'+route, json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)

    def registration(self, email='new-launch@example.invalid'):
        return dict(email=email, password='Synthetic-River-Kowhai-752!', consent_version='prelaunch-2026-10-16')

    def test_new_verified_account_shares_support_between_web_and_android_but_cannot_order(self):
        web, phone = Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)
        data = self.registration()
        self.assertEqual(self.post(web, 'register', data).status_code, 202)
        self.assertFalse(get_user_model().objects.get(email=data['email']).is_active)
        token = mail.outbox[-1].body.split('#verify=')[1].split()[0]
        self.assertEqual(self.post(web, 'verify', {'token':token}).status_code, 200)
        for client in (web, phone):
            self.assertEqual(self.post(client, 'login', data).status_code, 200)
            state = client.get('/api/bootstrap').json()
            self.assertTrue(state['registration_enabled'])
            self.assertEqual(state['account']['email'], data['email'])
            self.assertFalse(state['intake_enabled'])
            self.assertFalse(state['billing_enabled'])
            self.assertFalse(state['live_services'])
            self.assertEqual(self.post(client, 'orders', {}).status_code, 503)
            self.assertEqual(client.get('/admin/wholesale/').status_code, 302)
        ticket = self.post(web, 'tickets', {'subject':'Account question', 'category':'support', 'body':'Synthetic web message'}).json()['id']
        self.assertEqual(phone.get('/api/tickets').json()['tickets'][0]['id'], ticket)
        self.assertEqual(self.post(phone, f'tickets/{ticket}/messages', {'body':'Synthetic phone reply'}).status_code, 200)
        self.assertEqual(len(web.get(f'/api/tickets/{ticket}/messages').json()['messages']), 2)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_new_google_account_works_with_intake_closed_without_granting_staff(self):
        claims = dict(iss='https://accounts.google.com', email_verified=True,
                      email='google-launch@example.invalid', sub='synthetic-google-launch')
        with patch.dict('os.environ', {'GOOGLE_WEB_CLIENT_ID':'synthetic-client'}), patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
            for client in (Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)):
                self.assertEqual(self.post(client, 'google-login', {'id_token':'synthetic-google-token-for-test'}).status_code, 200)
                self.assertEqual(self.post(client, 'orders', {}).status_code, 503)
        user = get_user_model().objects.get(email=claims['email'])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(GoogleIdentity.objects.count(), 1)

    @override_settings(REGISTRATION_ENABLED=False, INTAKE_ENABLED=True)
    def test_order_switch_cannot_open_registration(self):
        self.assertEqual(self.post(self.client, 'register', self.registration()).status_code, 503)
        self.assertFalse(self.client.get('/api/bootstrap').json()['registration_enabled'])
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_mail_outage_is_same_for_new_and_existing_accounts(self):
        get_user_model().objects.create_user('existing@example.invalid', email='existing@example.invalid')
        with patch('portal.views.get_connection') as connection:
            connection.return_value.open.side_effect = OSError('synthetic outage')
            responses = [self.post(self.client, 'register', self.registration(email)) for email in ('existing@example.invalid', 'new@example.invalid')]
        self.assertEqual([r.status_code for r in responses], [503,503])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_recipient_delivery_failure_rolls_back_partial_account(self):
        with patch('portal.views.send_mail', side_effect=OSError('synthetic provider failure')):
            response = self.post(self.client, 'register', self.registration())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_registration_still_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post('/api/register', json.dumps(self.registration()), content_type='application/json')
        self.assertEqual(response.status_code, 403)
