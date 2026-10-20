import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

class EmailVerification(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email = models.EmailField()
    verified_at = models.DateTimeField(auto_now_add=True)

class PricePlan(models.Model):
    name = models.CharField(max_length=120)
    source = models.TextField(help_text='Supplier quote or document reference; admin only')
    network = models.CharField(max_length=100)
    download_mbps = models.PositiveIntegerField()
    upload_mbps = models.PositiveIntegerField()
    wholesale_ex_gst = models.DecimalField(max_digits=9, decimal_places=2)
    wholesale_incl_gst = models.DecimalField(max_digits=9, decimal_places=2)
    setup_ex_gst = models.DecimalField(max_digits=9, decimal_places=2)
    setup_incl_gst = models.DecimalField(max_digits=9, decimal_places=2)
    valid_until = models.DateField(null=True, blank=True)
    address_specific = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default='draft', choices=[('draft','Draft'),('review','Needs review'),('approved','Owner approved')])
    retail_monthly_cents = models.PositiveIntegerField(null=True, blank=True)
    retail_setup_cents = models.PositiveIntegerField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        for ex, incl in [('wholesale_ex_gst','wholesale_incl_gst'),('setup_ex_gst','setup_incl_gst')]:
            a, b = getattr(self, ex), getattr(self, incl)
            if a is not None and b is not None and (a < 0 or b != (a * Decimal('1.15')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)):
                raise ValidationError({incl:'Must match ex GST × 1.15 rounded to cents.'})
        if self.status == 'approved' and (self.address_specific or not self.valid_until or self.valid_until < timezone.localdate() or not self.retail_monthly_cents or self.retail_setup_cents is None):
            raise ValidationError('General publication requires a current general quote and explicit retail prices.')

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    address = models.CharField(max_length=300)
    postcode = models.CharField(max_length=4)
    contact_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=25, blank=True)
    status = models.CharField(max_length=30, default='requested', choices=[('requested','Request received'),('reviewing','Under review'),('cancelled','Cancelled')])
    idempotency_key = models.UUIDField(default=uuid.uuid4)
    consent_version = models.CharField(max_length=30, default='prelaunch-2026-10-16')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','idempotency_key'], name='order_user_key')]

class Ticket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    subject = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=[('support','Support'),('fault','Fault'),('complaint','Complaint'),('privacy','Privacy')])
    status = models.CharField(max_length=20, default='open', choices=[('open','Open'),('investigating','Investigating'),('supplier_review','Supplier review pending'),('resolved','Resolved')])
    created_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

class Invoice(models.Model):
    """Read-only ledger foundation; no issuance, payment collection or fake bills."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    supplier_reference = models.CharField(max_length=100, unique=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='NZD')
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=[('unpaid','Unpaid'),('paid','Paid'),('void','Void')])
    sandbox = models.BooleanField(default=False, help_text='Synthetic test ledger only; never settle real invoices with test funds')

class BillingAgreement(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    monthly_cents = models.PositiveIntegerField()
    setup_cents = models.PositiveIntegerField(default=0)
    synthetic_reviewed = models.BooleanField(default=False)
    subscription_id = models.CharField(max_length=100,blank=True,unique=True,null=True)
    checkout_id = models.CharField(max_length=100,blank=True)
    checkout_url = models.URLField(max_length=2048,blank=True)
    status = models.CharField(max_length=30,default='pending')
    consent_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(default=timezone.now,editable=False)

class StripePayment(models.Model):
    invoice = models.OneToOneField(Invoice,on_delete=models.PROTECT,null=True,blank=True)
    agreement = models.ForeignKey(BillingAgreement,on_delete=models.PROTECT,null=True,blank=True)
    session_id = models.CharField(max_length=100,unique=True,null=True,blank=True)
    provider_invoice_id = models.CharField(max_length=100,unique=True,null=True,blank=True)
    payment_intent = models.CharField(max_length=100,blank=True)
    amount_cents = models.PositiveIntegerField()
    refunded_cents = models.PositiveIntegerField(default=0)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now,editable=False)

class StripeEvent(models.Model):
    id = models.CharField(max_length=100,primary_key=True)
    kind = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class RateBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    window = models.BigIntegerField()
    count = models.PositiveIntegerField(default=0)

class PrivacyRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='received', choices=[('received','Received'),('reviewing','Reviewing'),('completed','Completed')])
    created_at = models.DateTimeField(auto_now_add=True)
