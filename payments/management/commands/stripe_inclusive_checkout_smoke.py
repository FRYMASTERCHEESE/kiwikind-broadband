"""Time-limited provider QA: test key only, no customer/payment/database writes."""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from django.core.management.base import BaseCommand
from payments import gateway
from payments.live_service import checkout_parameters

FLAG = 'KIWIKIND_STRIPE_INCLUSIVE_QA'
RUN = '2026-10-22-inclusive-v1'
DEADLINE = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


class Command(BaseCommand):
    help = 'Create and expire a synthetic TEST recurring checkout with inclusive GST and one-time setup.'

    def handle(self, *args, **options):
        if os.environ.get(FLAG) != RUN or datetime.now(timezone.utc) >= DEADLINE - timedelta(hours=1):
            self.stdout.write('Stripe inclusive provider QA: SKIPPED (switch off or window expired).')
            return
        session_id = None
        rate_id = None
        passed = False
        cleaned = True
        phase = 'identity'
        try:
            api = gateway.client()  # Never reads a live key; verifies pinned TEST account and mode.
            phase = 'tax_rate'
            rate = gateway.test_object(api.v1.tax_rates.create({
                'display_name': 'GST', 'description': 'KiwiKind TEST inclusive GST QA',
                'inclusive': True, 'percentage': 15, 'country': 'NZ',
            }, options={'idempotency_key': RUN+'-rate'}), 'tax_rate')
            rate_id = rate['id']
            if rate.get('inclusive') is not True or rate.get('country') != 'NZ' or rate.get('percentage') != 15:
                raise ValueError('Invalid test tax rate')
            # Stable parameters across retries. No real customer/email/supplier data.
            offer = SimpleNamespace(pk='kiwikind-inclusive-provider-qa', monthly_cents=1450,
                setup_cents=1230, gst_rate_id=rate_id, checkout_email=None,
                checkout_started_at=DEADLINE-timedelta(hours=1))
            params = checkout_parameters(offer)
            phase = 'checkout_create'
            session = gateway.test_object(api.v1.checkout.sessions.create(params,
                options={'idempotency_key': RUN+'-checkout'}), 'checkout.session')
            if str(session.get('id', '')).startswith('cs_test_'):
                session_id = session['id']
            phase = 'checkout_validate'
            if (not session_id or session.get('currency') != 'nzd' or session.get('amount_total') != 2680
                    or session.get('mode') != 'subscription' or session.get('customer') is not None
                    or session.get('subscription') is not None or session.get('status') not in ('open', 'expired')
                    or (session.get('status') == 'open' and not gateway.safe_checkout(session.get('url')))):
                raise ValueError('Unexpected test checkout')
            lines = gateway.plain(api.v1.checkout.sessions.line_items.list(session_id, {'limit': 10}))
            items = lines.get('data', [])
            if (lines.get('has_more') or len(items) != 2
                    or sorted(item.get('amount_total') for item in items) != [1230, 1450]
                    or any(not isinstance(item.get('amount_tax'), int) or item['amount_tax'] <= 0 for item in items)
                    or sum(bool((item.get('price') or {}).get('recurring')) for item in items) != 1
                    or any((item.get('price') or {}).get('tax_behavior') != 'inclusive' for item in items)):
                raise ValueError('Incorrect test recurring/setup lines')
            passed = True
        except Exception as exc:
            category = type(exc).__name__
            if category not in {'PermissionError','AuthenticationError','InvalidRequestError','IdempotencyError',
                                'APIConnectionError','BillingUnavailable','ReconciliationError','ValueError','AttributeError'}:
                category = 'provider_failure'
            self.stdout.write('Stripe inclusive provider QA: FAILED at %s (%s).' % (phase, category))
        finally:
            if session_id:
                try:
                    current = gateway.test_object(api.v1.checkout.sessions.retrieve(session_id), 'checkout.session', session_id)
                    if current.get('status') == 'open':
                        current = gateway.test_object(api.v1.checkout.sessions.expire(session_id), 'checkout.session', session_id)
                    cleaned = current.get('status') == 'expired'
                except Exception:
                    cleaned = False
            if rate_id:
                try:
                    rate = gateway.test_object(api.v1.tax_rates.update(rate_id, {'active': False}), 'tax_rate', rate_id)
                    cleaned = cleaned and rate.get('active') is False
                except Exception:
                    cleaned = False
            if passed and cleaned:
                self.stdout.write('Stripe inclusive provider QA: PASS (TEST total 26.80; monthly 14.50; setup 12.30 once; session expired; test tax rate archived; no payment/customer/service).')
            elif not cleaned:
                self.stdout.write('Stripe inclusive provider QA: ATTENTION (test resource cleanup needs review).')
