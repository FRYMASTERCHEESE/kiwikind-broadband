"""Offline, trusted operator enrolment. Never run automatically during deployment."""
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django_otp.plugins.otp_totp.models import TOTPDevice
from portal.admin_site import OWNER_EMAIL, is_owner

class Command(BaseCommand):
    help = 'Send owner email verification or enrol an owner authenticator from a trusted console.'
    def add_arguments(self, parser):
        parser.add_argument('action', choices=['verify-email','enrol-mfa'])
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(pk=settings.OWNER_USER_ID or None,
            username=OWNER_EMAIL,email=OWNER_EMAIL,is_active=True,is_staff=True).first()
        if not user:
            raise CommandError('Set OWNER_USER_ID to the independently checked existing owner staff account. No account is created or promoted.')
        if options['action'] == 'verify-email':
            token=signing.dumps({'id':user.pk,'email':user.email,'owner_verification':True},salt='verify')
            send_mail('Verify KiwiKind owner email',f'{settings.PUBLIC_ORIGIN}/#verify={token}',settings.DEFAULT_FROM_EMAIL,[OWNER_EMAIL])
            self.stdout.write('Verification sent to the owner mailbox.')
            return
        if not is_owner(user): raise CommandError('Verify owner email first.')
        if TOTPDevice.objects.filter(user=user,confirmed=True).exists():
            raise CommandError('Owner already has MFA. Recovery requires a separate trusted operator review.')
        device=TOTPDevice(user=user,name='Owner authenticator',confirmed=False)
        self.stdout.write('On a private console only, add this URI to your authenticator. It contains a secret:')
        self.stdout.write(device.config_url)
        if not device.verify_token(getpass('Authenticator code: ')):
            raise CommandError('Invalid code. Device was not enrolled.')
        device.confirmed=True
        device.save()
        self.stdout.write('MFA enrolled. Protect database backups; they contain the authenticator secret.')
