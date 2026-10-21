"""Read-only provider evidence for the owner's latest reviewed test agreement.

No provider response bodies, IDs, customer details or exceptions leave this module.
No writes to Stripe or the billing ledger. A check is not a launch approval.
"""
import os
import stripe
from . import gateway
from .models import TestAgreement, TestInvoice
from .service import validate_session, invoice_subscription


def verify_owner_evidence(owner):
    config = gateway.configuration()
    if not all(config[k] for k in ('test_key_present', 'webhook_present', 'account_pinned')):
        return {'verified': False, 'detail': 'Required sandbox configuration is missing.'}
    agreement = TestAgreement.objects.filter(user=owner, reviewed=True,
        subscription_id__isnull=False).order_by('-created_at').first()
    if not agreement:
        return {'verified': False, 'detail': 'No reviewed owner TEST subscription is recorded.'}
    invoice = TestInvoice.objects.filter(agreement=agreement, status='paid').exclude(
        payment_intent='').order_by('-created_at').first()
    if not invoice:
        return {'verified': False, 'detail': 'No paid owner TEST invoice is recorded.'}
    try:
        api = stripe.StripeClient(os.environ['STRIPE_TEST_SECRET_KEY'].strip(),
            stripe_version=gateway.API_VERSION, max_network_retries=0,
            http_client=stripe.RequestsClient(timeout=6))
        account = gateway.plain(api.v1.accounts.retrieve_current())
        balance = gateway.plain(api.v1.balance.retrieve())
        if (account.get('object') != 'account' or account.get('id') != os.environ['STRIPE_TEST_ACCOUNT_ID'].strip()
                or balance.get('object') != 'balance' or balance.get('livemode') is not False):
            raise ValueError('Account mismatch')
        session = validate_session(agreement, api.v1.checkout.sessions.retrieve(agreement.checkout_id))
        sub = gateway.test_object(api.v1.subscriptions.retrieve(agreement.subscription_id), 'subscription', agreement.subscription_id)
        current = gateway.test_object(api.v1.invoices.retrieve(invoice.provider_id), 'invoice', invoice.provider_id)
        payments = gateway.plain(api.v1.invoice_payments.list({'invoice': invoice.provider_id, 'status': 'paid', 'limit': 2}))
        allocations = payments.get('data', [])
        if payments.get('has_more') or len(allocations) != 1:
            raise ValueError('Payment allocation unavailable')
        allocation = gateway.test_object(allocations[0], 'invoice_payment')
        intent = gateway.test_object(api.v1.payment_intents.retrieve(invoice.payment_intent), 'payment_intent', invoice.payment_intent)
        charge = gateway.test_object(api.v1.charges.retrieve(intent.get('latest_charge')), 'charge', intent.get('latest_charge'))
        if (session.get('status') != 'complete' or session.get('subscription') != agreement.subscription_id
                or session.get('customer') != agreement.customer_id
                or sub.get('customer') != agreement.customer_id
                or (sub.get('metadata') or {}).get('kiwikind_test_agreement') != str(agreement.pk)
                or invoice_subscription(current) != agreement.subscription_id
                or current.get('customer') != agreement.customer_id
                or current.get('currency') != 'nzd' or current.get('total') != invoice.amount_cents
                or allocation.get('invoice') != invoice.provider_id
                or allocation.get('currency') != 'nzd' or allocation.get('amount_paid') != invoice.amount_cents
                or (allocation.get('payment') or {}).get('payment_intent') != invoice.payment_intent
                or intent.get('customer') != agreement.customer_id
                or intent.get('currency') != 'nzd' or intent.get('amount_received') != invoice.amount_cents
                or charge.get('payment_intent') != invoice.payment_intent
                or charge.get('customer') != agreement.customer_id
                or charge.get('currency') != 'nzd' or charge.get('amount') != invoice.amount_cents):
            raise ValueError('Binding mismatch')
        return {'verified': True, 'initial_paid_invoice': current.get('billing_reason') == 'subscription_create' and current.get('status') == 'paid'
                and current.get('amount_paid') == invoice.amount_cents and intent.get('status') == 'succeeded',
            'full_refund': invoice.amount_cents > 0 and charge.get('amount_refunded') == invoice.amount_cents,
            'cancellation': sub.get('cancel_at_period_end') is True or sub.get('status') == 'canceled',
            'detail': 'Current pinned Stripe TEST objects checked read-only. Renewal, decline and authentication challenge remain unverified.'}
    except Exception:
        return {'verified': False, 'detail': 'Provider check failed. Review sandbox access and record bindings privately.'}
