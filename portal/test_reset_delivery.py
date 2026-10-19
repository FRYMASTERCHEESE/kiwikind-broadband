import json
from unittest.mock import patch
from smtplib import SMTPAuthenticationError, SMTPRecipientsRefused
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core import mail

@override_settings(INTAKE_ENABLED=False, REGISTRATION_ENABLED=False, RESET_EMAIL_UNAVAILABLE=False)
class ResetDeliveryTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('reset@example.invalid',email='reset@example.invalid',password=None)
    def request_reset(self, email):
        return self.client.post('/api/password-reset',json.dumps({'email':email}),content_type='application/json')
    def test_transport_failure_same_for_known_and_unknown(self):
        with patch('portal.views.get_connection') as factory:
            factory.return_value.open.side_effect=SMTPAuthenticationError(535,b'sensitive-provider-detail')
            known=self.request_reset(self.user.email);unknown=self.request_reset('unknown@example.invalid')
        self.assertEqual(known.status_code,503)
        self.assertEqual(known.content,unknown.content)
        self.assertNotIn(b'sensitive-provider-detail',known.content)
    @override_settings(RESET_EMAIL_UNAVAILABLE=True)
    def test_blocked_transport_does_not_lookup_accounts(self):
        with patch('portal.views.User.objects.filter') as lookup:
            self.assertEqual(self.request_reset(self.user.email).status_code,503)
            self.assertEqual(self.request_reset('unknown@example.invalid').status_code,503)
            lookup.assert_not_called()
    def test_google_only_account_receives_browser_reset_link_without_account_mutation(self):
        response=self.request_reset(self.user.email.upper())
        self.assertEqual(response.status_code,202)
        self.assertEqual(mail.outbox[0].to,[self.user.email])
        self.assertIn('/#reset=',mail.outbox[0].body)
        self.assertFalse(get_user_model().objects.get(pk=self.user.pk).has_usable_password())
    def test_recipient_failure_does_not_expose_account_or_provider_detail(self):
        with patch('portal.views.send_mail',side_effect=SMTPRecipientsRefused({'private':'secret'})):
            known=self.request_reset(self.user.email)
        unknown=self.request_reset('unknown@example.invalid')
        self.assertEqual(known.status_code,202)
        self.assertEqual(known.content,unknown.content)
        self.assertNotIn(b'secret',known.content)
