"""Synthetic provider tests: never uses cards or contacts Stripe."""
import hashlib
import hmac
import json
import os
import time
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from portal.testing import owner_fixture
from . import live_gateway as gateway
from .live_models import OneDollarVerification


ENV = {
    'KIWIKIND_OWNER_DOLLAR_TEST_ENABLED': '1',
    'STRIPE_LIVE_SECRET_KEY': 'rk_live_synthetic',
    'STRIPE_LIVE_ACCOUNT_ID': 'acct_synthetic',
    'STRIPE_LIVE_WEBHOOK_SECRET': 'whsec_synthetic',
}


@override_settings(
    ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True, PAGES_ENABLED=True,
    PUBLIC_ORIGIN='https://kiwikind.example.invalid',
    PAGES_URL='https://frymastercheese.github.io/kiwikind-broadband-website/')
class OneDollarTests(TestCase):
    def setUp(self):
        active = patch.dict(os.environ, ENV)
        active.start()
        self.addCleanup(active.stop)
        U = get_user_model()
        self.owner = U.objects.create_user('synthetic-owner', is_staff=True, is_superuser=True)
        owner_fixture(self.client, self.owner)
        self.customer = U.objects.create_user('synthetic-customer', 'customer@example.invalid')
        self.api = MagicMock()
        stub = patch('payments.live_gateway.client', return_value=self.api)
        stub.start()
        self.addCleanup(stub.stop)
        self.session = None

        def create(params, **kwargs):
            self.session = {
                'id': 'cs_live_owner_dollar_synthetic',
                'object': 'checkout.session', 'livemode': True,
                'mode': 'payment', 'amount_total': 100,
                'currency': 'nzd', 'subscription': None, 'status': 'open',
                'payment_status': 'unpaid', 'payment_intent': None,
                'client_reference_id': params['client_reference_id'],
                'metadata': params['metadata'],
                'url': 'https://checkout.stripe.com/c/pay/cs_live_owner_dollar_synthetic',
            }
            return dict(self.session)

        self.api.v1.checkout.sessions.create.side_effect = create
        self.api.v1.checkout.sessions.retrieve.side_effect = lambda _id: dict(self.session)
        self.api.v1.payment_intents.retrieve.side_effect = lambda identifier: {
            'id': identifier, 'object': 'payment_intent', 'livemode': True,
            'currency': 'nzd', 'amount': 100, 'amount_received': 100,
            'status': 'succeeded',
            'metadata': {'kiwikind_owner_one_dollar': str(OneDollarVerification.objects.get().pk)},
        }

    def post(self, data=None):
        return self.client.post('/api/owner/dollar-verification/checkout',
            json.dumps(data if data is not None else {'confirm_one_time_live_nzd_1': True}),
            content_type='application/json')

    def hook(self, kind, obj, event_id=None, **change):
        event = {'id': event_id or 'evt_' + uuid.uuid4().hex, 'livemode': True,
            'api_version': gateway.API_VERSION, 'type': kind, 'data': {'object': obj}}
        event.update(change)
        body = json.dumps(event).encode()
        stamp = int(time.time())
        sig = hmac.new(ENV['STRIPE_LIVE_WEBHOOK_SECRET'].encode(),
            str(stamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
        return self.client.post('/api/payments/webhook', body,
            content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={stamp},v1={sig}')

    def paid(self):
        self.assertEqual(self.post().status_code, 200)
        self.session.update(status='complete', payment_status='paid', payment_intent='pi_synthetic')
        return self.hook('checkout.session.completed', self.session)

    def test_only_authenticated_owner_with_google_mfa_can_view_or_pay(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/owner/dollar-verification').status_code, 401)
        self.assertEqual(self.post().status_code, 401)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/api/owner/dollar-verification').status_code, 403)
        self.assertEqual(self.post().status_code, 403)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_disabled_by_default_and_cannot_spend(self):
        with patch.dict(os.environ, {'KIWIKIND_OWNER_DOLLAR_TEST_ENABLED': '0'}):
            result = self.client.get('/api/owner/dollar-verification')
            self.assertFalse(result.json()['enabled'])
            self.assertEqual(self.post().status_code, 503)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_consent_cannot_set_amount_or_recurring(self):
        for body in ({}, {'confirm_one_time_live_nzd_1': False},
                     {'confirm_one_time_live_nzd_1': True, 'amount_cents': 1},
                     {'confirm_one_time_live_nzd_1': True, 'mode': 'subscription'}):
            self.assertEqual(self.post(body).status_code, 400)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.cookies = self.client.cookies
        self.assertEqual(client.post('/api/owner/dollar-verification/checkout',
            json.dumps({'confirm_one_time_live_nzd_1': True}),
            content_type='application/json').status_code, 403)
        self.api.v1.checkout.sessions.create.assert_not_called()

    def test_fixed_one_time_amount_and_idempotent_checkout(self):
        first = self.post()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['amount_cents'], 100)
        self.assertFalse(first.json()['recurring'])
        self.assertEqual(self.post().status_code, 200)
        self.api.v1.checkout.sessions.create.assert_called_once()
        params = self.api.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params['mode'], 'payment')
        self.assertEqual(params['line_items'][0]['price_data']['unit_amount'], 100)
        self.assertNotIn('recurring', params['line_items'][0]['price_data'])
        self.assertNotIn('subscription_data', params)
        self.assertIn('owner.html', params['success_url'])
        self.assertEqual(OneDollarVerification.objects.count(), 1)

    def test_provider_cannot_change_amount(self):
        original = self.api.v1.checkout.sessions.create.side_effect
        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            result['amount_total'] = 500
            return result
        self.api.v1.checkout.sessions.create.side_effect = altered
        self.assertEqual(self.post().status_code, 409)

    def test_signed_webhook_confirmed_and_replay_ignored(self):
        self.assertEqual(self.paid().status_code, 200)
        row = OneDollarVerification.objects.get()
        self.assertEqual((row.state, row.payment_intent_id), ('paid', 'pi_synthetic'))
        duplicate = self.hook('checkout.session.completed', self.session, event_id='evt_same')
        self.assertEqual(duplicate.status_code, 200)
        again = self.hook('checkout.session.completed', self.session, event_id='evt_same')
        self.assertTrue(again.json()['duplicate'])
        self.assertEqual(self.post().status_code, 409)

    def test_webhook_rejects_invalid_signature_and_not_live(self):
        self.assertEqual(self.client.post('/api/payments/webhook', '{}',
            content_type='application/json').status_code, 400)
        self.assertEqual(self.post().status_code, 200)
        self.session.update(status='complete', payment_status='paid', payment_intent='pi_synthetic')
        self.assertEqual(self.hook('checkout.session.completed', self.session, livemode=False).status_code, 400)
        self.assertNotEqual(OneDollarVerification.objects.get().state, 'paid')

    def test_refund_reconciles_separately_from_subscriptions(self):
        self.assertEqual(self.paid().status_code, 200)
        charge = {'id': 'ch_synthetic', 'object': 'charge', 'livemode': True,
            'currency': 'nzd', 'amount': 100, 'payment_intent': 'pi_synthetic',
            'amount_refunded': 100}
        self.api.v1.charges.retrieve.return_value = dict(charge)
        self.assertEqual(self.hook('charge.refunded', charge).status_code, 200)
        row = OneDollarVerification.objects.get()
        self.assertEqual((row.state, row.refunded_cents), ('refunded', 100))
        self.assertEqual(self.post().status_code, 409)
