"""Read-only Stripe sandbox identity check. Does not enable billing or print secrets."""
import os
import stripe
from django.core.management.base import BaseCommand
from payments import gateway


class Command(BaseCommand):
    help = "Verify pinned Stripe test account via read-only API calls without opening checkout."

    def handle(self, *args, **kwargs):
        cfg = gateway.configuration()
        needed = ("test_key_present", "webhook_present", "account_pinned")
        if not all(cfg.get(k) for k in needed):
            self.stdout.write("Stripe sandbox verification: WAITING (required test settings missing).")
            return

        try:
            # Do not use gateway.client(): it deliberately requires the checkout
            # feature switch. This verifier must NOT change that switch, even
            # temporarily, or create Stripe resources.
            api = stripe.StripeClient(
                os.environ["STRIPE_TEST_SECRET_KEY"].strip(),
                stripe_version=gateway.API_VERSION,
                max_network_retries=0,
                http_client=stripe.RequestsClient(timeout=6),
            )
            account = gateway.plain(api.v1.accounts.retrieve_current())
            balance = gateway.plain(api.v1.balance.retrieve())
            if not (
                isinstance(account, dict)
                and account.get("object") == "account"
                and account.get("id") == os.environ["STRIPE_TEST_ACCOUNT_ID"].strip()
                and isinstance(balance, dict)
                and balance.get("object") == "balance"
                and balance.get("livemode") is False
            ):
                raise ValueError("Account or test mode does not match")
        except Exception:
            # Do not log provider exception text: some SDK error objects contain
            # request identifiers, configuration details or sensitive responses.
            self.stdout.write(
                "Stripe sandbox verification: FAILED (review sandbox credentials "
                "and permissions privately; checkout remains disabled)."
            )
            return

        self.stdout.write(
            "Stripe sandbox verification: PASS (expected test account and mode; "
            "no payments created; checkout switch unchanged)."
        )
