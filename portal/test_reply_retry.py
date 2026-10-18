import uuid
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from .models import Ticket, Message, AuditEvent


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=False)
class ReplyRetryTests(TestCase):
    def setUp(self):
        owner = User.objects.create_superuser('operator', 'kiwikindbroadband@gmail.com', 'synthetic-password')
        customer = User.objects.create_user('customer@example.invalid')
        self.ticket = Ticket.objects.create(user=customer, subject='Practice', category='support')
        self.original = Message.objects.create(ticket=self.ticket, author=customer, body='Test question')
        self.client.force_login(owner)
        self.url = f'/admin/portal/ticket/{self.ticket.pk}/change/'
        self.payload = {'status': 'open', 'reply_submission_key': str(uuid.uuid4()),
            'messages-TOTAL_FORMS': '2', 'messages-INITIAL_FORMS': '1',
            'messages-MIN_NUM_FORMS': '0', 'messages-MAX_NUM_FORMS': '1000',
            'messages-0-id': str(self.original.pk), 'messages-0-ticket': str(self.ticket.pk),
            'messages-1-ticket': str(self.ticket.pk), 'messages-1-body': 'Thanks', '_save': 'Save'}

    def test_replaying_submission_creates_one_reply_and_one_reply_audit(self):
        for _ in range(3):
            self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        self.assertEqual(self.ticket.messages.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(action='support_reply').count(), 1)

    def test_fresh_submission_allows_intentional_follow_up(self):
        self.client.post(self.url, self.payload)
        self.payload['reply_submission_key'] = str(uuid.uuid4())
        self.payload['messages-1-body'] = 'Another update'
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        self.assertEqual(self.ticket.messages.count(), 3)

    def test_missing_key_does_not_save_reply(self):
        del self.payload['reply_submission_key']
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 200)
        self.assertEqual(self.ticket.messages.count(), 1)
