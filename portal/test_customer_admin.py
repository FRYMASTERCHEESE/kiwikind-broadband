from .testing import owner_fixture, owner_request
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from .models import AuditEvent, GoogleIdentity


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True)
class CustomerAdminTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('operator', 'kiwikindbroadband@gmail.com', 'synthetic-password')
        self.customer = User.objects.create_user('customer@example.invalid', 'customer@example.invalid', 'synthetic-password')
        self.device = owner_fixture(self.client, self.owner)
        self.url = f'/admin/portal/customer/{self.customer.pk}/change/'

    def test_directory_search_and_owner_exclusion(self):
        response = self.client.get('/admin/portal/customer/')
        self.assertContains(response, 'customer@example.invalid')
        self.assertNotContains(response, 'href="/admin/portal/customer/' + str(self.owner.pk) + '/change/"')
        self.assertNotContains(self.client.get('/admin/portal/customer/?q=absent'), 'customer@example.invalid')
        self.assertEqual(self.client.get(f'/admin/portal/customer/{self.owner.pk}/change/').status_code, 302)

    def test_safe_edit_ignores_identity_and_privilege_fields_and_audits(self):
        response = self.client.post(self.url, {'first_name': 'Test', 'last_name': 'Customer',
            'is_active': 'on', 'email': 'attacker@example.invalid', 'is_superuser': 'on',
            'is_staff': 'on', 'password': 'forged', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Test')
        self.assertEqual(self.customer.email, 'customer@example.invalid')
        self.assertFalse(self.customer.is_staff or self.customer.is_superuser)
        self.assertTrue(self.customer.check_password('synthetic-password'))
        self.assertTrue(AuditEvent.objects.filter(action='customer_account_updated', actor=self.owner).exists())

    def test_deactivation_blocks_existing_customer_session(self):
        from django.test import Client
        customer_client = Client()
        customer_client.force_login(self.customer)
        self.assertEqual(customer_client.get('/api/me').status_code, 200)
        self.client.post(self.url, {'first_name': '', 'last_name': '', '_save': 'Save'})
        self.assertEqual(customer_client.get('/api/me').status_code, 401)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.client.post(self.url, {'first_name': '', 'last_name': '', 'is_active': 'on', '_save': 'Save'})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_no_creation_deletion_or_customer_access(self):
        self.assertEqual(self.client.get('/admin/portal/customer/add/').status_code, 403)
        self.assertEqual(self.client.post(f'/admin/portal/customer/{self.customer.pk}/delete/').status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/admin/portal/customer/').status_code, 302)

    def test_links_and_google_identity_are_read_only(self):
        GoogleIdentity.objects.create(user=self.customer, subject='synthetic-google-subject')
        response = self.client.get(self.url)
        self.assertContains(response, 'Google and password')
        for model in ['order', 'ticket', 'invoice', 'privacyrequest']:
            self.assertContains(response, f'/admin/portal/{model}/?user__id__exact={self.customer.pk}')
