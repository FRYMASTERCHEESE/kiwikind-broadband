import copy
import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import PrivateCatalogueRelease, Order
from .private_catalogue import validate_payload, digest
from .testing import owner_fixture
from .broadband import quote
from payments.retail_pricing import order_quote


def sample():
    return [{'id': 'synthetic-service', 'family': 'ufb', 'kind': 'complete_service',
        'name': 'Synthetic 123/45 service', 'description': 'Disposable test service.',
        'base': '42.00', 'baseSetup': '12.00', 'setupUnknown': False,
        'gst_basis': 'exclusive', 'allowance': '123GB; excess usage charged per GB.',
        'terms': 'Synthetic test terms. Eligibility must be checked.',
        'source_ref': 'synthetic-evidence', 'price_status': 'verified', 'unverified': [],
        'groups': [{'id': 'data', 'label': 'Data', 'options': [
            {'id': 'included', 'name': '123GB', 'monthly': '0.00', 'setup': '0.00',
             'unknown': False, 'usage': {'rate': '2.00', 'unit': 'GB'}}]}]}]


@override_settings(BROADBAND_CATALOGUE_ENABLED=True, PLAN_PUBLICATION_ENABLED=True,
                   KIWIKIND_ALL_IN_RETAIL_ENABLED=True)
class PrivateCatalogueTests(TestCase):
    def publish(self):
        from django.contrib.auth import get_user_model
        from .owner_admin import OWNER_EMAIL, OWNER_USERNAME
        owner = get_user_model().objects.create_superuser(OWNER_USERNAME, OWNER_EMAIL)
        owner_fixture(self.client, owner)
        payload = validate_payload(sample())
        return PrivateCatalogueRelease.objects.create(payload=payload, active=True,
            verified_on=timezone.localdate(), valid_until=timezone.localdate()+timedelta(days=1),
            approved_by=owner, approved_at=timezone.now(), approved_digest=digest(payload))

    def test_empty_and_draft_never_fall_back_to_legacy_source(self):
        PrivateCatalogueRelease.objects.create(payload=sample())
        response = self.client.get('/api/broadband/catalogue').json()
        self.assertEqual(response['products'], [])
        self.assertFalse(response['orders_enabled'])
        self.assertEqual(self.client.get('/api/broadband/quote?product=adsl&options=0').status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_shared_projection_totals_usage_and_confidentiality(self):
        self.publish()
        response = self.client.get('/api/broadband/catalogue')
        plan = response.json()['products'][0]
        expected = order_quote(4200, 1200, include_processing=True, monthly_price_increase_cents=400)
        self.assertEqual(plan['default_quote']['monthly_cents'], expected['monthly_cents'])
        self.assertEqual(plan['default_quote']['first_invoice_cents'], expected['monthly_cents']+expected['setup_cents'])
        self.assertEqual(plan['allowance'], sample()[0]['allowance'])
        compatibility = self.client.get('/api/plans').json()['plans'][0]
        self.assertEqual(compatibility['retail_monthly_cents'], expected['monthly_cents'])
        self.assertEqual(compatibility['allowance'], plan['allowance'])
        self.assertIn('2.3000/GB', plan['default_quote']['usage'][0])
        for private in ('source_ref', '42.00', 'source_monthly_cents', 'monthly_addition_cents'):
            self.assertNotIn(private, response.content.decode())

    def test_gate_expiry_tampering_and_unapproved_owner_fail_closed(self):
        release = self.publish()
        for setting in ('PLAN_PUBLICATION_ENABLED', 'BROADBAND_CATALOGUE_ENABLED'):
            with override_settings(**{setting: False}):
                self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])
                self.assertEqual(self.client.get('/api/broadband/quote?product=synthetic-service&options=included').status_code, 503)
        PrivateCatalogueRelease.objects.filter(pk=release.pk).update(valid_until=timezone.localdate()-timedelta(days=1))
        self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])
        PrivateCatalogueRelease.objects.filter(pk=release.pk).update(valid_until=timezone.localdate(), payload=sample()+sample())
        self.assertEqual(self.client.get('/api/broadband/catalogue').json()['products'], [])

    def test_duplicate_service_group_option_and_unknown_fees_rejected(self):
        for mutate in (
            lambda p: p.append(copy.deepcopy(p[0])),
            lambda p: p[0]['groups'].append(copy.deepcopy(p[0]['groups'][0])),
            lambda p: p[0]['groups'][0]['options'].append(copy.deepcopy(p[0]['groups'][0]['options'][0])),
            lambda p: p[0].update(kind='component'),
            lambda p: p[0].update(base='NaN'),
            lambda p: p[0].update(setupUnknown=True),
            lambda p: p[0].update(unverified=['Excess data rules']),
        ):
            payload = sample(); mutate(payload)
            with self.assertRaises(ValidationError): validate_payload(payload, publish=True)

    def test_import_dry_run_idempotency_and_immutable_archive(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent) as folder:
            file = Path(folder)/'synthetic.json'; file.write_text(json.dumps(sample()))
            call_command('import_private_catalogue', str(file), stdout=io.StringIO())
            self.assertEqual(PrivateCatalogueRelease.objects.count(), 0)
            for _ in range(2):
                call_command('import_private_catalogue', str(file), apply=True, stdout=io.StringIO())
        self.assertEqual(PrivateCatalogueRelease.objects.count(), 1)
        release = PrivateCatalogueRelease.objects.get()
        self.assertFalse(release.active)
        release.payload[0]['base'] = '43.00'
        with self.assertRaises(ValidationError): release.save()

    def test_retail_uplift_is_exactly_four_and_setup_is_once_only(self):
        old = order_quote(4200, 1200, include_processing=True)
        new = order_quote(4200, 1200, include_processing=True, monthly_price_increase_cents=400)
        self.assertEqual(new['monthly_cents']-old['monthly_cents'], 400)
        self.assertEqual(new['setup_cents'], old['setup_cents'])
        self.assertEqual(new['first_invoice_cents'], new['monthly_cents']+new['setup_cents'])
