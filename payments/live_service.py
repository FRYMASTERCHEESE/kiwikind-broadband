"""Live recurring Checkout and current-state reconciliation, never provisioning."""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from portal.models import AuditEvent
from .live_models import LiveAgreement, LiveInvoice
from .live_gateway import BillingUnavailable, ReconciliationError, plain, origin, safe_checkout, live_object
from .live_gateway import verified_gst_rate


def validate_session(a, value):
    obj = live_object(value, 'checkout.session')
    if (not str(obj.get('id', '')).startswith('cs_live_') or obj.get('mode') != 'subscription'
            or obj.get('currency') != 'nzd' or obj.get('amount_total') != a.monthly_cents + a.setup_cents
            or obj.get('client_reference_id') != str(a.pk)
            or (obj.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk)):
        raise ReconciliationError('Checkout does not match the approved customer agreement')
    if a.checkout_id and obj['id'] != a.checkout_id:
        raise ReconciliationError('Checkout identity changed')
    return obj


def checkout_parameters(a):
    """Shared provider request, exercised in Stripe sandbox before release."""
    items = [{'price_data': {'currency': 'nzd', 'unit_amount': a.monthly_cents,
        'tax_behavior': 'inclusive', 'recurring': {'interval': 'month'},
        'product_data': {'name': 'KiwiKind monthly (GST included)'}}, 'quantity': 1}]
    if a.setup_cents:
        items.append({'price_data': {'currency': 'nzd', 'unit_amount': a.setup_cents,
            'tax_behavior': 'inclusive', 'product_data': {'name': 'KiwiKind setup once (GST included)'}}, 'quantity': 1})
    params = dict(automatic_tax={'enabled': False}, adaptive_pricing={'enabled': False},
        allow_promotion_codes=False, mode='subscription', allowed_payment_method_types=['card'],
        client_reference_id=str(a.pk), customer_email=a.checkout_email, line_items=items,
        metadata={'kiwikind_live_agreement': str(a.pk)},
        subscription_data={'metadata': {'kiwikind_live_agreement': str(a.pk)}, 'default_tax_rates':[a.gst_rate_id]},
        success_url=origin()+'/payments/?returned=1', cancel_url=origin()+'/payments/?cancelled=1',
        expires_at=int((a.checkout_started_at+timedelta(hours=1)).timestamp()),
        custom_text={'submit': {'message': 'Recurring monthly charge and one-time setup include GST. Payment does not automatically activate broadband.'}})
    from django.conf import settings
    if settings.PAGES_ENABLED:
        params['success_url']=settings.PAGES_URL+'account.html?returned=1'
        params['cancel_url']=settings.PAGES_URL+'account.html?cancelled=1'
    return params


def checkout(user, agreement_id, expected_version, api):
    # Persist first-attempt time and immutable input BEFORE making a network call.
    # A lost response can be retried with the same Stripe idempotency key, but never
    # silently recreated after Stripe may have removed that key (24 hours).
    with transaction.atomic():
        from portal.models import Order, BroadbandOrder
        linked = BroadbandOrder.objects.filter(payment_agreement_id=agreement_id, order__user=user).first()
        if linked:
            Order.objects.select_for_update().get(pk=linked.order_id)
        a = LiveAgreement.objects.select_for_update().filter(pk=agreement_id, user=user, reviewed=True).first()
        if not a:
            raise LiveAgreement.DoesNotExist
        if str(a.terms_version) != expected_version:
            raise ReconciliationError('Reviewed terms changed; refresh before consenting')
        a.check_checkout_eligibility()
        if a.subscription_id or a.status != 'pending':
            raise ReconciliationError('Checkout has already completed')
        if not a.checkout_started_at:
            a.check_checkout_eligibility()
            a.gst_rate_id = verified_gst_rate(api)
            a.checkout_started_at = timezone.now()
            a.checkout_email = user.email
            a.save(update_fields=['checkout_started_at', 'checkout_email', 'gst_rate_id', 'updated_at'])
            AuditEvent.objects.create(actor=user, action='live_recurring_consent', reference=str(a.pk))
        if timezone.now() - a.checkout_started_at > timedelta(hours=23):
            raise ReconciliationError('Older attempt needs reconciliation before any new checkout')
    if a.checkout_id:
        obj = validate_session(a, api.v1.checkout.sessions.retrieve(a.checkout_id))
    else:
        params = checkout_parameters(a)
        obj = validate_session(a, api.v1.checkout.sessions.create(params,
            options={'idempotency_key': 'kiwikind-live-checkout-'+str(a.pk)}))
    if obj.get('status') != 'open' or not safe_checkout(obj.get('url')):
        raise ReconciliationError('Checkout is no longer open; refresh status')
    with transaction.atomic():
        locked = LiveAgreement.objects.select_for_update().get(pk=a.pk)
        if locked.checkout_id and locked.checkout_id != obj['id']:
            raise ReconciliationError('Conflicting checkout')
        locked.checkout_id = obj['id']
        locked.save(update_fields=['checkout_id', 'updated_at'])
    return obj['url']


def bind_subscription(api, subscription_id):
    """Never associate subscriptions using caller email/metadata alone."""
    sub = live_object(api.v1.subscriptions.retrieve(subscription_id), 'subscription', subscription_id)
    identifier = (sub.get('metadata') or {}).get('kiwikind_live_agreement')
    if not identifier:
        return None, sub  # An unrelated subscription on the same Stripe account.
    a = LiveAgreement.objects.select_for_update().filter(pk=identifier, reviewed=True,
        checkout_started_at__isnull=False).first()
    if not a:
        raise ReconciliationError('Unknown or unapproved customer agreement')
    if not a.checkout_id:
        raise ReconciliationError('Checkout still reconciling; retry')
    # Refresh under the per-agreement lock. A delayed competing handler must
    # not overwrite a later cancellation with a snapshot fetched before the lock.
    sub = live_object(api.v1.subscriptions.retrieve(subscription_id), 'subscription', subscription_id)
    if (sub.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk):
        raise ReconciliationError('Subscription metadata changed')
    session = validate_session(a, api.v1.checkout.sessions.retrieve(a.checkout_id))
    if (session.get('status') != 'complete' or session.get('subscription') != subscription_id
            or not sub.get('customer') or session.get('customer') != sub['customer']
            or (a.customer_id and a.customer_id != sub['customer'])
            or (a.subscription_id and a.subscription_id != subscription_id)):
        raise ReconciliationError('Subscription/customer binding mismatch')
    items = (sub.get('items') or {}).get('data') or []
    tax_rates = sub.get('default_tax_rates') or []
    if [r.get('id') if isinstance(r,dict) else r for r in tax_rates] != [a.gst_rate_id]:
        raise ReconciliationError('Subscription GST treatment changed')
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
        a = LiveAgreement.objects.select_for_update().filter(checkout_id=identifier).first()
        if not a:
            if (obj.get('metadata') or {}).get('kiwikind_live_agreement'):
                raise ReconciliationError('Checkout creation still reconciling')
            return
        current = validate_session(a, api.v1.checkout.sessions.retrieve(identifier))
        if current.get('status') != 'complete' or not current.get('subscription'):
            raise ReconciliationError('Incomplete checkout')
        bind_subscription(api, current['subscription'])
    elif kind.startswith('customer.subscription.'):
        bind_subscription(api, obj['id'])
    elif kind in ('invoice.paid', 'invoice.payment_failed', 'invoice.voided', 'invoice.marked_uncollectible', 'invoice.finalized'):
        current = live_object(api.v1.invoices.retrieve(obj['id']), 'invoice', obj['id'])
        subscription = invoice_subscription(current)
        if not subscription:
            return
        a, _ = bind_subscription(api, subscription)
        if not a:
            return
        current = live_object(api.v1.invoices.retrieve(obj['id']), 'invoice', obj['id'])
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
        ledger, _ = LiveInvoice.objects.get_or_create(provider_id=current['id'], defaults={
            'agreement': a, 'amount_cents': expected, 'status': current['status']})
        if ledger.agreement_id != a.pk or ledger.amount_cents != expected:
            raise ReconciliationError('Ledger ownership/amount mismatch')
        ledger.status = current['status']
        if ledger.status == 'paid':
            payments = plain(api.v1.invoice_payments.list({'invoice': current['id'], 'status': 'paid', 'limit': 100}))
            entries = payments.get('data', [])
            if payments.get('has_more') or len(entries) != 1:
                raise ReconciliationError('Multiple payment allocation needs review')
            item = live_object(entries[0], 'invoice_payment')
            if item.get('invoice') != current['id']:
                raise ReconciliationError('Invoice allocation binding mismatch')
            intent = (item.get('payment') or {}).get('payment_intent')
            if item.get('amount_paid') != expected or item.get('currency') != 'nzd' or not intent:
                raise ReconciliationError('Invoice payment allocation mismatch')
            pi = live_object(api.v1.payment_intents.retrieve(intent), 'payment_intent', intent)
            if (pi.get('amount_received') != expected or pi.get('currency') != 'nzd'
                    or pi.get('customer') != a.customer_id or pi.get('status') != 'succeeded'
                    or (ledger.payment_intent and ledger.payment_intent != intent)):
                raise ReconciliationError('Payment intent mismatch')
            ledger.payment_intent = intent
        ledger.save()
    elif kind == 'charge.refunded' or kind.startswith('charge.dispute.'):
        charge_id = obj.get('charge') if kind.startswith('charge.dispute.') else obj['id']
        charge = live_object(api.v1.charges.retrieve(charge_id), 'charge', charge_id)
        intent = charge.get('payment_intent')
        if not intent:
            return
        ledger = LiveInvoice.objects.select_for_update().filter(payment_intent=intent).select_related('agreement').first()
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
            dispute = live_object(api.v1.disputes.retrieve(obj['id']), 'dispute', obj['id'])
            if dispute.get('charge') != charge_id:
                raise ReconciliationError('Dispute charge mismatch')
            ledger.dispute_status = dispute.get('status', '')
        ledger.save(update_fields=['refunded_cents','dispute_status','updated_at'])
