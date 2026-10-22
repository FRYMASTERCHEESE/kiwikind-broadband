"""Isolated test billing records. Never mixed with real customer invoices or services."""
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class TestAgreement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    label = models.CharField(max_length=100, default='Synthetic billing test')
    monthly_cents = models.PositiveIntegerField(validators=[MinValueValidator(50), MaxValueValidator(1000000)])
    setup_cents = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(1000000)])
    terms_version = models.UUIDField(default=uuid.uuid4, editable=False)
    reviewed = models.BooleanField(default=False, help_text='Explicitly authorise synthetic test billing for this account; never a real broadband order.')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='billing_tests_created', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    checkout_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    checkout_email = models.EmailField(blank=True, editable=False)
    checkout_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    customer_id = models.CharField(max_length=255, blank=True, editable=False)
    subscription_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    status = models.CharField(max_length=30, default='pending', editable=False)
    cancel_at_period_end = models.BooleanField(default=False, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sandbox billing agreement'
        verbose_name_plural = 'Sandbox billing agreements (test only)'
        constraints = [
            models.CheckConstraint(condition=models.Q(monthly_cents__gte=50, monthly_cents__lte=1000000), name='test_monthly_bounded'),
            models.CheckConstraint(condition=models.Q(setup_cents__gte=0, setup_cents__lte=1000000), name='test_setup_bounded'),
        ]

    def __str__(self):
        return f'TEST ONLY: {self.label}'


class TestInvoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agreement = models.ForeignKey(TestAgreement, on_delete=models.PROTECT, related_name='invoices')
    provider_id = models.CharField(max_length=255, unique=True)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=30)
    payment_intent = models.CharField(max_length=255, blank=True, db_index=True)
    refunded_cents = models.PositiveIntegerField(default=0)
    dispute_status = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sandbox invoice'
        constraints = [models.CheckConstraint(condition=models.Q(refunded_cents__lte=models.F('amount_cents')), name='test_refund_bounded')]


class TestEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    kind = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sandbox webhook receipt'


class OwnerSandboxRun(models.Model):
    """Isolated provider QA; not a customer agreement or permission to sell."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    agreement = models.OneToOneField(TestAgreement, on_delete=models.PROTECT)
    scenario = models.CharField(max_length=20, choices=[('renewal','Renewal'),('decline-3ds','Decline and 3DS')])
    clock_id = models.CharField(max_length=255, blank=True)
    customer_id = models.CharField(max_length=255, blank=True)
    advance_to = models.BigIntegerField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# Django discovers these separate production records without mixing ledgers.
from .live_models import LiveAgreement, LiveInvoice, LiveEvent  # noqa: E402,F401
