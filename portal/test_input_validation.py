import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Ticket, Message


class InputValidationTests(TestCase):
    def test_deeply_nested_json_is_a_client_error(self):
        # Below the body-size cap. Decoder depth limits vary by Python build;
        # either decoding rejection or rejecting the array root must be safe.
        response = self.client.post('/api/login', '[' * 7000 + '0' + ']' * 7000,
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_decoder_errors_are_safe_json_responses(self):
        with patch('portal.views.json.loads', side_effect=RecursionError):
            response = self.client.post('/api/login', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'Invalid JSON request'})
        for body in (b'{', b'\xff'):
            response = self.client.post('/api/login', body, content_type='application/json')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {'error': 'Invalid JSON request'})

    def test_invalid_text_cannot_create_partial_support_records(self):
        user = get_user_model().objects.create_user('synthetic@example.invalid')
        self.client.force_login(user)
        for field in ('subject', 'body'):
            for invalid in ('bad\x00text', 'bad\ud800text'):
                with self.subTest(field=field, invalid=repr(invalid)):
                    payload = {'subject': 'A question', 'category': 'support', 'body': 'Please help'}
                    payload[field] = invalid
                    response = self.client.post('/api/tickets', json.dumps(payload),
                                                content_type='application/json')
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('valid text', response.json()['error'])
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)

    def test_unicode_support_text_remains_supported(self):
        user = get_user_model().objects.create_user('synthetic@example.invalid')
        self.client.force_login(user)
        response = self.client.post('/api/tickets', json.dumps({
            'subject': 'Kia ora, whānau 💚', 'category': 'support',
            'body': 'Tēnā koutou — a connection question.'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Ticket.objects.get().subject, 'Kia ora, whānau 💚')
