"""Read-only checks for a published or deliberately hidden private catalogue."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = 'https://kiwikind-backend.onrender.com'
PRIVATE_KEYS = {'base', 'baseSetup', 'headline', 'source_ref', 'payload',
                'approved_by', 'approved_digest', 'monthly_addition_cents',
                'setup_addition_cents'}


def validate_admin_redirect(location):
    target = urllib.parse.urlsplit(urllib.parse.urljoin(ORIGIN, location))
    assert target.scheme == 'https' and not target.username and not target.password
    backend = target.netloc == urllib.parse.urlsplit(ORIGIN).netloc and target.path in (
        '/admin/login/', '/admin/owner-signin/', '/admin/mfa/')
    pages = target.netloc == 'frymastercheese.github.io' and target.path == '/kiwikind-broadband-website/owner.html' and not target.query and not target.fragment
    assert backend or pages, 'Unexpected private-admin redirect destination'


def assert_public(value):
    if isinstance(value, dict):
        assert not any(k in PRIVATE_KEYS or k.startswith('source_') for k in value), 'Private pricing field exposed'
        for item in value.values():
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)


def validate_catalogues(catalogue, compatibility):
    assert_public(catalogue)
    assert_public(compatibility)
    products, plans = catalogue['products'], compatibility['plans']
    assert catalogue['supplier_orders_enabled'] is False
    assert compatibility['live_orders_enabled'] is False
    assert catalogue['orders_enabled'] is bool(products)
    assert catalogue['gst_included'] is True and catalogue['currency'] == 'NZD'
    assert catalogue['payment_timing'] == 'after_connection_confirmation'
    by_id = {p['id']: p for p in plans}
    assert len(by_id) == len(plans) == len(products), 'Duplicate or mismatched catalogue'
    assert len({p['id'] for p in products}) == len(products), 'Duplicate product'
    assert len({p['name'].casefold() for p in products}) == len(products), 'Duplicate name'
    for product in products:
        q, old = product['default_quote'], by_id[product['id']]
        assert product['price_status'] == 'verified' and product['price_confirmation_required'] is True
        assert product['allowance'].strip() and product['terms'].strip()
        assert q['quote_complete'] and q['gst_included'] and q['price_confirmation_required']
        assert q['catalogue_version'] == catalogue['catalogue_version']
        assert all(type(q[k]) is int and q[k] >= 0 for k in ('monthly_cents', 'setup_cents', 'first_invoice_cents'))
        assert q['monthly_cents'] + q['setup_cents'] == q['first_invoice_cents']
        assert q['monthly_cents'] == old['retail_monthly_cents']
        assert q['setup_cents'] == old['retail_setup_cents']
        assert q['first_invoice_cents'] == old['first_invoice_cents']
        assert product['allowance'] == old['allowance']
        assert product['terms'] == old['terms']
        assert old['address_availability'] == 'unverified'
    return len(products)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read(path, json_required=False):
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(5):
        request = urllib.request.Request(ORIGIN + path, method='GET',
            headers={'User-Agent': 'KiwiKind-Public-Safety-Check/2.0', 'Accept': 'application/json'})
        try:
            try:
                response = opener.open(request, timeout=35)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                code, headers = response.code, response.headers
                body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise RuntimeError('Oversized public response; body withheld')
            # Free Render instances can return a temporary HTML wake-up page.
            if code in (502, 503, 504) or (json_required and 'application/json' not in headers.get('Content-Type', '')):
                raise urllib.error.URLError('Service not ready')
            return code, headers, body
        except (urllib.error.URLError, TimeoutError):
            if attempt == 4:
                raise RuntimeError('Public service did not become ready; body withheld') from None
            time.sleep(5)


def main():
    responses = []
    for path in ('/api/broadband/catalogue', '/api/plans'):
        code, headers, body = read(path, json_required=True)
        assert code == 200
        assert 'no-store' in headers.get('Cache-Control', '')
        assert not headers.get('Access-Control-Allow-Credentials')
        responses.append(json.loads(body))
    count = validate_catalogues(*responses)
    print(f'PASS: {count} public products; matching client catalogues; private costs absent; GST and totals checked')
    code, _, body = read('/api/status', json_required=True)
    assert code == 200
    status = json.loads(body)
    assert status['supplier_orders_enabled'] is False and status['live_services'] is False
    assert status['intake_enabled'] is False and status['availability'] == 'unverified'
    assert type(status['broadband_ordering_enabled']) is bool
    if count:
        assert status['broadband_ordering_enabled'] is True
    assert type(status['billing_enabled']) is bool
    for path in ('/admin/portal/draftplan/', '/admin/portal/privatecataloguerelease/'):
        code, headers, _ = read(path)
        if code in (301, 302, 303, 307, 308):
            validate_admin_redirect(headers.get('Location', ''))
        else:
            assert code in (401, 403, 404)
    for path in ('/api/orders', '/api/invoices', '/api/connection-progress', '/api/payments/summary', '/api/owner/catalogue'):
        assert read(path)[0] in (401, 403)
    print('PASS: private admin and customer data require authentication; supplier ordering remains disabled')
    print('Read-only verification: no sign-in, payment, customer request or supplier order created.')


if __name__ == '__main__':
    main()
