# Complete GST-inclusive customer prices

This optional pricing policy budgets typical card and subscription-collection
costs inside the **full advertised retail price**. No additional processing
fee or payment-method surcharge is added at Stripe Checkout. Customers must
see the final monthly amount, the final one-time setup amount and the initial
payment total before accepting their reviewed offer.

Source assumptions (22 October 2026):
- Stripe NZ standard domestic online card payments: 2.65% plus NZ$0.30
- Stripe Billing pay-as-you-go subscription volume: 0.7%
- Actual merchant rates and fees (international cards, GST on fees, refunds,
  disputes and other products) may differ.
- The internal retailer's existing NZ$3 monthly and NZ$10 one-time allowance
  remains inside the baseline price; the calculation then budgets processing.

The backend switch `KIWIKIND_ALL_IN_RETAIL_ENABLED=1` applies to **new**
website and Android catalogue quotes and new agreements only. It defaults to
OFF. An immutable `pricing_policy` identifier retains the older calculation
for historical agreements. Running migrations never reprices historical
agreements. All customers see the actual full GST-inclusive amounts before
consenting. Quotes requested before a policy change must be refreshed before
a draft owner offer can be created. Already signed Stripe sessions, invoices
and recurring subscriptions are not silently modified.

Example from owner-supplied Vetta 500/100 UFB churn (NZD):
Supplier monthly $69.92 ex GST, churn setup $35.00 ex GST.
Baseline quote: $83.41 monthly, $50.25 one-time, first $133.66.
Estimated all-inclusive standard domestic card pricing:
$86.62 monthly, $52.00 one-time, first $138.62.
No separate processing fee should appear later. These are customer-facing
retail totals, not a guarantee of business profit or installation eligibility.

Activation: green Django/PostgreSQL/Android CI, verify the deployed Render
service branch and database migration, then enable the opt-in on the server.
Do not change historical signed terms or charge cards as a deployment test.
Owner-only catalogue and supplier approval safeguards remain unchanged.
