import time
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from .models import PrivateCatalogueRelease
from .test_private_catalogue import sample
from .testing import owner_fixture


@override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True)
class CatalogueReviewTests(TestCase):
    def setUp(self):
        self.release=PrivateCatalogueRelease.objects.create(payload=sample())
        self.list_url='/api/owner/catalogue-releases'
        self.detail_url=f'{self.list_url}/{self.release.pk}'

    def owner(self):
        owner=get_user_model().objects.create_superuser('synthetic-owner','synthetic@example.invalid')
        owner_fixture(self.client,owner)

    def test_no_source_prices_without_owner_google_and_mfa(self):
        for url in [self.list_url,self.detail_url]:self.assertEqual(self.client.get(url).status_code,403)
        customer=get_user_model().objects.create_superuser('customer','customer@example.invalid')
        self.client.force_login(customer)
        for url in [self.list_url,self.detail_url]:self.assertEqual(self.client.get(url).status_code,403)

    def test_owner_sees_source_and_same_retail_policy_without_mutating_release(self):
        self.owner();before=self.release.checksum
        listed=self.client.get(self.list_url)
        self.assertEqual(listed.status_code,200);self.assertEqual(listed['Cache-Control'],'no-store')
        self.assertNotIn('payload',listed.json()['releases'][0])
        response=self.client.get(self.detail_url)
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertFalse(data['can_publish'])
        self.assertEqual(data['products'][0]['source']['base'],'42.00')
        from payments.retail_pricing import order_quote
        expected=order_quote(4200,1200,include_processing=True,monthly_price_increase_cents=400)
        self.assertEqual(data['products'][0]['retail_preview']['monthly_cents'],expected['monthly_cents'])
        self.release.refresh_from_db();self.assertEqual(self.release.checksum,before);self.assertFalse(self.release.active)

    def test_unknown_setup_is_never_rendered_as_a_payable_zero(self):
        payload=sample();payload[0]['setupUnknown']=True
        release=PrivateCatalogueRelease.objects.create(payload=payload)
        self.owner();row=self.client.get(f'{self.list_url}/{release.pk}').json()['products'][0]
        self.assertIsNone(row['retail_preview']['setup_cents'])
        self.assertIsNone(row['retail_preview']['first_invoice_cents'])

    def test_review_endpoint_cannot_approve_import_or_activate(self):
        self.owner()
        for url in [self.list_url,self.detail_url]:
            self.assertEqual(self.client.post(url,{'active':True,'approved':True}).status_code,405)
        self.release.refresh_from_db();self.assertFalse(self.release.active);self.assertIsNone(self.release.approved_at)

    def test_expired_google_or_missing_mfa_loses_source_access(self):
        self.owner();session=self.client.session;session['owner_admin_verified_at']=time.time()-3600;session.save()
        self.assertEqual(self.client.get(self.detail_url).status_code,403)
        session=self.client.session;session['owner_admin_verified_at']=time.time();session.pop('otp_device_id',None);session.save()
        self.assertEqual(self.client.get(self.detail_url).status_code,403)
