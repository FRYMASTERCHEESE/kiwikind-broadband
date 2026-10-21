"""Sandbox recurring Checkout and current-state reconciliation, never provisioning."""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from portal.models import AuditEvent
from .models import TestAgreement, TestInvoice
from .gateway import BillingUnavailable, ReconciliationError, plain, origin, safe_checkout, test_object


def validate_session(a, value):
    obj = test_object(value, 'checkout.session')
    if (not str(obj.get('id', '')).startswith('cs_test_') or obj.get('mode') != 'subscription'
            or obj.get('currency') != 'nzd' or obj.get('amount_total') != a.monthly_cents + a.setup_cents
            or obj.get('client_reference_id') != str(a.pk)
            or (obj.get('metadata') or {}).get('kiwikind_test_agreement') != str(a.pk)):
        raise ReconciliationError('Checkout does not match the reviewed test agreement')
    if a.checkout_id and obj['id'] != a.checkout_id:
        raise ReconciliationError('Checkout identity changed')
    return obj


def checkout(user, agreement_id, expected_version, api):
    # Persist first-attempt time and immutable input BEFORE making a network call.
    # A lost response can be retried with the same Stripe idempotency key, but never
    # silently recreated after Stripe may have removed that key (24 hours).
    with transaction.atomic():
        a = TestAgreement.objects.select_for_update().filter(pk=agreement_id, user=user, reviewed=True).first()
        if not a:
            raise TestAgreement.DoesNotExist
        if str(a.terms_version) != expected_version:
            raise ReconciliationError('Reviewed terms changed; refresh before consenting')
        if a.subscription_id or a.status != 'pending':
            raise ReconciliationError('Test checkout has already completed')
        if not a.checkout_started_at:
            a.full_clean()
            a.checkout_started_at = timezone.now()
            a.checkout_email = user.email
            a.save(update_fields=['checkout_started_at', 'checkout_email', 'updated_at'])
            AuditEvent.objects.create(actor=user, action='sandbox_recurring_consent', reference=str(a.pk))
        if timezone.now() - a.checkout_started_at > timedelta(hours=23):
            raise ReconciliationError('Older attempt needs reconciliation before any new checkout')
    if a.checkout_id:
        obj = validate_session(a, api.v1.checkout.sessions.retrieve(a.checkout_id))
    else:
        items = [{'price_data': {'currency': 'nzd', 'unit_amount': a.monthly_cents,
            'recurring': {'interval': 'month'}, 'product_data': {'name': 'KiwiKind TEST ONLY monthly'}}, 'quantity': 1}]
        if a.setup_cents:
            items.append({'price_data': {'currency': 'nzd', 'unit_amount': a.setup_cents,
                'product_data': {'name': 'KiwiKind TEST ONLY setup'}}, 'quantity': 1})
        params = dict(mode='subscription', allowed_payment_method_types=['card'],
            client_reference_id=str(a.pk), customer_email=a.checkout_email, line_items=items,
            metadata={'kiwikind_test_agreement': str(a.pk)},
            subscription_data={'metadata': {'kiwikind_test_agreement': str(a.pk)}},
            success_url=origin()+'/billing/?returned=1', cancel_url=origin()+'/billing/?cancelled=1',
            expires_at=int((a.checkout_started_at+timedelta(hours=1)).timestamp()),
            custom_text={'submit': {'message': 'TEST ONLY. No broadband service or real payment is supplied.'}})
        obj = validate_session(a, api.v1.checkout.sessions.create(params,
            options={'idempotency_key': 'kiwikind-sandbox-checkout-'+str(a.pk)}))
    if obj.get('status') != 'open' or not safe_checkout(obj.get('url')):
        raise ReconciliationError('Checkout is no longer open; refresh status')
    with transaction.atomic():
        locked = TestAgreement.objects.select_for_update().get(pk=a.pk)
        if locked.checkout_id and locked.checkout_id != obj['id']:
            raise ReconciliationError('Conflicting checkout')
        locked.checkout_id = obj['id']
        locked.save(update_fields=['checkout_id', 'updated_at'])
    return obj['url']


def bind_subscription(api, subscription_id):
    """Never associate subscriptions using caller email/metadata alone."""
    sub = test_object(api.v1.subscriptions.retrieve(subscription_id), 'subscription', subscription_id)
    identifier = (sub.get('metadata') or {}).get('kiwikind_test_agreement')
    if not identifier:
        return None, sub  # An unrelated subscription on the same Stripe account.
    a = TestAgreement.objects.select_for_update().filter(pk=identifier, reviewed=True,
        checkout_started_at__isnull=False).first()
    if not a:
        raise ReconciliationError('Unknown or unreviewed test agreement')
    if not a.checkout_id:
        raise ReconciliationError('Checkout still reconciling; retry')
    # Refresh under the per-agreement lock. A delayed competing handler must
    # not overwrite a later cancellation with a snapshot fetched before the lock.
    sub = test_object(api.v1.subscriptions.retrieve(subscription_id), 'subscription', subscription_id)
    if (sub.get('metadata') or {}).get('kiwikind_test_agreement') != str(a.pk):
        raise ReconciliationError('Subscription metadata changed')
    session = validate_session(a, api.v1.checkout.sessions.retrieve(a.checkout_id))
    if (session.get('status') != 'complete' or session.get('subscription') != subscription_id
            or not sub.get('customer') or session.get('customer') != sub['customer']
            or (a.customer_id and a.customer_id != sub['customer'])
            or (a.subscription_id and a.subscription_id != subscription_id)):
        raise ReconciliationError('Subscription/customer binding mismatch')
    items = (sub.get('items') or {}).get('data') or []
    if (len(items) != 1 or items[0].get('quantity') != 1
            or (items[0].get('price') or {}).get('unit_amount') != a.monthly_cents
            or (items[0].get('price') or {}).get('currency') != 'nzd'
            or (items[0].get('price') or {}).get('recurring', {}).get('interval') != 'month'
            or (items[0].get('price') or {}).get('recurring', {}).get('interval_count') != 1):
        raise ReconciliationError('Subscription price changed')
    allowed = {'incomplete','incomplete_expired','trialing','active','past_due','canceled','unpaid','paused'}
    if sub.get('status') not in allowed:
        raise ReconciliationError('Unknown subscription status')
    a.subscription_id = subscription_id
    a.customer_id = sub['customer']
    a.status = sub['status']
    a.cancel_at_period_end = sub.get('cancel_at_period_end') is True
    a.save(update_fields=['subscription_id','customer_id','status','cancel_at_period_end','updated_at'])
    return a, sub


def invoice_subscription(obj):
    return ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription') or obj.get('subscription')


def reconcile(api, kind, obj):
    if kind == 'checkout.session.completed':
        identifier = obj.get('id')
        a = TestAgreement.objects.select_for_update().filter(checkout_id=identifier).first()
        if not a:
            if (obj.get('metadata') or {}).get('kiwikind_test_agreement'):
                raise ReconciliationError('Checkout creation still reconciling')
            return
        current = validate_session(a, api.v1.checkout.sessions.retrieve(identifier))
        if current.get('status') != 'complete' or not current.get('subscription'):
            raise ReconciliationError('Incomplete checkout')
        bind_subscription(api, current['subscription'])
    elif kind.startswith('customer.subscription.'):
        bind_subscription(api, obj['id'])
    elif kind in ('invoice.paid', 'invoice.payment_failed', 'invoice.voided', 'invoice.marked_uncollectible', 'invoice.finalized'):
        current = test_object(api.v1.invoices.retrieve(obj['id']), 'invoice', obj['id'])
        subscription = invoice_subscription(current)
        if not subscription:
            return
        a, _ = bind_subscription(api, subscription)
        if not a:
            return
        current = test_object(api.v1.invoices.retrieve(obj['id']), 'invoice', obj['id'])
        if invoice_subscription(current) != subscription:
            raise ReconciliationError('Invoice subscription changed')
        reason = current.get('billing_reason')
        if reason not in ('subscription_create', 'subscription_cycle'):
            raise ReconciliationError('Unsupported invoice adjustment; manual review needed')
        expected = a.monthly_cents + (a.setup_cents if reason == 'subscription_create' else 0)
        if (current.get('currency') != 'nzd' or current.get('total') != expected
                or current.get('customer') != a.customer_id
                or current.get('status') not in ('open','paid','void','uncollectible')
                or (current.get('status') == 'paid' and current.get('amount_paid') != expected)):
            raise ReconciliationError('Invoice does not match the reviewed amounts/customer')
        ledger, _ = TestInvoice.objects.get_or_create(provider_id=current['id'], defaults={
            'agreement': a, 'amount_cents': expected, 'status': current['status']})
        if ledger.agreement_id != a.pk or ledger.amount_cents != expected:
            raise ReconciliationError('Ledger ownership/amount mismatch')
        ledger.status = current['status']
        if ledger.status == 'paid':
            payments = plain(api.v1.invoice_payments.list({'invoice': current['id'], 'status': 'paid', 'limit': 100}))
            entries = payments.get('data', [])
            if payments.get('has_more') or len(entries) != 1:
                raise ReconciliationError('Multiple payment allocation needs review')
            item = test_object(entries[0], 'invoice_payment')
            if item.get('invoice') != current['id']:
                raise ReconciliationError('Invoice allocation binding mismatch')
            intent = (item.get('payment') or {}).get('payment_intent')
            if item.get('amount_paid') != expected or item.get('currency') != 'nzd' or not intent:
                raise ReconciliationError('Invoice payment allocation mismatch')
            pi = test_object(api.v1.payment_intents.retrieve(intent), 'payment_intent', intent)
            if (pi.get('amount_received') != expected or pi.get('currency') != 'nzd'
                    or pi.get('customer') != a.customer_id or pi.get('status') != 'succeeded'
                    or (ledger.payment_intent and ledger.payment_intent != intent)):
                raise ReconciliationError('Payment intent mismatch')
            ledger.payment_intent = intent
        ledger.save()
    elif kind == 'charge.refunded' or kind.startswith('charge.dispute.'):
        charge_id = obj.get('charge') if kind.startswith('charge.dispute.') else obj['id']
        charge = test_object(api.v1.charges.retrieve(charge_id), 'charge', charge_id)
        intent = charge.get('payment_intent')
        if not intent:
            return
        ledger = TestInvoice.objects.select_for_update().filter(payment_intent=intent).select_related('agreement').first()
        if not ledger:
            # A refund/dispute may precede invoice.paid. Retry instead of losing it.
            raise ReconciliationError('Payment not reconciled yet')
        if (charge.get('currency') != 'nzd' or charge.get('amount') != ledger.amount_cents
                or charge.get('customer') != ledger.agreement.customer_id):
            raise ReconciliationError('Charge binding mismatch')
        amount = charge.get('amount_refunded')
        if type(amount) is not int or not 0 <= amount <= ledger.amount_cents:
            raise ReconciliationError('Invalid refund total')
        ledger.refunded_cents = amount
        if kind.startswith('charge.dispute.'):
            dispute = test_object(api.v1.disputes.retrieve(obj['id']), 'dispute', obj['id'])
            if dispute.get('charge') != charge_id:
                raise ReconciliationError('Dispute charge mismatch')
            ledger.dispute_status = dispute.get('status', '')
        ledger.save(update_fields=['refunded_cents','dispute_status','updated_at'])
