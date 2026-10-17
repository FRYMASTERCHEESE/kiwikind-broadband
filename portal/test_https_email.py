import json
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMessage, get_connection
from django.test import Client, SimpleTestCase, TestCase, override_settings

from .email_backend import BrevoEmailBackend, MailDeliveryError
from .models import GoogleIdentity


EMAIL_SETTINGS = {
    'EMAIL_BACKEND': 'portal.email_backend.BrevoEmailBackend',
    'BREVO_API_KEY': 'synthetic-unit-test-key',
    'DEFAULT_FROM_EMAIL': 'KiwiKind Broadband <kiwikindbroadband@gmail.com>',
    'EMAIL_REPLY_TO': 'kiwikindbroadband@gmail.com',
    'RESET_EMAIL_UNAVAILABLE': False,
    'INTAKE_ENABLED': False,
    'PUBLIC_ORIGIN': 'https://kiwikind.example.invalid',
}
FREE_ACCOUNT = {'plan': [{'type': 'free', 'credits': 300}], 'relay': {'enabled': True}}
SENDERS = {'senders': [{'email': 'kiwikindbroadband@gmail.com', 'active': True}]}


def reply(data, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = data
    response.__enter__.return_value = response
    return response


class ProviderMock:
    def setUp(self):
        super().setUp()
        self.session = MagicMock()
        self.session.headers = {}
        self.session.request.side_effect = [
            reply(FREE_ACCOUNT), reply(SENDERS), reply({'messageId': '<synthetic-id>'}, 201),
        ]
        patcher = patch('portal.email_backend.requests.Session', return_value=self.session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def message(self):
        return EmailMessage('Reset password', 'https://kiwikind.example.invalid/#reset=synthetic',
                            EMAIL_SETTINGS['DEFAULT_FROM_EMAIL'], ['synthetic@example.invalid'])


@override_settings(**EMAIL_SETTINGS)
class HttpsBackendTests(ProviderMock, SimpleTestCase):
    def test_delivery_uses_fixed_https_api_plain_text_and_gmail_reply_to(self):
        self.assertEqual(get_connection().send_messages([self.message()]), 1)
        calls = self.session.request.call_args_list
        self.assertEqual([(c.args[0], c.args[1]) for c in calls], [
            ('GET', 'https://api.brevo.com/v3/account'),
            ('GET', 'https://api.brevo.com/v3/senders'),
            ('POST', 'https://api.brevo.com/v3/smtp/email'),
        ])
        for call in calls:
            self.assertIs(call.kwargs['allow_redirects'], False)
            self.assertEqual(call.kwargs['timeout'], (3, 7))
        payload = calls[-1].kwargs['json']
        self.assertEqual(payload['sender']['email'], 'kiwikindbroadband@gmail.com')
        self.assertEqual(payload['replyTo']['email'], 'kiwikindbroadband@gmail.com')
        self.assertEqual(payload['textContent'], self.message().body)
        self.assertNotIn(EMAIL_SETTINGS['BREVO_API_KEY'], json.dumps(payload))
        self.assertEqual(self.session.headers, {})
        self.session.close.assert_called_once()

    @override_settings(BREVO_API_KEY='')
    def test_missing_key_fails_without_network(self):
        with self.assertRaises(MailDeliveryError):
            get_connection().open()
        self.session.request.assert_not_called()

    def test_paid_empty_or_unknown_plan_and_disabled_relay_fail_before_sending(self):
        for account in [
            {'plan': [{'type': 'subscription', 'credits': 1000}], 'relay': {'enabled': True}},
            {'plan': [{'type': 'free', 'credits': 0}], 'relay': {'enabled': True}},
            {'plan': [{'type': 'new-unknown-plan', 'credits': 300}], 'relay': {'enabled': True}},
            {'plan': [{'type': 'free', 'credits': 300}], 'relay': {'enabled': False}},
            {'plan': [{'type': 'free', 'credits': 300}], 'relay': None},
            {'plan': 'malformed'},
        ]:
            with self.subTest(account=account):
                self.session.reset_mock()
                self.session.request.side_effect = [reply(account)]
                with self.assertRaises(MailDeliveryError):
                    get_connection().open()
                self.assertEqual(self.session.request.call_count, 1)
                self.session.close.assert_called_once()

    def test_inactive_or_missing_sender_is_not_sent(self):
        for senders in ({'senders': []}, {'senders': [{'email': 'kiwikindbroadband@gmail.com', 'active': False}]}):
            with self.subTest(senders=senders):
                self.session.request.side_effect = [reply(FREE_ACCOUNT), reply(senders)]
                with self.assertRaises(MailDeliveryError):
                    get_connection().open()

    def test_provider_http_failures_and_redirects_are_sanitized_without_retry(self):
        for code in (301, 400, 401, 403, 429, 500, 503):
            with self.subTest(code=code):
                self.session.reset_mock()
                self.session.request.side_effect = [reply({'message': 'private-provider-detail'}, code)]
                with self.assertRaises(MailDeliveryError) as failure:
                    get_connection().open()
                self.assertNotIn('private-provider-detail', str(failure.exception))
                self.assertEqual(self.session.request.call_count, 1)

    def test_timeout_and_invalid_json_do_not_expose_key_or_provider_body(self):
        malformed = reply({})
        malformed.json.side_effect = ValueError('private-body')
        for result in (requests.Timeout('synthetic-unit-test-key'), malformed, reply([])):
            with self.subTest(result=type(result).__name__):
                self.session.request.side_effect = [result]
                with self.assertRaises(MailDeliveryError) as failure:
                    get_connection().open()
                self.assertNotIn('synthetic-unit-test-key', str(failure.exception))
                self.assertNotIn('private-body', str(failure.exception))

    def test_runtime_diagnostics_identify_stage_without_secret_or_response_body(self):
        self.session.request.side_effect = [reply({'message': 'private-provider-detail'}, 403)]
        with self.assertLogs('portal.email_backend', level='WARNING') as logs:
            with self.assertRaises(MailDeliveryError):
                get_connection().open()
        output = '\n'.join(logs.output)
        self.assertIn('stage=account http_status=403', output)
        self.assertNotIn('private-provider-detail', output)
        self.assertNotIn(EMAIL_SETTINGS['BREVO_API_KEY'], output)

    def test_disabled_relay_diagnostic_reports_free_allowance_without_account_data(self):
        self.session.request.side_effect = [reply({
            'plan': [{'type': 'free', 'credits': 300}], 'relay': {'enabled': False},
            'email': 'private@example.invalid',
        })]
        with self.assertLogs('portal.email_backend', level='WARNING') as logs:
            with self.assertRaises(MailDeliveryError):
                get_connection().open()
        output = '\n'.join(logs.output)
        self.assertIn('free_credits=300 relay_enabled=False', output)
        self.assertNotIn('private@example.invalid', output)

    def test_send_rejection_or_missing_receipt_is_never_reported_as_delivered(self):
        for result in (reply({'message': 'private-recipient'}, 400), reply({}, 201), requests.Timeout('private')):
            with self.subTest(result=type(result).__name__):
                self.session.reset_mock()
                self.session.request.side_effect = [reply(FREE_ACCOUNT), reply(SENDERS), result]
                with self.assertRaises(MailDeliveryError):
                    get_connection().send_messages([self.message()])
                self.assertEqual(self.session.request.call_count, 3)
                self.session.close.assert_called_once()


@override_settings(**EMAIL_SETTINGS)
class HttpsResetFlowTests(ProviderMock, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            'synthetic@example.invalid', email='synthetic@example.invalid', password=None,
        )
        self.identity = GoogleIdentity.objects.create(user=self.user, subject='synthetic-google-subject')

    def post(self, client, route, data, token='', **headers):
        return client.post('/api/' + route, json.dumps(data), content_type='application/json',
                           HTTP_X_CSRFTOKEN=token, **headers)

    def test_android_request_delivers_https_browser_link_and_password_works_in_android_session(self):
        android = Client(enforce_csrf_checks=True)
        csrf = android.get('/api/csrf').json()['csrfToken']
        response = self.post(android, 'password-reset', {'email': self.user.email}, csrf,
                             HTTP_USER_AGENT='Dalvik synthetic Android')
        self.assertEqual(response.status_code, 202)
        payload = self.session.request.call_args.kwargs['json']
        link = payload['textContent']
        self.assertTrue(link.startswith('https://kiwikind.example.invalid/#reset='))
        token = link.split('#reset=')[1]
        self.assertEqual(signing.loads(token, salt='reset')['id'], self.user.pk)
        browser = Client(enforce_csrf_checks=True)
        browser_csrf = browser.get('/api/csrf').json()['csrfToken']
        password = 'Synthetic-Kowhai-HTTPS-641!'
        self.assertEqual(self.post(browser, 'password-reset/confirm',
                                   {'token': token, 'password': password}, browser_csrf).status_code, 200)
        self.assertEqual(self.post(android, 'login', {'email': self.user.email, 'password': password}, csrf).status_code, 200)
        self.identity.refresh_from_db()
        self.assertEqual(self.identity.subject, 'synthetic-google-subject')
        self.assertEqual(self.identity.user_id, self.user.pk)
        self.assertFalse(browser.get('/api/status').json()['intake_enabled'])

    def test_browser_request_uses_same_https_backend_without_client_api_key(self):
        browser = Client(enforce_csrf_checks=True)
        token = browser.get('/api/csrf').json()['csrfToken']
        response = self.post(browser, 'password-reset', {'email': self.user.email}, token)
        self.assertEqual(response.status_code, 202)
        self.assertNotIn(EMAIL_SETTINGS['BREVO_API_KEY'].encode(), response.content)
        self.assertNotIn(b'messageId', response.content)
        self.assertEqual(self.session.request.call_args.args[0], 'POST')

    def test_unconfigured_provider_returns_same_error_before_account_lookup(self):
        with override_settings(BREVO_API_KEY=''), patch('portal.views.User.objects.filter') as lookup:
            known = self.post(self.client, 'password-reset', {'email': self.user.email})
            unknown = self.post(self.client, 'password-reset', {'email': 'unknown@example.invalid'})
        self.assertEqual(known.status_code, 503)
        self.assertEqual(known.content, unknown.content)
        lookup.assert_not_called()

    def test_send_failure_is_private_and_unknown_account_never_triggers_send(self):
        self.session.request.side_effect = [reply(FREE_ACCOUNT), reply(SENDERS), reply({'message': 'private'}, 429)]
        with self.assertLogs('portal.views', level='WARNING') as logs:
            known = self.post(self.client, 'password-reset', {'email': self.user.email})
        self.session.reset_mock()
        self.session.request.side_effect = [reply(FREE_ACCOUNT), reply(SENDERS)]
        unknown = self.post(self.client, 'password-reset', {'email': 'unknown@example.invalid'})
        self.assertEqual(known.status_code, 202)
        self.assertEqual(known.content, unknown.content)
        self.assertEqual(self.session.request.call_count, 2)
        self.assertNotIn('private', ''.join(logs.output))
