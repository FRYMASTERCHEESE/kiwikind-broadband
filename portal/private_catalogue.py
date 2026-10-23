"""Private, immutable catalogue releases. No supplier prices in source files."""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_payload(payload, publish=False):
    """A product is a complete service configuration, not a component row.

    Keep incomplete research in private drafts. Publication requires explicit
    confirmation of every price, data policy, installation and service term.
    """
    def fail():
        raise ValidationError('Invalid private catalogue: check service IDs, amounts, usage, terms and verification.')

    def amount(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{1,5}\.\d{2}', value):
            fail()
        try:
            if not 0 <= Decimal(value) <= 10000:
                fail()
        except InvalidOperation:
            fail()

    def text(value, limit=2000):
        if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
            fail()

    def key(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', value):
            fail()

    if not isinstance(payload, list) or not 1 <= len(payload) <= 200:
        fail()
    ids, names = set(), set()
    for p in payload:
        if not isinstance(p, dict):
            fail()
        key(p.get('id')); text(p.get('name'), 160); text(p.get('description'))
        if p.get('family') not in ('ufb', 'vector', 'adsl', 'vdsl', 'rbi', 'fixed-wireless', 'mobile-4g'):
            fail()
        identity = p['name'].strip().casefold()
        if p['id'] in ids or identity in names or p.get('kind') != 'complete_service' or p.get('gst_basis') != 'exclusive':
            fail()
        ids.add(p['id']); names.add(identity)
        amount(p.get('base')); amount(p.get('baseSetup'))
        text(p.get('allowance')); text(p.get('terms')); text(p.get('source_ref'), 160)
        if p.get('price_status') not in ('unverified', 'verified') or type(p.get('setupUnknown')) is not bool:
            fail()
        if not isinstance(p.get('unverified'), list) or any(not isinstance(v, str) for v in p['unverified']):
            fail()
        if publish and (p['unverified'] or p['price_status'] != 'verified' or p['setupUnknown']):
            fail()
        groups = p.get('groups')
        if not isinstance(groups, list) or not groups or len(groups) > 10:
            fail()
        group_ids = set()
        headline = Decimal(p['base'])
        for group in groups:
            if not isinstance(group, dict):
                fail()
            key(group.get('id')); text(group.get('label'), 160)
            if group['id'] in group_ids:
                fail()
            group_ids.add(group['id'])
            options = group.get('options')
            if not isinstance(options, list) or not options or len(options) > 200:
                fail()
            option_ids = set()
            for opt in options:
                if not isinstance(opt, dict):
                    fail()
                key(opt.get('id')); text(opt.get('name'), 160)
                if opt['id'] in option_ids or type(opt.get('unknown')) is not bool:
                    fail()
                option_ids.add(opt['id'])
                amount(opt.get('monthly')); amount(opt.get('setup'))
                usage = opt.get('usage')
                if usage is not None:
                    if not isinstance(usage, dict) or usage.get('unit') not in ('GB', 'Mbps'):
                        fail()
                    amount(usage.get('rate'))
                if publish and opt['unknown']:
                    fail()
            headline += min(Decimal(o['monthly']) for o in options)
        # Derived, never accept a misleading headline from an import.
        p['headline'] = f'{headline:.2f}'
    return payload


def approved_products():
    from .models import PrivateCatalogueRelease
    from .owner_admin import OWNER_USERNAME, OWNER_EMAIL
    release = PrivateCatalogueRelease.objects.filter(
        active=True, approved_at__isnull=False, verified_on__lte=timezone.localdate(),
        valid_until__gte=timezone.localdate(), approved_by__username=OWNER_USERNAME,
        approved_by__email=OWNER_EMAIL, approved_by__is_active=True,
        approved_by__is_staff=True, approved_by__is_superuser=True,
        approved_by__owneridentity__verified_email=OWNER_EMAIL).first()
    if release is None:
        return [], 'unpublished'
    try:
        payload = validate_payload(release.payload, publish=True)
        if release.approved_digest != digest(payload):
            return [], 'unpublished'
    except (ValidationError, TypeError, ValueError, KeyError):
        return [], 'unpublished'
    return payload, release.approved_digest[:24]
