"""Pinned live account; new charges require TWO explicit release switches.

Reading provider state and receiving signed callbacks remain possible when new
checkout is paused. Test keys/objects never enter this separate live ledger.
"""
import os
import re
from urllib.parse import urlsplit
import stripe
from decimal import Decimal, InvalidOperation
from .gateway import API_VERSION, BillingUnavailable, ReconciliationError, plain, origin


def configuration():
    return {
        'checkout_switch_on': os.environ.get('KIWIKIND_LIVE_BILLING_ENABLED') == '1',
        'release_approved': os.environ.get('KIWIKIND_LIVE_RELEASE_APPROVED') == '1',
        'live_key_present': bool(re.fullmatch(r'(?:sk|rk)_live_[A-Za-z0-9]+', os.environ.get('STRIPE_LIVE_SECRET_KEY', '').strip())),
        'webhook_present': bool(re.fullmatch(r'whsec_[A-Za-z0-9]+', os.environ.get('STRIPE_LIVE_WEBHOOK_SECRET', '').strip())),
        'account_pinned': bool(re.fullmatch(r'acct_[A-Za-z0-9]+', os.environ.get('STRIPE_LIVE_ACCOUNT_ID', '').strip())),
        'gst_rate_present': bool(re.fullmatch(r'txr_[A-Za-z0-9]+', os.environ.get('STRIPE_LIVE_GST_RATE_ID', '').strip())),
    }


def credentials_ready():
    c = configuration()
    return all(c[k] for k in ('live_key_present', 'webhook_present', 'account_pinned'))


def configured():
    return all(configuration().values())


def client(*, for_checkout=False):
    if not credentials_ready() or (for_checkout and not configured()):
        raise BillingUnavailable('Live billing is not configured and released')
    origin()
    api = stripe.StripeClient(os.environ['STRIPE_LIVE_SECRET_KEY'].strip(),
        stripe_version=API_VERSION, max_network_retries=0, http_client=stripe.RequestsClient(timeout=3))
    account = plain(api.v1.accounts.retrieve_current())
    balance = plain(api.v1.balance.retrieve())
    if (account.get('object') != 'account' or account.get('id') != os.environ['STRIPE_LIVE_ACCOUNT_ID'].strip()
            or balance.get('object') != 'balance' or balance.get('livemode') is not True):
        raise BillingUnavailable('Stripe account/mode mismatch')
    if for_checkout and (account.get('charges_enabled') is not True or account.get('payouts_enabled') is not True):
        raise BillingUnavailable('Stripe account activation is incomplete')
    return api


def live_object(value, object_type=None, identifier=None):
    obj = plain(value)
    if (not isinstance(obj, dict) or obj.get('livemode') is not True
            or (object_type and obj.get('object') != object_type)
            or (identifier and obj.get('id') != identifier)):
        raise ReconciliationError('Unverified live provider object')
    return obj


def verified_gst_rate(api, identifier=None):
    identifier = identifier or os.environ.get('STRIPE_LIVE_GST_RATE_ID', '').strip()
    if not re.fullmatch(r'txr_[A-Za-z0-9]+', identifier):
        raise BillingUnavailable('Inclusive GST rate is not configured')
    rate = live_object(api.v1.tax_rates.retrieve(identifier), 'tax_rate', identifier)
    try:
        percentage = Decimal(str(rate.get('percentage')))
    except (InvalidOperation, ValueError):
        raise BillingUnavailable('Invalid GST rate')
    if rate.get('active') is not True or rate.get('inclusive') is not True or percentage != Decimal('15') or rate.get('country') != 'NZ':
        raise BillingUnavailable('Expected active inclusive NZ GST rate')
    return identifier


def safe_checkout(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r'[\s\\]', url):
        return False
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname == 'checkout.stripe.com' and p.port in (None, 443)
                and not p.username and not p.password and p.path.startswith('/c/pay/cs_live_'))
    except ValueError:
        return False


