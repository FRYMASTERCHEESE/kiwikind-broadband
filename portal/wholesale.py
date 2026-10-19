"""Manual Vetta preparation. No HTTP client, API credentials or supplier mutations."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import uuid

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, WholesaleOrder, WholesaleFault, WholesaleEvent
from .suppliers import Availability, UnconfiguredSupplier

GST_RATE = Decimal('0.15')
LAUNCH_BLOCKERS = ('Wholesale agreement', 'Verified pricing and tax treatment', 'Operating and support processes', 'Legal and privacy approval')
ORDER_TRANSITIONS = {
    'draft': ('availability_review', 'cancelled'), 'availability_review': ('draft', 'quote_review', 'cancelled'),
    'quote_review': ('ready', 'availability_review', 'cancelled'), 'ready': ('submitted', 'quote_review', 'cancelled'),
    'submitted': ('provisioning', 'cancelled'), 'provisioning': ('active', 'cancelled'), 'active': (), 'cancelled': (),
}
FAULT_TRANSITIONS = {'triage': ('ready', 'closed'), 'ready': ('escalated', 'triage', 'closed'),
                     'escalated': ('investigating', 'resolved'), 'investigating': ('resolved',),
                     'resolved': ('closed', 'triage'), 'closed': ()}


def price_breakdown(value):
    """Draft NZD illustration only. Missing price is not zero; never use floats."""
    if value is None:
        return None
    try:
        if isinstance(value, (float, bool)):
            raise ValueError('Use a decimal amount.')
        net = Decimal(value)
        if not net.is_finite() or net < 0 or net > Decimal('99999.99') or net != net.quantize(Decimal('.01')):
            raise ValueError('Use a non-negative amount with at most two decimal places.')
        tax = (net * GST_RATE).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        return {'ex_gst': f'{net:.2f}', 'gst': f'{tax:.2f}', 'inc_gst': f'{net + tax:.2f}', 'currency': 'NZD'}
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Invalid decimal amount.') from exc


def address_matches(left, right):
    normalize = lambda value: ' '.join(value.strip().casefold().split())
    return normalize(left.address) == normalize(right.address) and left.postcode == right.postcode


class VettaManualSupplier(UnconfiguredSupplier):
    """Only reads explicitly supplied, verified portal evidence. Inherited writes fail closed."""
    def check_evidence(self, case, evidence, *, practice=False):
        if (not evidence or evidence.rehearsal != practice or not address_matches(case, evidence)
                or not evidence.source_reference.strip() or not evidence.checked_at or not evidence.valid_until
                or not evidence.checked_by_id or evidence.checked_at > timezone.now()
                or evidence.valid_until <= timezone.now() or evidence.result == 'unknown'):
            return Availability(None, None, 'Not verified: record a matching, current manual portal check.')
        return Availability(evidence.result == 'available', evidence.source_reference,
                            'Manual portal evidence only; not an order or availability guarantee.')


def require_operator(request):
    from django.conf import settings
    if not settings.ADMIN_ENABLED or not admin.site.has_permission(request):
        raise PermissionDenied


def transition(request, model, pk, *, target, revision, submission_key, reference='', note=''):
    require_operator(request)
    if model not in (WholesaleOrder, WholesaleFault):
        raise ValidationError('Unsupported case type.')
    key = uuid.UUID(str(submission_key))
    reference, note = reference.strip(), note.strip()
    if not note or len(note) > 2000 or len(reference) > 160 or '\x00' in note + reference:
        raise ValidationError('Add a short processing note, without credentials or invalid text.')
    field = 'order' if model is WholesaleOrder else 'fault'
    graph = ORDER_TRANSITIONS if model is WholesaleOrder else FAULT_TRANSITIONS
    with transaction.atomic():
        case = model.objects.select_for_update().get(pk=pk)
        if model is WholesaleOrder and case.customer_request_id:
            # Serialize against customer cancellation too, not just other operators.
            from .models import Order
            case.customer_request = Order.objects.select_for_update().get(pk=case.customer_request_id)
        previous = WholesaleEvent.objects.filter(submission_key=key).first()
        if previous:
            if (getattr(previous, f'{field}_id') != case.pk or previous.to_state != target
                    or previous.reference != reference or previous.note != note):
                raise ValidationError('This submission key was already used for a different update.')
            return case  # A double click / network retry cannot duplicate a transition.
        if case.revision != revision:
            raise ValidationError('This case changed in another tab. Reload before updating it.')
        if target not in graph[case.state]:
            raise ValidationError('That status change is not allowed.')
        case.full_clean()
        if not case.rehearsal:
            if model is WholesaleOrder and case.customer_request.status == 'cancelled' and target != 'cancelled':
                raise ValidationError('The customer cancelled this request. Close preparation without placing an order.')
            blocked = ('submitted', 'provisioning', 'active') if model is WholesaleOrder else ('escalated', 'investigating')
            if target in blocked:
                raise ValidationError('Live supplier processing is disabled pending agreements, pricing, operations and legal approval.')
        if model is WholesaleOrder and target in ('quote_review', 'ready', 'submitted', 'provisioning', 'active'):
            result = VettaManualSupplier().check_evidence(case, case.availability, practice=case.rehearsal)
            if result.available is not True:
                raise ValidationError('Record current, matching available-fibre evidence before proceeding.')
            if target != 'quote_review' and (not case.plan or case.plan.retail_ex_gst is None or case.plan.wholesale_ex_gst is None
                    or not case.plan.source_reference or not case.plan.verified_at):
                raise ValidationError('Record a verified wholesale quote and draft retail amount first.')
        if model is WholesaleFault and target in ('ready', 'escalated') and not (case.service_reference.strip() and case.diagnostics.strip()):
            raise ValidationError('Record the service reference and first-line diagnostic checks first.')
        if target in ('submitted', 'provisioning', 'active', 'escalated', 'investigating', 'resolved') and not reference:
            raise ValidationError('Record a practice portal / resolution reference for this update.')
        old = case.state
        # Conditional update also detects conflicts on engines without SELECT FOR UPDATE.
        changed = model.objects.filter(pk=pk, revision=revision).update(state=target, revision=revision + 1, updated_at=timezone.now())
        if changed != 1:
            raise ValidationError('This case changed. Reload before updating it.')
        WholesaleEvent.objects.create(**{field: case}, actor=request.user, submission_key=key,
                                      from_state=old, to_state=target, reference=reference, note=note)
        AuditEvent.objects.create(actor=request.user, action='wholesale_transition', reference=f'{field}:{pk}:{old}:{target}')
        case.refresh_from_db()
        return case
