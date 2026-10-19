"""Private onboarding records. These are not supplier orders or customer bills."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class DraftPlan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    download_mbps = models.PositiveIntegerField(null=True, blank=True)
    upload_mbps = models.PositiveIntegerField(null=True, blank=True)
    wholesale_ex_gst = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    retail_ex_gst = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    setup_ex_gst = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    source_reference = models.CharField(max_length=160, blank=True, help_text='Private quote/document reference, never credentials or a signed URL.')
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(max_length=2000, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [models.CheckConstraint(condition=models.Q(**{f'{field}__gte': 0}) | models.Q(**{f'{field}__isnull': True}), name=f'draft_{field}_nonnegative') for field in ['wholesale_ex_gst', 'retail_ex_gst', 'setup_ex_gst']]

    def clean(self):
        if self.verified_at and (not self.source_reference.strip() or self.verified_at > timezone.now()):
            raise ValidationError('A verified quote needs a source reference and a date that is not in the future.')

    def __str__(self):
        return f'{self.name} (draft only)'


class AvailabilityEvidence(models.Model):
    address = models.CharField(max_length=300)
    postcode = models.CharField(max_length=4, validators=[RegexValidator(r'^[0-9]{4}$', 'Use a four-digit NZ postcode.')])
    result = models.CharField(max_length=20, choices=[('unknown', 'Not verified'), ('available', 'Fibre available in portal'), ('unavailable', 'Not available in portal')], default='unknown')
    source_reference = models.CharField(max_length=160, blank=True, help_text='Reference from a manual Vetta portal check. Do not paste credentials.')
    checked_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True, help_text='Operator recheck deadline, not a Vetta guarantee.')
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rehearsal = models.BooleanField(default=True, help_text='Synthetic practice evidence. Never used as real availability.')
    notes = models.TextField(max_length=2000, blank=True)

    class Meta:
        ordering = ['-id']

    def clean(self):
        if self.result != 'unknown':
            if not all([self.source_reference.strip(), self.checked_at, self.valid_until]):
                raise ValidationError('A result requires a portal reference, check time and recheck deadline.')
            if self.checked_at > timezone.now() or self.valid_until <= self.checked_at:
                raise ValidationError('Use a past check time and a later recheck deadline.')

    def __str__(self):
        return f'{self.address} — {self.get_result_display()}'


class WholesaleOrder(models.Model):
    STATES = [('draft', 'Draft'), ('availability_review', 'Availability review'), ('quote_review', 'Quote review'),
              ('ready', 'Prepared — launch approval required'), ('submitted', 'Practice: submitted in portal'),
              ('provisioning', 'Practice: provisioning'), ('active', 'Practice: active'), ('cancelled', 'Closed / cancelled')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_request = models.OneToOneField('portal.Order', null=True, blank=True, on_delete=models.PROTECT, related_name='wholesale_preparation')
    rehearsal = models.BooleanField(default=True, help_text='Practice cases must use synthetic data and cannot link customer records.')
    address = models.CharField(max_length=300)
    postcode = models.CharField(max_length=4, validators=[RegexValidator(r'^[0-9]{4}$', 'Use a four-digit NZ postcode.')])
    plan = models.ForeignKey(DraftPlan, null=True, blank=True, on_delete=models.PROTECT)
    availability = models.ForeignKey(AvailabilityEvidence, null=True, blank=True, on_delete=models.PROTECT)
    state = models.CharField(max_length=30, choices=STATES, default='draft', editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.rehearsal and self.customer_request_id:
            raise ValidationError('Practice cases must not link customer requests.')
        if not self.rehearsal and not self.customer_request_id:
            raise ValidationError('Real preparation must link an existing customer request. New intake is closed.')
        if self.customer_request_id:
            from .wholesale import address_matches
            if not address_matches(self, self.customer_request):
                raise ValidationError('The address must match the linked customer request.')

    def __str__(self):
        return f'{"PRACTICE" if self.rehearsal else "PREPARATION"} {self.pk}'


class WholesaleFault(models.Model):
    STATES = [('triage', 'First-line triage'), ('ready', 'Prepared for escalation — launch approval required'),
              ('escalated', 'Practice: escalated in portal'), ('investigating', 'Practice: supplier investigating'),
              ('resolved', 'Resolved / practice complete'), ('closed', 'Closed')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.OneToOneField('portal.Ticket', null=True, blank=True, on_delete=models.PROTECT, related_name='wholesale_preparation')
    rehearsal = models.BooleanField(default=True)
    summary = models.CharField(max_length=150)
    service_reference = models.CharField(max_length=100, blank=True)
    diagnostics = models.TextField(max_length=2000, blank=True, help_text='First-line checks / line-test findings. Exclude passwords and payment details.')
    state = models.CharField(max_length=30, choices=STATES, default='triage', editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.rehearsal and self.ticket_id:
            raise ValidationError('Practice faults must not link customer tickets.')
        if not self.rehearsal and not self.ticket_id:
            raise ValidationError('Real preparation must link an existing support ticket.')
        if self.ticket_id and self.ticket.category != 'support':
            raise ValidationError('Only support tickets can prepare a network fault. Handle privacy and complaints internally.')

    def __str__(self):
        return f'{"PRACTICE" if self.rehearsal else "PREPARATION"} {self.summary}'


class WholesaleEvent(models.Model):
    order = models.ForeignKey(WholesaleOrder, null=True, blank=True, on_delete=models.PROTECT, related_name='events')
    fault = models.ForeignKey(WholesaleFault, null=True, blank=True, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submission_key = models.UUIDField(unique=True)
    from_state = models.CharField(max_length=30)
    to_state = models.CharField(max_length=30)
    reference = models.CharField(max_length=160, blank=True)
    note = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.CheckConstraint(condition=(models.Q(order__isnull=False, fault__isnull=True) | models.Q(order__isnull=True, fault__isnull=False)), name='wholesale_event_one_case')]
