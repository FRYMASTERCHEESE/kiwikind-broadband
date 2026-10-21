"""Only disposable test databases may exercise the private owner readiness pages."""
from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import Client, TestCase, override_settings
from .models import Provider, AuditEvent, DraftPlan, WholesaleOrder
from .testing import owner_fixture
from payments.models import TestAgreement, TestInvoice, TestEvent

PAGE='/admin/launch-readiness/'
POST='/admin/launch-readiness/framework/'

@override_settings(ADMIN_ENABLED=True,OWNER_GOOGLE_ADMIN_ENABLED=True,
                   INTAKE_ENABLED=False,PLAN_PUBLICATION_ENABLED=False,
                   PUBLIC_ORIGIN='https://kiwikind.example.invalid')
class OwnerLaunchReadinessTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user(
            'fake-owner','fake-owner@example.invalid',is_staff=True,is_superuser=True)
        self.stranger=get_user_model().objects.create_user(
            'fake-stranger','fake-stranger@example.invalid',is_staff=True,is_superuser=True)
        self.provider,_=Provider.objects.get_or_create(name='Vetta',defaults={
            'website':'https://vetta.example.invalid','summary':'Synthetic only'})
        self.provider.stage='enquiry_sent'
        self.provider.save(update_fields=['stage'])

    def login(self):
        owner_fixture(self.client,self.owner)

    def test_anonymous_and_forged_staff_denied(self):
        self.assertEqual(self.client.get(PAGE).status_code,404)
        self.assertEqual(self.client.post(POST,{'ack_framework_review':'yes'}).status_code,404)
        for user in (self.stranger,self.owner):
            self.client.force_login(user)
            self.assertEqual(self.client.get(PAGE).status_code,404)
            self.assertEqual(self.client.post(POST,{'ack_framework_review':'yes'}).status_code,404)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.stage,'enquiry_sent')

    def test_private_get_read_only_and_never_leaks_wholesale_amount(self):
        self.login()
        DraftPlan.objects.create(name='Synthetic confidential',source_reference='VERY-SECRET-QUOTE',
                                 wholesale_ex_gst='83.42',retail_ex_gst='99.00')
        response=self.client.get(PAGE)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'private launch readiness')
        self.assertContains(response,'Needs verification')
        self.assertNotContains(response,'VERY-SECRET-QUOTE')
        self.assertNotContains(response,'83.42')
        self.assertNotContains(response,'99.00')
        self.assertIn('no-store',response['Cache-Control'])
        self.assertFalse(AuditEvent.objects.filter(action='supplier_framework_attested').exists())

    def test_owner_consents_once_and_never_opens_customer_sales(self):
        self.login()
        self.assertEqual(self.client.get(POST).status_code,405)
        self.assertEqual(self.client.post(POST,{}).status_code,400)
        first=self.client.post(POST,{'ack_framework_review':'yes'})
        self.assertEqual(first.status_code,302)
        self.assertEqual(first['Location'],PAGE)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.stage,'agreement_recorded')
        self.assertEqual(AuditEvent.objects.filter(action='supplier_framework_attested').count(),1)
        self.assertEqual(self.client.post(POST,{'ack_framework_review':'yes'}).status_code,302)
        self.assertEqual(AuditEvent.objects.filter(action='supplier_framework_attested').count(),1)
        self.assertEqual(WholesaleOrder.objects.count(),0)
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
        self.assertFalse(self.client.get('/api/status').json()['billing_enabled'])
        self.assertContains(self.client.get(PAGE),'Framework stage is already recorded')

    def test_expired_owner_session_denied(self):
        self.login()
        session=self.client.session;session.pop('otp_device_id',None);session.save()
        self.assertEqual(self.client.get(PAGE).status_code,404)
        self.assertEqual(self.client.post(POST,{'ack_framework_review':'yes'}).status_code,404)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.stage,'enquiry_sent')

    def test_csrf_enforced_for_owner(self):
        cli=Client(enforce_csrf_checks=True);owner_fixture(cli,self.owner)
        self.assertEqual(cli.post(POST,{'ack_framework_review':'yes'}).status_code,403)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.stage,'enquiry_sent')

    def test_missing_supplier_never_created(self):
        self.login();self.provider.delete()
        self.assertEqual(self.client.post(POST,{'ack_framework_review':'yes'}).status_code,409)
        self.assertFalse(Provider.objects.filter(name='Vetta').exists())

    def test_realistic_paid_refund_cancellation_evidence_is_recorded(self):
        self.login()
        initial=self.client.get(PAGE)
        self.assertContains(initial,'A paid TEST invoice and signed receipt are not yet both present.')
        agreement=TestAgreement.objects.create(
            user=self.owner,created_by=self.owner,monthly_cents=100,setup_cents=0,
            reviewed=True,subscription_id='sub_synthetic',cancel_at_period_end=True)
        TestInvoice.objects.create(agreement=agreement,provider_id='in_synthetic',
            amount_cents=100,status='paid',payment_intent='pi_synthetic',refunded_cents=100)
        for kind in ('invoice.paid','charge.refunded','customer.subscription.updated'):
            TestEvent.objects.create(id='evt_'+kind.replace('.','_'),kind=kind)
        page=self.client.get(PAGE)
        self.assertContains(page,'Provider-bound TEST invoice and invoice.paid receipt recorded.')
        self.assertContains(page,'Fully refunded TEST invoice')
        self.assertContains(page,'Cancel-at-period-end and subscription.updated receipt')
        self.assertContains(page,'these separate real sandbox lifecycle scenarios remain unverified')

    @override_settings(INTAKE_ENABLED=True,PLAN_PUBLICATION_ENABLED=True)
    def test_public_sales_switch_is_a_warning_not_a_pass(self):
        self.login()
        response=self.client.get(PAGE)
        self.assertContains(response,'WARNING:')
        self.assertContains(response,'is enabled. Investigate')
