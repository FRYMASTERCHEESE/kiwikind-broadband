"""Two device sessions see the same records, with intake still closed."""
import json
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model


@override_settings(INTAKE_ENABLED=False)
class SharedAccountTests(TestCase):
    def test_independent_sessions_share_support_and_preserve_gates(self):
        user=get_user_model().objects.create_user('shared@example.invalid', email='shared@example.invalid', password='Test-Kowhai-River-651!')
        website, android=Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)

        def post(client, path, body):
            token=client.get('/api/csrf').json()['csrfToken']
            return client.post('/api/'+path,json.dumps(body),content_type='application/json',HTTP_X_CSRFTOKEN=token)

        for client in (website, android):
            self.assertEqual(post(client,'login',{'email':user.email,'password':'Test-Kowhai-River-651!'}).status_code,200)
            self.assertEqual(client.get('/api/me').json()['email'],user.email)
        response=post(website,'tickets',{'subject':'Across devices','category':'support','body':'Sent from website'})
        self.assertEqual(response.status_code,201)
        ticket=response.json()['id']
        self.assertEqual(android.get('/api/tickets').json()['tickets'][0]['id'],ticket)
        self.assertEqual(post(android,f'tickets/{ticket}/messages',{'body':'Reply from Android'}).status_code,200)
        messages=website.get(f'/api/tickets/{ticket}/messages').json()['messages']
        self.assertEqual([m['body'] for m in messages],['Sent from website','Reply from Android'])
        for client in (website, android):
            self.assertFalse(client.get('/api/status').json()['intake_enabled'])
            self.assertFalse(client.get('/api/invoices').json()['billing_enabled'])
            self.assertEqual(post(client,'orders',{}).status_code,503)
        self.assertEqual(post(android,'logout',{}).status_code,200)
        self.assertEqual(android.get('/api/me').status_code,401)
        self.assertEqual(website.get('/api/me').status_code,200)
