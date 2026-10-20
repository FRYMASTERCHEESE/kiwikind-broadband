from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import DraftPlan
from .testing import owner_fixture


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True, PLAN_PUBLICATION_ENABLED=False)
class CatalogueTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('kiwikind-owner-admin',
            'kiwikindbroadband@gmail.com', is_staff=True, is_superuser=True)
        owner_fixture(self.client, self.owner)

    def approved(self, **changes):
        values = dict(name='Synthetic general offer', download_mbps=500, upload_mbps=100,
            wholesale_ex_gst=Decimal('60.00'), wholesale_inc_gst=Decimal('69.00'),
            setup_ex_gst=Decimal('35.00'), setup_inc_gst=Decimal('40.25'),
            retail_ex_gst=Decimal('80.00'), retail_setup_ex_gst=Decimal('40.00'),
            network='Synthetic network', source_reference='private-supplier-quote',
            verified_at=timezone.now(), valid_until=timezone.localdate()+timedelta(days=1),
            address_specific=False, review_status='approved', approved_at=timezone.now(),
            approved_by=self.owner)
        values.update(changes)
        return DraftPlan.objects.create(**values)

    def test_quote_is_private_address_specific_unapproved(self):
        quote = DraftPlan.objects.get(name='Direct UFB 500/100 — address-specific quote')
        self.assertEqual(quote.wholesale_ex_gst, Decimal('69.92'))
        self.assertEqual(quote.wholesale_inc_gst, Decimal('80.41'))
        self.assertEqual(quote.setup_ex_gst, Decimal('35.00'))
        self.assertEqual(quote.setup_inc_gst, Decimal('40.25'))
        self.assertTrue(quote.address_specific)
        self.assertEqual(quote.review_status, 'draft')
        self.assertIsNone(quote.retail_ex_gst)
        self.assertIsNone(quote.approved_by)
        quote.full_clean()
        with override_settings(PLAN_PUBLICATION_ENABLED=True):
            self.assertEqual(self.client.get('/api/plans').json()['plans'], [])

    def test_publication_gate_and_projection_hide_wholesale(self):
        self.approved()
        self.assertEqual(self.client.get('/api/plans').json()['plans'], [])
        with override_settings(PLAN_PUBLICATION_ENABLED=True):
            response = self.client.get('/api/plans')
            plan = response.json()['plans'][0]
            self.assertEqual(plan['retail_monthly_cents'], 9200)
            self.assertEqual(plan['retail_setup_cents'], 4600)
            self.assertNotIn('wholesale', response.content.decode())
            self.assertNotIn('private-supplier-quote', response.content.decode())
            self.assertEqual(plan['address_availability'], 'unverified')
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertNotIn('Access-Control-Allow-Credentials', response)

    @override_settings(PLAN_PUBLICATION_ENABLED=True)
    def test_invalid_unapproved_expired_and_wrong_owner_never_publish(self):
        other = get_user_model().objects.create_superuser('other', 'another@example.invalid', 'SyntheticPass')
        for i, changes in enumerate([{'address_specific': True}, {'review_status': 'draft'},
                {'approved_at': None}, {'approved_by': other}, {'network': ''},
                {'valid_until': timezone.localdate()-timedelta(days=1)}, {'retail_ex_gst': None},
                {'wholesale_inc_gst': Decimal('60.00')}]):
            self.approved(name=f'Synthetic {i}', **changes)
        self.assertEqual(self.client.get('/api/plans').json()['plans'], [])

    def test_gst_mismatch_and_address_specific_approval_rejected(self):
        plan = self.approved(wholesale_inc_gst=Decimal('1.00'))
        with self.assertRaises(ValidationError):
            plan.full_clean()
        plan.wholesale_inc_gst = Decimal('69.00')
        plan.address_specific = True
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_catalogue_management_requires_mfa_and_does_not_open_billing(self):
        self.assertContains(self.client.get('/admin/portal/draftplan/'), 'Price catalogue')
        self.assertFalse(self.client.get('/api/status').json()['billing_enabled'])
        session = self.client.session
        session.pop('otp_device_id')
        session.save()
        self.assertEqual(self.client.get('/admin/portal/draftplan/').status_code, 302)
        self.assertEqual(self.client.post('/admin/portal/draftplan/add/', {'name':'forged'}).status_code, 302)
        self.assertFalse(DraftPlan.objects.filter(name='forged').exists())
