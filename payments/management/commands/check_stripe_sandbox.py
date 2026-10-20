"""Read-only operator preflight. Never prints keys or creates payment objects."""
import stripe
from django.core.management.base import BaseCommand, CommandError
from payments import gateway

class Command(BaseCommand):
    help = 'Check private sandbox configuration; optionally verify account/mode without making changes.'
    def add_arguments(self, parser):
        parser.add_argument('--verify-provider',action='store_true')
    def handle(self, *args, **options):
        for label, value in gateway.configuration().items():
            self.stdout.write(f'{label}: {"present/on" if value else "missing/off"}')
        self.stdout.write('Live payments: disabled by this implementation')
        if options['verify_provider']:
            try:
                gateway.client()
            except (gateway.BillingUnavailable,stripe.StripeError):
                raise CommandError('Test account verification failed. Review credentials, account ID and restricted-key permissions privately.') from None
            self.stdout.write('PASS: pinned Stripe account and test-mode access verified. No changes made.')
