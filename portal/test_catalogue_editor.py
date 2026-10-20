"""Synthetic-only coverage for the private manual catalogue editor."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .catalogue_forms import CataloguePlanForm, catalogue_readiness
from .models import AuditEvent, DraftPlan
from .testing import owner_fixture


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True, PLAN_PUBLICATION_ENABLED=False)
class CatalogueEditorTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            'kiwikind-owner-admin', 'kiwikindbroadband@gmail.com', is_staff=True, is_superuser=True)
        owner_fixture(self.client, self.owner)

    def data(self, **changes):
        data = dict(name='Synthetic editor quote', download_mbps='250', upload_mbps='50',
            wholesale_ex_gst='40.01', setup_ex_gst='10.00', address_specific='on',
            source_reference='synthetic-private-quote', review_status='draft', notes='Synthetic only.')
        data.update(changes)
        return data

    def general_data(self, **changes):
        data = self.data(network='Synthetic LFC', retail_ex_gst='70.00', retail_setup_ex_gst='20.00',
            verified_at=timezone.now().isoformat(), valid_until=(timezone.localdate()+timedelta(days=7)).isoformat(),
            review_status='approved', confirm_current_approval='on')
        data.pop('address_specific')
        data.update(changes)
        return data

    def plan(self):
        return DraftPlan.objects.create(name='Synthetic existing quote', download_mbps=250, upload_mbps=50,
            wholesale_ex_gst=Decimal('40.01'), wholesale_inc_gst=Decimal('46.01'),
            setup_ex_gst=Decimal('10.00'), setup_inc_gst=Decimal('11.50'),
            source_reference='synthetic-private-quote')

    def test_server_derives_gst_and_ignores_forged_gross(self):
        form = CataloguePlanForm(self.data(wholesale_inc_gst='0.01', setup_inc_gst='999.00'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.wholesale_inc_gst, Decimal('46.01'))
        self.assertEqual(form.instance.setup_inc_gst, Decimal('11.50'))
        self.assertIsNone(form.instance.retail_ex_gst)
        self.assertIsNone(form.instance.approved_at)

    def test_missing_costs_stay_unknown_not_zero(self):
        form = CataloguePlanForm(self.data(wholesale_ex_gst='', setup_ex_gst=''))
        self.assertTrue(form.is_valid(), form.errors)
        for name in ('wholesale_ex_gst', 'wholesale_inc_gst', 'setup_ex_gst', 'setup_inc_gst'):
            self.assertIsNone(getattr(form.instance, name))

    def test_zero_setup_is_distinct_from_unknown(self):
        form = CataloguePlanForm(self.data(setup_ex_gst='0.00'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.setup_inc_gst, Decimal('0.00'))

    def test_negative_nonfinite_overprecise_and_overflow_rejected(self):
        for value in ('-1.00', 'NaN', 'Infinity', '1.001', '99999.99'):
            with self.subTest(value=value):
                form = CataloguePlanForm(self.data(wholesale_ex_gst=value))
                self.assertFalse(form.is_valid())

    def test_approval_requires_current_explicit_confirmation(self):
        form = CataloguePlanForm(self.general_data(confirm_current_approval=''))
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_current_approval', form.errors)

    def test_confirmed_general_offer_validates_without_publishing(self):
        form = CataloguePlanForm(self.general_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(self.client.get('/api/plans').json()['plans'], [])

    def test_confirmation_does_not_bypass_address_specific_guard(self):
        form = CataloguePlanForm(self.general_data(address_specific='on'))
        self.assertFalse(form.is_valid())

    def test_confirmation_does_not_bypass_missing_network_or_expiry(self):
        for values in ({'network': ''}, {'valid_until': ''},
                {'valid_until': (timezone.localdate()-timedelta(days=1)).isoformat()},
                {'verified_at': (timezone.now()+timedelta(days=1)).isoformat()}):
            with self.subTest(values=values):
                self.assertFalse(CataloguePlanForm(self.general_data(**values)).is_valid())

    def test_checkbox_cannot_ambiguously_approve_a_draft(self):
        form = CataloguePlanForm(self.data(confirm_current_approval='on'))
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_current_approval', form.errors)

    def test_existing_quote_requires_version(self):
        plan = self.plan()
        form = CataloguePlanForm(self.data(name=plan.name), instance=plan)
        self.assertFalse(form.is_valid())
        self.assertIn('edit version', str(form.non_field_errors()))

    def test_matching_version_allows_private_edit_and_recalculates_gst(self):
        plan = self.plan()
        form = CataloguePlanForm(self.data(name=plan.name, wholesale_ex_gst='50.00',
            expected_updated_at=plan.updated_at.isoformat()), instance=plan)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.wholesale_inc_gst, Decimal('57.50'))

    def test_stale_tab_cannot_overwrite_newer_quote(self):
        plan = self.plan()
        version = plan.updated_at.isoformat()
        plan.notes = 'Newer private evidence'
        plan.save()
        form = CataloguePlanForm(self.data(name=plan.name, expected_updated_at=version), instance=plan)
        self.assertFalse(form.is_valid())
        plan.refresh_from_db()
        self.assertEqual(plan.notes, 'Newer private evidence')

    def test_admin_template_contains_private_checklist_and_version(self):
        plan = self.plan()
        response = self.client.get(f'/admin/portal/draftplan/{plan.pk}/change/')
        self.assertContains(response, 'Publication blockers and evidence checklist')
        self.assertContains(response, 'expected_updated_at')
        self.assertContains(response, 'confirm_current_approval')
        self.assertContains(response, 'Plan publication is disabled')

    def test_admin_creates_audited_draft_without_public_plan_or_billing(self):
        response = self.client.post('/admin/portal/draftplan/add/', self.data())
        self.assertEqual(response.status_code, 302)
        plan = DraftPlan.objects.get(name='Synthetic editor quote')
        self.assertEqual(plan.review_status, 'draft')
        self.assertIsNone(plan.approved_at)
        self.assertIsNone(plan.approved_by_id)
        self.assertTrue(AuditEvent.objects.filter(action='catalogue_draft', reference=f'plan:{plan.pk}', actor=self.owner).exists())
        self.assertFalse(self.client.get('/api/status').json()['billing_enabled'])
        with override_settings(PLAN_PUBLICATION_ENABLED=True):
            self.assertEqual(self.client.get('/api/plans').json()['plans'], [])

    def test_admin_stale_post_leaves_quote_and_audit_unchanged(self):
        plan = self.plan()
        version = plan.updated_at.isoformat()
        plan.notes = 'Keep newer note'
        plan.save()
        before = AuditEvent.objects.count()
        response = self.client.post(f'/admin/portal/draftplan/{plan.pk}/change/',
            self.data(name=plan.name, expected_updated_at=version))
        self.assertContains(response, 'Reload the page before saving')
        plan.refresh_from_db()
        self.assertEqual(plan.notes, 'Keep newer note')
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_other_account_cannot_read_or_write_catalogue(self):
        other = get_user_model().objects.create_user('catalogue-outsider', 'other@example.invalid', is_staff=True, is_superuser=True)
        self.client.force_login(other)
        response = self.client.get('/admin/portal/draftplan/')
        self.assertIn(response.status_code, (302, 403, 404))
        response = self.client.post('/admin/portal/draftplan/add/', self.data())
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(DraftPlan.objects.filter(name='Synthetic editor quote').exists())

    def test_readiness_lists_unknowns_without_inventing_prices(self):
        text = catalogue_readiness(self.plan())
        self.assertIn('Address-specific', text)
        self.assertIn('validity is unknown', text)
        self.assertIn('Retail monthly/setup prices have not been chosen', text)
        self.assertIn('does not submit a Vetta order', text)

    def test_new_quote_checklist_stays_private(self):
        self.assertIn('New private draft', catalogue_readiness(DraftPlan()))
