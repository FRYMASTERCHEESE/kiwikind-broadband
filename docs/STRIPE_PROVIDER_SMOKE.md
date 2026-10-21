# Stripe provider-only smoke test (not a customer payment)

The normal test suite uses mocked Stripe responses. This separate, one-time operator test verifies that the configured Stripe TEST key can **actually create and expire a recurring Checkout Session** in the intended sandbox, using an inline NZD $1 test price. It does not complete a card payment or exercise payment lifecycle webhooks.

Safety boundaries:
- Only runs with `KIWIKIND_STRIPE_PROVIDER_SMOKE_RUN=2026-10-21-v1`, while the UTC deadline is still in the future.
- Requires the existing pinned Stripe TEST account, test-mode balance and sandbox switch.
- Uses an identical idempotency key for every retry within the short test window.
- Contains no real customer email or service address, uses no production database models and outputs no Stripe keys, object IDs or checkout URLs.
- Immediately expires any valid open test Checkout. Expired sessions are accepted on retry.
- Operator MUST reset the one-shot environment variable to `off` after checking the deployment logs. No real charges, broadband orders or published prices are created.
- This does NOT prove a successful payment, provider webhook delivery, renewal, decline, authentication, cancellation, refund, dispute, signed Android release, or live customer checkout. Those require additional controlled end-to-end testing. A previous production synthetic-customer SQL write was blocked, and is not retried or rerouted by this test.

Verification: run `python manage.py test payments.test_provider_checkout_smoke --settings=config.test_settings`. Deployment remains on `feature/neon-postgres-config`, and GitHub Pages remains unchanged.
