"""Private startup diagnostic for live Stripe mode: read-only, secret-free."""
from django.core.management.base import BaseCommand

from payments.live_preflight import settings_status, verify_account


class Command(BaseCommand):
    help = "Report live Stripe account readiness without creating payments or enabling checkout."

    def add_arguments(self, parser):
        parser.add_argument("--verify-provider", action="store_true")

    def handle(self, *args, **options):
        config = settings_status()
        for key in ("live_api_key_present", "live_account_id_present",
                    "live_webhook_secret_present"):
            self.stdout.write(
                "Stripe live %s: %s" %
                (key, "present" if config[key] else "missing")
            )
        self.stdout.write("Stripe live checkout: " + ("ENABLED (approved customer agreements only)" if config['live_checkout_enabled'] else "DISABLED (release or configuration pending)"))
        if options["verify_provider"]:
            verified = verify_account()
            # Report statuses ONLY, not raw keys, IDs or Stripe responses.
            self.stdout.write("Stripe live identity: " + verified["result"])
            if verified["account_matches_live_mode"]:
                self.stdout.write("Stripe live charges_enabled: " +
                                  ("yes" if verified["charges_enabled"] else "no"))
                self.stdout.write("Stripe live payouts_enabled: " +
                                  ("yes" if verified["payouts_enabled"] else "no"))
