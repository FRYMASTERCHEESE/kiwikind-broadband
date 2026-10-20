"""Synthetic admin sessions for isolated tests/visual fixtures only."""
import time
from django.conf import settings
from django.db import connection
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import OwnerIdentity
from .owner_admin import OWNER_EMAIL, OWNER_USERNAME


def owner_fixture(client, user):
    name = str(connection.settings_dict['NAME'])
    assert (name.startswith(('test_', 'file:memorydb_')) or
            (settings.DEBUG and name.replace('\\', '/').endswith('test-results/visual.sqlite3'))), \
        'Synthetic fixture requires a disposable test database.'
    user.username, user.email = OWNER_USERNAME, OWNER_EMAIL
    user.set_unusable_password()
    user.save()
    OwnerIdentity.objects.get_or_create(user=user, defaults={
        'subject': 'synthetic-owner', 'verified_email': OWNER_EMAIL})
    device, _ = TOTPDevice.objects.get_or_create(user=user, name='Test only', confirmed=True)
    client.force_login(user)
    session = client.session
    session['owner_admin_verified_at'] = time.time()
    session['owner_google_subject'] = 'synthetic-owner'
    session['otp_device_id'] = device.persistent_id
    session.save()
    return device


def owner_request(request, client, user, device):
    request.user, request.session = user, client.session
    user.otp_device = device
    user.is_verified = lambda: True
