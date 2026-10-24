"""Real-billing records are separate from the existing sandbox ledger.

No record or price is seeded. Owner review, customer consent and release gates
are all required before a real Checkout session can be created.
"""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from portal.owner_admin import OWNER_EMAIL, OWNER_USERNAME


def approved_agreements():
    return LiveAgreement.objects.filter(reviewed=True, approved_at__isnull=False,
        approved_by__username=OWNER_USERNAME, approved_by__email=OWNER_EMAIL,
        approved_by__is_active=True, approved_by__is_staff=True, approved_by__is_superuser=True,
        approved_by__owneridentity__verified_email=OWNER_EMAIL).exclude(broadband_order__order__status='cancelled')


def default_price_policy():
    if getattr(settings, 'KIWIKIND_VETTA_SOURCE_PRICES_ONLY', False):
        return 'vetta_source_v1'
    return ('all_in_v3' if getattr(settings, 'KIWIKIND_ALL_IN_RETAIL_ENABLED', False)
            else 'legacy_v1')


class LiveAgreement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    label = models.CharField(max_length=100)
    service_reference = models.CharField(max_length=100, unique=True,
        help_text='Private KiwiKind service reference. Do not enter passwords, card data or supplier credentials.')
    source_monthly_cents = models.PositiveIntegerField(validators=[MaxValueValidator(1000000)], help_text='Combined supplier monthly amount in cents, excluding GST. The server adds GST then exactly $3 including GST once.')
    source_setup_cents = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(1000000)], help_text='Combined confirmed supplier setup amount in cents, excluding GST. The server adds GST then exactly $10 including GST once. Blank blocks approval.')
    pricing_policy = models.CharField(max_length=16, default=default_price_policy, editable=False)
    monthly_cents = models.PositiveIntegerField(default=0, editable=False, validators=[MinValueValidator(50), MaxValueValidator(1200000)],
        help_text='Final monthly NZD total in cents, including any applicable GST. No extra tax is added at checkout.')
    setup_cents = models.PositiveIntegerField(null=True, blank=True, editable=False, validators=[MaxValueValidator(1200000)],
        help_text='Final one-off total in cents. Enter 0 only when no setup charge applies; blank means undecided.')
    tax_treatment = models.CharField(max_length=20, default='gst_included', editable=False)
    service_terms = models.TextField(max_length=8000,
        help_text='The exact service, speed, billing-start, contract, cancellation and refund terms for customer acceptance.')
    bill_from = models.DateField(null=True, blank=True,
        help_text='Earliest approved payment date. Checkout charges immediately when the customer confirms, never before this date.')
    supplier_confirmed = models.BooleanField(default=False,
        help_text='Owner confirms this specific service can be supplied. Payment never automatically activates broadband.')
    terms_version = models.UUIDField(default=uuid.uuid4, editable=False)
    reviewed = models.BooleanField(default=False, help_text='Owner-reviewed offer; separate server release approval and customer consent are still required.')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='live_billing_approvals', editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='live_billing_created', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    checkout_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    checkout_email = models.EmailField(blank=True, editable=False)
    gst_rate_id = models.CharField(max_length=255, blank=True, editable=False)
    checkout_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    customer_id = models.CharField(max_length=255, blank=True, editable=False)
    subscription_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    status = models.CharField(max_length=30, default='pending', editable=False)
    cancel_at_period_end = models.BooleanField(default=False, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer payment agreement'
        verbose_name_plural = 'Customer payment agreements'
        constraints = [
            models.CheckConstraint(condition=models.Q(monthly_cents__gte=50, monthly_cents__lte=1200000), name='live_monthly_bounded'),
            models.CheckConstraint(condition=models.Q(setup_cents__isnull=True) | models.Q(setup_cents__gte=0, setup_cents__lte=1200000), name='live_setup_bounded'),
        ]

    def calculate_quote(self):
        from .retail_pricing import order_quote
        try:
            quote = order_quote(self.source_monthly_cents, self.source_setup_cents,
                source_prices_only=(self.pricing_policy == 'vetta_source_v1'),
                include_processing=(self.pricing_policy in ('all_in_v2', 'all_in_v3')),
                monthly_price_increase_cents=(400 if self.pricing_policy == 'all_in_v3' else 0))
        except ValueError as exc:
            raise ValidationError('Enter confirmed supplier amounts as non-negative integer cents.') from exc
        self.monthly_cents, self.setup_cents = quote['monthly_cents'], quote['setup_cents']
        self.tax_treatment = 'gst_included'

    def clean_fields(self, exclude=None):
        self.calculate_quote()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.calculate_quote()
        if not self._state.adding:
            current = type(self).objects.get(pk=self.pk)
            protected = ('user_id', 'label', 'service_reference', 'source_monthly_cents',
                'source_setup_cents', 'monthly_cents', 'setup_cents', 'pricing_policy', 'service_terms',
                'bill_from', 'supplier_confirmed', 'terms_version', 'reviewed',
                'approved_by_id', 'approved_at', 'gst_rate_id')
            if current.checkout_started_at and any(getattr(self, f) != getattr(current, f) for f in protected):
                raise ValidationError('Payment agreement is immutable after checkout starts.')
        super().save(*args, **kwargs)

    def clean(self):
        if self.pricing_policy not in ('legacy_v1', 'all_in_v2', 'all_in_v3', 'vetta_source_v1'):
            raise ValidationError('Invalid agreement pricing policy')
        self.calculate_quote()
        if self.reviewed and 'Complete the confirmed connection, billing-start, contract, cancellation and refund terms before approving this offer.' in self.service_terms:
            raise ValidationError('Replace the draft instructions with confirmed service terms before approval.')
        if self.reviewed and (not self.supplier_confirmed or not self.bill_from or self.setup_cents is None
                or self.tax_treatment != 'gst_included'
                or not self.service_terms.strip() or not self.label.strip() or not self.service_reference.strip()):
            raise ValidationError('Review requires confirmed service supply, final monthly/setup totals, tax treatment, payment-start date and written service terms.')

    def check_checkout_eligibility(self):
        self.full_clean()
        linked = getattr(self, 'broadband_order', None)
        if linked and linked.order.status == 'cancelled':
            raise ValidationError('This broadband order has been cancelled.')
        if not approved_agreements().filter(pk=self.pk).exists():
            raise ValidationError('A current verified-owner approval is required.')
        if not self.bill_from or self.bill_from > timezone.localdate():
            raise ValidationError('The approved payment-start date has not arrived.')
        if not self.user.is_active:
            raise ValidationError('The customer account is not active.')

    def __str__(self):
        return self.label


class LiveInvoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agreement = models.ForeignKey(LiveAgreement, on_delete=models.PROTECT, related_name='invoices')
    provider_id = models.CharField(max_length=255, unique=True)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=30)
    payment_intent = models.CharField(max_length=255, blank=True, db_index=True)
    refunded_cents = models.PositiveIntegerField(default=0)
    dispute_status = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Stripe invoice'
        constraints = [models.CheckConstraint(condition=models.Q(refunded_cents__lte=models.F('amount_cents')), name='live_refund_bounded')]


class LiveEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    kind = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Live webhook receipt'


class OneDollarVerification(models.Model):
    """At most one owner-authorised real $1 payment; unrelated to broadband billing."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='one_dollar_verification')
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    checkout_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    state = models.CharField(max_length=30, default='not_started', editable=False)
    refunded_cents = models.PositiveIntegerField(default=0, editable=False)
    dispute_status = models.CharField(max_length=40, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Owner one-dollar payment verification'
        constraints = [
            models.CheckConstraint(condition=models.Q(refunded_cents__lte=100), name='owner_dollar_refund_bound'),
        ]
