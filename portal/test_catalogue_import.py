"""Disposable database tests for MFA-only, draft-only private wholesale CSV import."""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .catalogue_import import FIELDS
from .models import AuditEvent, DraftPlan
from .testing import owner_fixture

ROUTE = '/admin/catalogue/import/'
HEADER = ','.join(FIELDS)
VALID = 'Synthetic UFB 100/20,100,20,Test network,50.00,35.00,65.00,20.00,SYNTHETIC-QUOTE-1'
SECOND = 'Synthetic UFB 500/100,500,100,Test network,70.00,,90.00,,SYNTHETIC-QUOTE-2'


def upload(content, name='private.csv'):
    return SimpleUploadedFile(name, content.encode('utf-8'), content_type='text/csv')


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=True,
                   INTAKE_ENABLED=False, PLAN_PUBLICATION_ENABLED=False)
class PrivateCatalogueImportTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            'temp-owner', 'temp-owner@example.invalid', is_staff=True, is_superuser=True)
        self.customer = get_user_model().objects.create_user(
            'customer', 'customer@example.invalid')

    def login_owner(self):
        owner_fixture(self.client, self.owner)

    def perform(self, csv_data=HEADER+'\n'+VALID+'\n', acknowledge=True, name='private.csv'):
        return self.client.post(ROUTE, {
            'catalogue_csv': upload(csv_data, name=name),
            'confirm_draft_only': 'yes' if acknowledge else 'no',
        })

    def test_anonymous_customer_and_spoofed_staff_must_not_import(self):
        for user in (None, self.customer, self.owner):
            if user:
                self.client.force_login(user)
            response = self.perform()
            self.assertEqual(response.status_code,404)
            self.assertFalse(DraftPlan.objects.filter(name='Synthetic UFB 100/20').exists())
        self.assertFalse(AuditEvent.objects.filter(action='catalogue_csv_import').exists())

    def test_owner_get_never_imports_and_template_has_no_prices(self):
        self.login_owner()
        self.assertContains(self.client.get(ROUTE),'private, unverified')
        template = self.client.get(ROUTE+'?template=1')
        self.assertEqual(template.status_code,200)
        self.assertEqual(template['Content-Type'],'text/csv; charset=utf-8')
        self.assertEqual(template.content.decode(),HEADER+'\n')
        self.assertNotIn('50.00',template.content.decode())
        self.assertFalse(DraftPlan.objects.filter(name='Synthetic UFB 100/20').exists())

    def test_import_only_private_drafts_and_calculates_gst(self):
        self.login_owner()
        self.assertEqual(self.perform().status_code,302)
        row = DraftPlan.objects.get(name='Synthetic UFB 100/20')
        self.assertEqual(row.review_status,'draft')
        self.assertTrue(row.address_specific)
        self.assertEqual(row.wholesale_ex_gst,Decimal('50.00'))
        self.assertEqual(row.wholesale_inc_gst,Decimal('57.50'))
        self.assertEqual(row.setup_inc_gst,Decimal('40.25'))
        self.assertEqual(row.retail_ex_gst,Decimal('65.00'))
        self.assertIsNone(row.verified_at)
        self.assertIsNone(row.valid_until)
        self.assertIsNone(row.approved_by)
        self.assertIsNone(row.approved_at)
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
        with override_settings(PLAN_PUBLICATION_ENABLED=True):
            self.assertEqual(self.client.get('/api/plans').json()['plans'],[])
        self.assertEqual(AuditEvent.objects.filter(action='catalogue_csv_import').count(),1)

    def test_blank_unknown_setup_is_not_turned_into_free(self):
        self.login_owner()
        self.assertEqual(self.perform(HEADER+'\n'+SECOND+'\n').status_code,302)
        row = DraftPlan.objects.get(name='Synthetic UFB 500/100')
        self.assertIsNone(row.setup_ex_gst)
        self.assertIsNone(row.setup_inc_gst)
        self.assertIsNone(row.retail_setup_ex_gst)

    def test_repeat_import_skips_exact_duplicates_and_does_not_rewrite(self):
        self.login_owner()
        self.assertEqual(self.perform().status_code,302)
        item=DraftPlan.objects.get(name='Synthetic UFB 100/20')
        self.assertEqual(self.perform().status_code,302)
        self.assertEqual(DraftPlan.objects.filter(name=item.name).count(),1)
        self.assertEqual(AuditEvent.objects.filter(action='catalogue_csv_import').count(),1)

    def test_existing_private_edited_plan_never_overwritten(self):
        self.login_owner()
        self.perform()
        row=DraftPlan.objects.get(name='Synthetic UFB 100/20')
        row.wholesale_ex_gst=Decimal('60.00')
        row.save(update_fields=['wholesale_ex_gst'])
        self.assertEqual(self.perform().status_code,409)
        row.refresh_from_db()
        self.assertEqual(row.wholesale_ex_gst,Decimal('60.00'))
        self.assertEqual(AuditEvent.objects.filter(action='catalogue_csv_import').count(),1)

    def test_existing_approved_cannot_be_overwritten(self):
        self.login_owner()
        self.perform()
        row=DraftPlan.objects.get(name='Synthetic UFB 100/20')
        row.review_status='approved'
        row.save(update_fields=['review_status'])
        self.assertEqual(self.perform().status_code,409)
        row.refresh_from_db()
        self.assertEqual(row.review_status,'approved')

    def test_atomic_no_partial_rows_when_one_invalid(self):
        self.login_owner()
        response=self.perform(HEADER+'\n'+VALID+'\n'+SECOND.replace('70.00','NaN')+'\n')
        self.assertEqual(response.status_code,400)
        self.assertFalse(DraftPlan.objects.filter(name__startswith='Synthetic UFB').exists())
        self.assertFalse(AuditEvent.objects.filter(action='catalogue_csv_import').exists())

    def test_rows_reject_dangerous_sources_and_missing_quotes(self):
        self.login_owner()
        for value in ('', 'sk_test_should_not_upload', 'token=example'):
            with self.subTest(reference=value):
                response=self.perform(HEADER+'\n'+VALID.replace('SYNTHETIC-QUOTE-1',value)+'\n')
                self.assertEqual(response.status_code,400)
        self.assertFalse(DraftPlan.objects.filter(name__startswith='Synthetic UFB').exists())

    def test_bad_gst_amount_headers_duplicate_name_and_too_many_rows(self):
        self.login_owner()
        bad=[HEADER+'\n'+VALID.replace('50.00','50.001')+'\n',
             HEADER+',unknown\n'+VALID+',extra\n',
             HEADER+'\n'+VALID+'\n'+VALID+'\n',
             HEADER+'\n'+VALID.replace('100,20','100000,20')+'\n',
             HEADER+'\n'+VALID.replace('50.00','-10.00')+'\n',
             HEADER+'\n'+VALID.replace('Synthetic UFB 100/20','=FORMULA')+'\n',
             HEADER+'\n'+VALID.replace(',Test network,',',Network,Unexpected,')+'\n',
             HEADER+'\n'+SECOND+'\n'*100 + '\n'.join([VALID.replace('100/20',f'{x}/20') for x in range(51)])]
        for data in bad:
            with self.subTest(sample=data[:25]):
                self.assertNotEqual(self.perform(data).status_code,302)
        self.assertFalse(DraftPlan.objects.filter(name__startswith='Synthetic UFB').exists())

    def test_requires_explicit_consent_and_rejects_non_csv_and_oversize(self):
        self.login_owner()
        self.assertEqual(self.perform(acknowledge=False).status_code,400)
        self.assertEqual(self.perform(name='private.pdf').status_code,400)
        self.assertEqual(self.perform(HEADER+'\n'+VALID+(' '*101000)).status_code,400)
        self.assertFalse(DraftPlan.objects.filter(name='Synthetic UFB 100/20').exists())

    def test_owner_mfa_expired_cannot_import(self):
        self.login_owner()
        session=self.client.session;session.pop('otp_device_id');session.save()
        self.assertEqual(self.perform().status_code,404)
        self.assertFalse(DraftPlan.objects.filter(name='Synthetic UFB 100/20').exists())

    def test_csrf_protection_is_enforced_on_upload(self):
        client=Client(enforce_csrf_checks=True)
        owner_fixture(client,self.owner)
        response=client.post(ROUTE,{
            'catalogue_csv':upload(HEADER+'\n'+VALID+'\n'), 'confirm_draft_only':'yes'})
        self.assertEqual(response.status_code,403)
        self.assertFalse(DraftPlan.objects.filter(name='Synthetic UFB 100/20').exists())
