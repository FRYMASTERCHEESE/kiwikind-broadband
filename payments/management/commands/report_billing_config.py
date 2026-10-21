"""Report presence booleans only. Never print environment values or provider data."""
import json
from django.core.management.base import BaseCommand
from payments import gateway, live_gateway


class Command(BaseCommand):
    help = 'Print safe billing configuration booleans; no Stripe network calls or mutations.'

    def handle(self, *args, **options):
        self.stdout.write('KIWIKIND_BILLING_CONFIG '+json.dumps({
            'sandbox': gateway.configuration(), 'live': live_gateway.configuration()}, sort_keys=True))
