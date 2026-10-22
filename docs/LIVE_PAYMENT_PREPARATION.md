# Live payment preparation — not enabled

The owner authorised preparation and verification for launch on 22 October
2026. This does not publish the private catalogue, release Android, enable
customer charges or permit supplier orders.

`payments.retail_pricing.order_quote` prepares GST-inclusive NZD amounts from
combined server-trusted supplier selections. Add $3 to the monthly total and
$10 once to the installation total **after** applying GST. Neither addition
receives further GST. Missing installation prices cannot produce a payable
total. The first invoice equals the displayed monthly and setup lines.

This helper is not wired into checkout. The existing sandbox remains isolated.
No supplier price records are committed with this change.

Before a live implementation can be verified:

1. Configure the expected live Stripe account ID and live server credential
   in Render's private environment editor. Never put secrets in chat, client
   code, repository files, screenshots or logs. Leave test credentials intact.
2. Use the existing owner/MFA protected read-only diagnostic to verify the
   pinned live account and its charges/payouts capabilities. Identity checks
   already completed by the owner must not be repeated unnecessarily.
3. Implement separate live agreements, checkout and signed webhook ledger;
   use immutable server-approved prices, versioned consent, stable idempotency,
   ownership checks and reconciliation. Do not deploy unfinished draft PR41.
4. Test renewals, failures, authentication, cancellations, replayed/out-of-order
   webhooks and web/Android handoff using test credentials before activation.
5. Present the resulting checkout and exact prices to the owner before live
   customer charges. Do not perform a real charge merely to test readiness.

Keep the Closed Alpha track intact, private prices unpublished and supplier
ordering disabled. Confirm service availability manually before offering an
agreement while supplier ordering remains manual.
