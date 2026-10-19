"""Disposable test-database checks: migration preservation and competing operators."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, TransactionTestCase, override_settings, skipUnlessDBFeature

from .models import WholesaleOrder, WholesaleEvent
from .wholesale import transition


class WholesaleMigrationTests(TransactionTestCase):
    def test_existing_accounts_identities_sessions_and_requests_survive_migration(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('portal', '0008_provider_shortlist')])
        try:
            apps = executor.loader.project_state([('portal', '0008_provider_shortlist')]).apps
            user = apps.get_model('auth', 'User').objects.create(username='migration-fixture', email='fixture@example.invalid', password=make_password('synthetic-never-used'))
            original_password = user.password
            apps.get_model('portal', 'GoogleIdentity').objects.create(user_id=user.pk, subject='synthetic-subject')
            order = apps.get_model('portal', 'Order').objects.create(user_id=user.pk, address='1 Synthetic Test Road', postcode='3400', contact_name='Fixture')
            browser = Client()
            browser.force_login(get_user_model().objects.get(pk=user.pk))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate([('portal', '0009_wholesale_preparation')])
        from .models import GoogleIdentity, Order
        restored = get_user_model().objects.get(pk=user.pk)
        self.assertEqual(restored.password, original_password)
        self.assertEqual(GoogleIdentity.objects.get(user=restored).subject, 'synthetic-subject')
        self.assertEqual(Order.objects.get(pk=order.pk).user_id, restored.pk)
        self.assertEqual(Order.objects.get(pk=order.pk).status, 'requested')
        self.assertFalse(WholesaleOrder.objects.exists())
        self.assertEqual(browser.get('/api/bootstrap').json()['account']['email'], 'fixture@example.invalid')


@override_settings(ADMIN_ENABLED=True, OWNER_GOOGLE_ADMIN_ENABLED=False)
class WholesaleConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_competing_operators_cannot_both_advance_same_revision(self):
        owner = get_user_model().objects.create_user('kiwikind-owner-admin', 'kiwikindbroadband@gmail.com', is_staff=True, is_superuser=True)
        case = WholesaleOrder.objects.create(address='1 Synthetic Test Road', postcode='3400', created_by=owner)
        barrier = Barrier(2)

        def update():
            request = RequestFactory().post('/admin/wholesale/')
            request.user = get_user_model().objects.get(pk=owner.pk)
            request.session = {}
            barrier.wait(timeout=15)
            try:
                transition(request, WholesaleOrder, case.pk, target='availability_review', revision=0,
                           submission_key=uuid.uuid4(), note='Synthetic concurrent review')
                return 'saved'
            except ValidationError:
                return 'stale'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: update(), range(2)))
        self.assertCountEqual(results, ['saved', 'stale'])
        self.assertEqual(WholesaleEvent.objects.filter(order=case).count(), 1)
        case.refresh_from_db(); self.assertEqual(case.revision, 1)
