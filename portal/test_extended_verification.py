"""Additional prelaunch journeys. Disposable DB and local mail only."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail, signing, serializers
from django.db import connection, close_old_connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings

from .models import GoogleIdentity, PrivacyRequest, RateBucket, Ticket, Message
from .security import limited

User = get_user_model()
OLD = 'Synthetic-Kowhai-River-751!'
NEW = 'Synthetic-Totara-Mountain-937!'

@override_settings(INTAKE_ENABLED=False, ADMIN_ENABLED=False, RESET_EMAIL_UNAVAILABLE=False)
class ExtendedJourneys(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('extended-a@example.invalid', email='extended-a@example.invalid', password=OLD)
        self.bob = User.objects.create_user('extended-b@example.invalid', email='extended-b@example.invalid', password=OLD)

    def post(self, client, route, body):
        token = client.get('/api/csrf').json()['csrfToken']
        return client.post('/api/' + route, json.dumps(body), content_type='application/json', HTTP_X_CSRFTOKEN=token)

    def login(self, user):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client, 'login', {'email':user.email, 'password':OLD}).status_code, 200)
        return client

    def reset_token(self, user):
        user.refresh_from_db()
        return signing.dumps({'id':user.pk, 'token':default_token_generator.make_token(user)}, salt='reset')

    def test_reset_revokes_both_old_sessions_and_keeps_other_account(self):
        web, phone, other = self.login(self.alice), self.login(self.alice), self.login(self.bob)
        self.assertEqual(self.post(Client(enforce_csrf_checks=True), 'password-reset/confirm', {'token':self.reset_token(self.alice), 'password':NEW}).status_code, 200)
        self.assertEqual(web.get('/api/me').status_code, 401)
        self.assertEqual(phone.get('/api/me').status_code, 401)
        self.assertEqual(other.get('/api/me').json()['email'], self.bob.email)
        self.assertEqual(self.post(web, 'login', {'email':self.alice.email, 'password':OLD}).status_code, 401)
        self.assertEqual(self.post(phone, 'login', {'email':self.alice.email, 'password':NEW}).status_code, 200)

    def test_expired_and_tampered_reset_do_not_change_password(self):
        now = time.time()
        with patch('django.core.signing.time.time', return_value=now-3602):
            expired = self.reset_token(self.alice)
        for token in (expired, self.reset_token(self.alice)+'tampered'):
            self.assertEqual(self.post(self.client, 'password-reset/confirm', {'token':token, 'password':NEW}).status_code, 400)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password(OLD))

    def test_server_expired_session_cannot_restore_or_write(self):
        client = self.login(self.alice)
        session = client.session
        session.set_expiry(-1)
        session.save()
        self.assertEqual(client.get('/api/me').status_code, 401)
        self.assertEqual(self.post(client, 'tickets', {'subject':'Expired', 'category':'support', 'body':'Should not store'}).status_code, 401)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_google_only_recovery_then_deletion_queue_preserves_identity(self):
        user = User.objects.create_user('extended-google@example.invalid', email='extended-google@example.invalid', password=None)
        identity = GoogleIdentity.objects.create(user=user, subject='extended-synthetic-subject')
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(self.post(client, 'privacy/deletion', {'password':OLD}).status_code, 403)
        self.assertEqual(self.post(client, 'password-reset', {'email':user.email}).status_code, 202)
        token = mail.outbox[-1].body.split('#reset=')[1].strip()
        self.assertEqual(self.post(client, 'password-reset/confirm', {'token':token, 'password':NEW}).status_code, 200)
        self.assertEqual(self.post(client, 'login', {'email':user.email, 'password':NEW}).status_code, 200)
        self.assertEqual(self.post(client, 'privacy/deletion', {'password':NEW}).status_code, 202)
        self.assertEqual(PrivacyRequest.objects.get(user=user).status, 'received')
        identity.refresh_from_db()
        self.assertEqual(identity.user_id, user.pk)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_switch_account_does_not_expose_previous_export_or_messages(self):
        client = self.login(self.alice)
        ticket = self.post(client, 'tickets', {'subject':'Private Alice', 'category':'privacy', 'body':'Alice-only record'}).json()['id']
        old_session = client.cookies['sessionid'].value
        self.assertEqual(self.post(client, 'logout', {}).status_code, 200)
        replay = Client()
        replay.cookies['sessionid'] = old_session
        self.assertEqual(replay.get('/api/me').status_code, 401)
        self.assertEqual(self.post(client, 'login', {'email':self.bob.email, 'password':OLD}).status_code, 200)
        self.assertEqual(client.get('/api/privacy/export').json()['tickets'], [])
        self.assertEqual(client.get('/api/tickets/'+ticket+'/messages').status_code, 404)
        self.assertEqual(self.post(client, 'tickets/'+ticket+'/messages', {'body':'Intrusion'}).status_code, 404)
        self.assertEqual(Message.objects.count(), 1)

    def test_cross_origin_and_google_callback_csrf_rejected_without_account_creation(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get('/api/csrf').json()['csrfToken']
        self.assertEqual(client.post('/api/login', json.dumps({'email':self.alice.email,'password':OLD}), content_type='application/json', HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://attacker.example.invalid').status_code, 403)
        with patch('portal.views._verified_google_signin') as verifier:
            client.cookies['g_csrf_token'] = 'cookie-value'
            self.assertEqual(client.post('/api/google-callback', {'g_csrf_token':'wrong','credential':'x'*30}).status_code, 403)
            verifier.assert_not_called()
        self.assertEqual(User.objects.count(), 2)

    def test_restored_synthetic_records_preserve_ownership_and_authentication(self):
        # Portable fixture recovery in disposable DB; not a production recovery drill.
        ticket = Ticket.objects.create(user=self.alice, subject='Recovery fixture', category='support')
        ticket_id = ticket.pk
        message = Message.objects.create(ticket=ticket, author=self.alice, body='Restorable synthetic record')
        fixture = serializers.serialize('json', [ticket, message])
        message.delete()
        ticket.delete()
        for row in serializers.deserialize('json', fixture):
            row.save()
        alice, bob = self.login(self.alice), self.login(self.bob)
        self.assertEqual(alice.get(f'/api/tickets/{ticket_id}/messages').json()['messages'][0]['body'], 'Restorable synthetic record')
        self.assertEqual(bob.get(f'/api/tickets/{ticket_id}/messages').status_code, 404)

class ConcurrentRateLimit(TransactionTestCase):
    def burst(self, scope, window):
        if connection.vendor != 'postgresql':
            self.skipTest('Production concurrency must run on disposable PostgreSQL')
        workers = 12
        barrier = Barrier(workers)
        original_save = RateBucket.save
        def delayed_save(bucket, *args, **kwargs):
            # Amplify a real overlapping read/modify/write schedule.
            time.sleep(0.03)
            return original_save(bucket, *args, **kwargs)
        def call(_):
            close_old_connections()
            try:
                request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.83')
                barrier.wait(timeout=15)
                return limited(request, scope, limit=5, seconds=900)
            finally:
                close_old_connections()
        with patch('portal.security.time.time', return_value=window*900), patch.object(RateBucket, 'save', delayed_save):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                denied = list(pool.map(call, range(workers)))
        self.assertEqual(RateBucket.objects.get().count, workers)
        self.assertEqual(sum(denied), workers-5)

    def test_existing_bucket_concurrent_attempts_not_lost(self):
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.83')
        with patch('portal.security.time.time', return_value=900000):
            limited(request, 'existing')
        RateBucket.objects.update(count=0)
        self.burst('existing', 1000)

    def test_first_bucket_concurrent_creation_not_lost(self):
        self.burst('first', 1000)

    def test_concurrent_window_rollover_not_lost(self):
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.83')
        with patch('portal.security.time.time', return_value=899100):
            limited(request, 'rollover')
        self.burst('rollover', 1000)

@override_settings(INTAKE_ENABLED=False)
class ConcurrentAccountActions(TransactionTestCase):
    def burst(self, action):
        if connection.vendor != 'postgresql':
            self.skipTest('Production concurrency must run on disposable PostgreSQL')
        barrier = Barrier(4)
        def call(_):
            close_old_connections()
            try:
                client = Client()
                client.raise_request_exception = False
                barrier.wait(timeout=15)
                return action(client).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(call, range(4)))

    def post(self, client, route, body):
        return client.post('/api/'+route, json.dumps(body), content_type='application/json')

    def test_reset_token_consumed_once_under_concurrency(self):
        user = User.objects.create_user('parallel-reset@example.invalid', password=OLD)
        token = signing.dumps({'id':user.pk,'token':default_token_generator.make_token(user)},salt='reset')
        original = User.set_password
        def delayed(user, raw):
            time.sleep(0.05)
            return original(user, raw)
        with patch.object(User,'set_password',delayed):
            statuses = self.burst(lambda c:self.post(c,'password-reset/confirm',{'token':token,'password':NEW}))
        self.assertEqual(sorted(statuses), [200,400,400,400])

    def test_google_first_login_race_does_not_duplicate_or_return_500(self):
        claims={'iss':'https://accounts.google.com','email_verified':True,'email':'parallel-google@example.invalid','sub':'parallel-synthetic-subject'}
        original = User.save
        def delayed(user,*args,**kwargs):
            if user.pk is None: time.sleep(0.05)
            return original(user,*args,**kwargs)
        with patch.dict(os.environ,{'GOOGLE_WEB_CLIENT_ID':'synthetic-client'}), patch('google.oauth2.id_token.verify_oauth2_token',return_value=claims), patch.object(User,'save',delayed):
            statuses=self.burst(lambda c:self.post(c,'google-login',{'id_token':'synthetic-token-with-required-length'}))
        self.assertTrue(all(s in (200,409) for s in statuses), statuses)
        self.assertEqual(User.objects.count(),1)
        self.assertEqual(GoogleIdentity.objects.count(),1)

    def test_parallel_deletion_requests_remain_one_queue_item(self):
        user=User.objects.create_user('parallel-deletion@example.invalid',password=OLD)
        original = PrivacyRequest.save
        def delayed(request,*args,**kwargs):
            time.sleep(0.05)
            return original(request,*args,**kwargs)
        def action(client):
            client.force_login(user)
            return self.post(client,'privacy/deletion',{'password':OLD})
        with patch.object(PrivacyRequest,'save',delayed):
            statuses=self.burst(action)
        self.assertEqual(statuses,[202]*4)
        self.assertEqual(PrivacyRequest.objects.count(),1)
