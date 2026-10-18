from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from .models import Provider, AuditEvent


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=False)
class ProviderAdminTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('operator', 'kiwikindbroadband@gmail.com', 'synthetic-password')
        self.client.force_login(self.owner)

    def test_shortlist_and_instructions_present(self):
        self.assertEqual(Provider.objects.count(), 4)
        self.assertFalse(Provider.objects.exclude(stage='not_contacted').exists())
        response = self.client.get('/admin/portal/provider/')
        self.assertEqual(response.status_code, 200)
        for text in ['Devoli', 'Wholesale Group', '2talk', 'Vetta', 'steps towards launch',
                     '100% operational', 'does not activate', 'free']:
            self.assertContains(response, text)

    def test_progress_notes_audited_without_enabling_services(self):
        provider = Provider.objects.get(name='Devoli')
        response = self.client.post(f'/admin/portal/provider/{provider.pk}/change/', {
            'name': provider.name, 'website': provider.website, 'summary': provider.summary,
            'stage': 'enquiry_sent', 'notes': 'Synthetic example note', 'contact_date': '', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AuditEvent.objects.filter(action='provider_updated', actor=self.owner).exists())
        self.assertContains(self.client.get(f'/admin/portal/provider/{provider.pk}/change/'), 'Synthetic example note')
        self.assertEqual(self.client.get('/api/status').json()['live_services'], False)
        self.assertEqual(self.client.get('/api/status').json()['billing_enabled'], False)

    def test_customer_and_anonymous_cannot_access(self):
        self.client.logout()
        self.assertEqual(self.client.get('/admin/portal/provider/').status_code, 302)
        self.client.force_login(User.objects.create_user('customer@example.invalid'))
        self.assertEqual(self.client.get('/admin/portal/provider/').status_code, 302)
