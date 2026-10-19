import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from .models import (Order, Ticket, Invoice, AuditEvent, DraftPlan, AvailabilityEvidence,
                     WholesaleOrder, WholesaleFault, WholesaleEvent)
from .suppliers import SupplierNotConfigured
from .wholesale import price_breakdown, VettaManualSupplier, transition


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=False, INTAKE_ENABLED=False, REGISTRATION_ENABLED=False)
class WholesaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('kiwikind-owner-admin', 'kiwikindbroadband@gmail.com', is_staff=True, is_superuser=True)
        cls.customer = get_user_model().objects.create_user('customer', 'customer@example.invalid')
        cls.other = get_user_model().objects.create_user('other', 'other@example.invalid')

    def setUp(self):
        self.client.force_login(self.owner)
        self.request = RequestFactory().post('/admin/wholesale/')
        self.request.user = self.owner
        self.request.session = {}

    def evidence(self, **overrides):
        values = dict(address='1 Synthetic Test Road', postcode='3400', result='available',
                      source_reference='synthetic-portal-check', checked_at=timezone.now() - timedelta(hours=1),
                      valid_until=timezone.now() + timedelta(days=1), checked_by=self.owner, rehearsal=True)
        values.update(overrides)
        return AvailabilityEvidence.objects.create(**values)

    def plan(self, **overrides):
        values = dict(name='Synthetic test only', wholesale_ex_gst=Decimal('40.00'), retail_ex_gst=Decimal('60.00'),
                      verified_at=timezone.now(), source_reference='synthetic-quote')
        values.update(overrides)
        return DraftPlan.objects.create(**values)

    def case(self, **overrides):
        values = dict(address='1 Synthetic Test Road', postcode='3400', created_by=self.owner,
                      availability=self.evidence(), plan=self.plan())
        values.update(overrides)
        return WholesaleOrder.objects.create(**values)

    def advance(self, case, target, **kwargs):
        values = dict(target=target, revision=case.revision, submission_key=uuid.uuid4(), note='Synthetic check completed', reference='practice-reference')
        values.update(kwargs)
        return transition(self.request, type(case), case.pk, **values)

    def test_gst_uses_exact_decimal_half_up_rounding(self):
        self.assertEqual(price_breakdown('60.00'), {'ex_gst': '60.00', 'gst': '9.00', 'inc_gst': '69.00', 'currency': 'NZD'})
        self.assertEqual(price_breakdown('0.10')['gst'], '0.02')
        self.assertEqual(price_breakdown('0')['inc_gst'], '0.00')
        self.assertIsNone(price_breakdown(None))

    def test_invalid_money_is_rejected(self):
        for value in ['-1', 'NaN', 'Infinity', '1.234', '100000', 'bad', 1.1, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                price_breakdown(value)

    def test_negative_draft_prices_cannot_be_saved_by_admin(self):
        plan = DraftPlan(name='Negative', retail_ex_gst=-1)
        with self.assertRaises(ValidationError): plan.full_clean()

    def test_verified_quote_requires_source_and_past_date(self):
        for source, when in [('', timezone.now()), ('ref', timezone.now() + timedelta(days=1))]:
            with self.assertRaises(ValidationError):
                DraftPlan(name='Bad', source_reference=source, verified_at=when).full_clean()

    def test_owner_dashboard_and_mobile_forms_render(self):
        self.assertContains(self.client.get('/admin/wholesale/'), 'No published retail prices')
        self.assertContains(self.client.get('/admin/'), 'Wholesale preparation dashboard')
        for model in ('draftplan', 'availabilityevidence', 'wholesaleorder', 'wholesalefault'):
            self.assertEqual(self.client.get(f'/admin/portal/{model}/add/').status_code, 200)

    def test_admin_off_denies_every_wholesale_route(self):
        with override_settings(ADMIN_ENABLED=False):
            for path in ['/admin/wholesale/', '/admin/portal/draftplan/', '/admin/portal/wholesaleorder/add/']:
                self.assertEqual(self.client.get(path).status_code, 404)
            with self.assertRaises(PermissionDenied): self.advance(self.case(), 'availability_review')

    def test_customer_staff_and_wrong_superuser_cannot_access_dashboard(self):
        staff = get_user_model().objects.create_user('staff', 'staff@example.invalid', is_staff=True)
        superuser = get_user_model().objects.create_user('other-admin', 'admin@example.invalid', is_staff=True, is_superuser=True)
        for user in [self.customer, staff, superuser]:
            self.client.force_login(user)
            for path in ['/admin/wholesale/', '/admin/portal/draftplan/', '/admin/portal/wholesaleorder/add/']:
                self.assertEqual(self.client.get(path).status_code, 302)
            self.request.user = user
            with self.assertRaises(PermissionDenied):
                transition(self.request, WholesaleOrder, uuid.uuid4(), target='submitted', revision=0, submission_key=uuid.uuid4(), note='not authorised')

    def test_expired_google_owner_proof_cannot_use_wholesale_tools(self):
        with override_settings(OWNER_GOOGLE_ADMIN_ENABLED=True):
            self.assertEqual(self.client.get('/admin/wholesale/').status_code, 302)
            with self.assertRaises(PermissionDenied): self.advance(self.case(), 'availability_review')

    def test_process_post_requires_csrf(self):
        case = self.case()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(f'/admin/portal/wholesaleorder/{case.pk}/process/', {
            'target': 'availability_review', 'revision': 0, 'submission_key': str(uuid.uuid4()), 'note': 'Test'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(WholesaleEvent.objects.exists())

    def test_process_form_records_one_audited_internal_action(self):
        case = self.case()
        response = self.client.post(f'/admin/portal/wholesaleorder/{case.pk}/process/', {
            'target': 'availability_review', 'revision': 0, 'submission_key': str(uuid.uuid4()), 'note': 'Reviewed synthetic address'})
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.state, 'availability_review')
        self.assertEqual(WholesaleEvent.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='wholesale_transition').count(), 1)

    def test_evidence_requires_provenance_and_dates(self):
        evidence = self.evidence(source_reference='', checked_at=None, valid_until=None)
        with self.assertRaises(ValidationError): evidence.full_clean()

    def test_stale_future_mismatched_or_practice_evidence_is_unknown(self):
        case = self.case()
        supplier = VettaManualSupplier()
        for change in [dict(valid_until=timezone.now()-timedelta(seconds=1)),
                       dict(checked_at=timezone.now()+timedelta(days=1)), dict(address='2 Different Road'),
                       dict(postcode='9999'), dict(source_reference=''), dict(result='unknown'), dict(rehearsal=False)]:
            with self.subTest(change=change):
                evidence = self.evidence(**change)
                self.assertIsNone(supplier.check_evidence(case, evidence, practice=True).available)
        self.assertIsNone(supplier.check_evidence(case, case.availability).available)
        self.assertTrue(supplier.check_evidence(case, case.availability, practice=True).available)

    def test_manual_supplier_never_calls_remote_services(self):
        supplier = VettaManualSupplier()
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Network must not be used')):
            self.assertIsNone(supplier.check_address('any address', '3400').available)
            for method in ['submit_order', 'get_order', 'cancel_order', 'report_fault']:
                with self.assertRaises(SupplierNotConfigured): getattr(supplier, method)('synthetic')

    def test_rehearsal_order_can_exercise_full_workflow_without_customer_records(self):
        case = self.case()
        for state in ['availability_review', 'quote_review', 'ready', 'submitted', 'provisioning', 'active']:
            case = self.advance(case, state)
        self.assertEqual(case.revision, 6)
        self.assertEqual(case.events.count(), 6)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_real_preparation_stops_before_submission_even_with_verified_quote(self):
        customer_request = Order.objects.create(user=self.customer, address='1 Synthetic Test Road', postcode='3400', contact_name='Synthetic')
        case = self.case(rehearsal=False, customer_request=customer_request)
        case.availability.rehearsal=False
        case.availability.save()
        for state in ['availability_review', 'quote_review', 'ready']:
            case = self.advance(case, state)
        with self.assertRaisesMessage(ValidationError, 'Live supplier processing is disabled'):
            self.advance(case, 'submitted')
        self.assertEqual(case.events.count(), 3)
        customer_request.refresh_from_db()
        self.assertEqual(customer_request.status, 'requested')

    def test_cancelled_customer_request_cannot_be_processed(self):
        order = Order.objects.create(user=self.customer, address='1 Synthetic Test Road', postcode='3400', contact_name='Synthetic', status='cancelled')
        case = self.case(customer_request=order, rehearsal=False)
        with self.assertRaises(ValidationError): self.advance(case, 'availability_review')
        self.assertEqual(self.advance(case, 'cancelled').state, 'cancelled')

    def test_practice_cannot_link_a_real_customer(self):
        order = Order.objects.create(user=self.customer, address='1 Synthetic Test Road', postcode='3400', contact_name='Synthetic')
        with self.assertRaises(ValidationError): self.case(customer_request=order).full_clean()

    def test_skip_stages_and_stale_revisions_do_not_change_state(self):
        case = self.case()
        with self.assertRaises(ValidationError): self.advance(case, 'active')
        case = self.advance(case, 'availability_review')
        with self.assertRaisesMessage(ValidationError, 'another tab'): self.advance(case, 'quote_review', revision=0)
        self.assertEqual(case.events.count(), 1)

    def test_retry_is_idempotent_and_key_cannot_change_payload(self):
        case = self.case(); key = uuid.uuid4()
        self.advance(case, 'availability_review', submission_key=key)
        self.advance(case, 'availability_review', submission_key=key)
        self.assertEqual(case.events.count(), 1)
        with self.assertRaises(ValidationError): self.advance(case, 'availability_review', submission_key=key, note='Changed')

    def test_ready_requires_priced_verified_quote_and_current_evidence(self):
        case = self.case(); case = self.advance(case, 'availability_review'); case = self.advance(case, 'quote_review')
        case.plan.wholesale_ex_gst = None; case.plan.save()
        with self.assertRaises(ValidationError): self.advance(case, 'ready')
        case.plan.wholesale_ex_gst = 40; case.plan.save()
        case.availability.valid_until = timezone.now()-timedelta(minutes=1); case.availability.save()
        with self.assertRaises(ValidationError): self.advance(case, 'ready')

    def test_unavailable_address_cannot_advance(self):
        case = self.case(); case.availability.result = 'unavailable'; case.availability.save()
        case = self.advance(case, 'availability_review')
        with self.assertRaises(ValidationError): self.advance(case, 'quote_review')

    def test_rehearsal_fault_requires_diagnostics_and_tracks_resolution(self):
        case = WholesaleFault.objects.create(summary='Synthetic fault', created_by=self.owner)
        with self.assertRaises(ValidationError): self.advance(case, 'ready')
        case.service_reference='practice-service'; case.diagnostics='Synthetic router and line checks'; case.save()
        for stage in ['ready', 'escalated', 'investigating', 'resolved', 'closed']: case=self.advance(case, stage)
        self.assertEqual(case.events.count(), 5)

    def test_real_fault_cannot_be_escalated_and_does_not_change_ticket(self):
        ticket = Ticket.objects.create(user=self.customer, subject='Synthetic', category='support')
        case = WholesaleFault.objects.create(ticket=ticket, rehearsal=False, summary='Test', service_reference='ref', diagnostics='Checks', created_by=self.owner)
        case=self.advance(case, 'ready')
        with self.assertRaises(ValidationError): self.advance(case, 'escalated')
        ticket.refresh_from_db(); self.assertEqual(ticket.status, 'open')

    def test_private_support_categories_cannot_be_escalated(self):
        for category in ['privacy', 'complaint']:
            ticket = Ticket.objects.create(user=self.customer, subject='Private', category=category)
            with self.assertRaises(ValidationError):
                WholesaleFault(ticket=ticket, rehearsal=False, summary='Test', created_by=self.owner).full_clean()

    def test_customer_projection_is_read_only_owned_and_excludes_practice_and_notes(self):
        order = Order.objects.create(user=self.customer, address='1 Synthetic Test Road', postcode='3400', contact_name='Synthetic')
        self.case(customer_request=order, rehearsal=False)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/connection-progress').json()['orders'], [])
        self.client.force_login(self.customer)
        data = self.client.get('/api/connection-progress').json()
        self.assertEqual(len(data['orders']), 1)
        self.assertFalse(data['live_orders_enabled']); self.assertFalse(data['payments_enabled'])
        self.assertNotIn('synthetic-quote', json.dumps(data)); self.assertNotIn('Synthetic Test Road', json.dumps(data))
        self.assertEqual(self.client.post('/api/connection-progress', {}).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get('/api/connection-progress').status_code, 401)

    def test_two_device_sessions_see_same_preparation(self):
        order = Order.objects.create(user=self.customer, address='1 Synthetic Test Road', postcode='3400', contact_name='Synthetic')
        case = self.case(customer_request=order, rehearsal=False)
        web, android = Client(), Client()
        for client in [web, android]: client.force_login(self.customer)
        self.advance(case, 'availability_review')
        self.assertEqual(web.get('/api/connection-progress').json(), android.get('/api/connection-progress').json())

    def test_prelaunch_intake_billing_and_supplier_actions_remain_closed(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post('/api/orders', '{}', content_type='application/json').status_code, 503)
        self.assertEqual(self.client.post('/api/register', '{}', content_type='application/json').status_code, 503)
        self.assertFalse(self.client.get('/api/status').json()['billing_enabled'])
        self.assertEqual(self.client.post('/api/invoices', '{}', content_type='application/json').status_code, 405)
        self.assertFalse(Order.objects.exists()); self.assertFalse(Invoice.objects.exists())

    def test_stale_admin_edit_cannot_overwrite_newer_workflow_status(self):
        case = self.case()
        payload = {'address': case.address, 'postcode': case.postcode, 'plan': case.plan_id,
                   'availability': case.availability_id, 'edit_revision': 0, '_save': 'Save'}
        self.advance(case, 'availability_review')
        response = self.client.post(f'/admin/portal/wholesaleorder/{case.pk}/change/', payload)
        self.assertContains(response, 'Reload before saving')
        case.refresh_from_db(); self.assertEqual(case.state, 'availability_review'); self.assertEqual(case.revision, 1)

    def test_admin_draft_edit_advances_revision_and_keeps_classification(self):
        case = self.case()
        response = self.client.post(f'/admin/portal/wholesaleorder/{case.pk}/change/', {
            'address': case.address, 'postcode': case.postcode, 'plan': case.plan_id, 'availability': case.availability_id,
            'edit_revision': 0, 'rehearsal': False, 'state': 'active', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.state, 'draft'); self.assertTrue(case.rehearsal); self.assertEqual(case.revision, 1)

    def test_portal_evidence_and_history_cannot_be_edited_or_deleted(self):
        case = self.case(); case = self.advance(case, 'availability_review')
        event = case.events.get()
        for model, pk in [('availabilityevidence', case.availability_id), ('wholesaleevent', event.pk)]:
            self.assertEqual(self.client.post(f'/admin/portal/{model}/{pk}/change/', {'note':'tampered'}).status_code, 403)
            self.assertEqual(self.client.post(f'/admin/portal/{model}/{pk}/delete/', {'post':'yes'}).status_code, 403)
