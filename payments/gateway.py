"""All network access is fixed to Stripe and rejects live credentials and objects."""
import os
import re
from urllib.parse import urlsplit
import stripe
from django.conf import settings

API_VERSION = '2026-09-30.endive'


class BillingUnavailable(Exception):
    pass


class ReconciliationError(Exception):
    pass


def plain(value):
    return value.to_dict() if isinstance(value, stripe.StripeObject) else value


def configuration():
    key = os.environ.get('STRIPE_TEST_SECRET_KEY', '').strip()
    secret = os.environ.get('STRIPE_TEST_WEBHOOK_SECRET', '').strip()
    account = os.environ.get('STRIPE_TEST_ACCOUNT_ID', '').strip()
    return {
        'switch_on': os.environ.get('KIWIKIND_STRIPE_SANDBOX') == '1',
        'test_key_present': bool(re.fullmatch(r'(?:sk|rk|skcs|rkcs)_test_[A-Za-z0-9]+', key)),
        'webhook_present': bool(re.fullmatch(r'whsec_[A-Za-z0-9]+', secret)),
        'account_pinned': bool(re.fullmatch(r'acct_[A-Za-z0-9]+', account)),
    }


def configured():
    return all(configuration().values())


def origin():
    value = settings.PUBLIC_ORIGIN.rstrip('/')
    parsed = urlsplit(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path
            or not parsed.hostname or (parsed.scheme != 'https' and not (
                settings.DEBUG and parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')))):
        raise BillingUnavailable('Invalid application origin')
    return value


def safe_checkout(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r'[\s\\]', url):
        return False
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname == 'checkout.stripe.com'
                and not p.username and not p.password and p.port in (None, 443)
                and p.path.startswith('/c/pay/cs_test_'))
    except ValueError:
        return False


def client():
    if not configured():
        raise BillingUnavailable('Sandbox is not configured')
    origin()
    api = stripe.StripeClient(os.environ['STRIPE_TEST_SECRET_KEY'].strip(),
        stripe_version=API_VERSION, max_network_retries=1,
        http_client=stripe.RequestsClient(timeout=10))
    # Pin BOTH the account and test mode; a successful CLI login is not proof.
    account = plain(api.v1.accounts.retrieve_current())
    balance = plain(api.v1.balance.retrieve())
    if (account.get('id') != os.environ['STRIPE_TEST_ACCOUNT_ID'].strip()
            or account.get('object') != 'account' or balance.get('object') != 'balance'
            or balance.get('livemode') is not False):
        raise BillingUnavailable('Stripe account/test mode mismatch')
    return api


def test_object(value, object_type=None, identifier=None):
    obj = plain(value)
    if (not isinstance(obj, dict) or obj.get('livemode') is not False
            or (object_type and obj.get('object') != object_type)
            or (identifier and obj.get('id') != identifier)):
        raise ReconciliationError('Unverified provider object')
    return obj
