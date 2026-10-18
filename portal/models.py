import uuid
import secrets
from django.conf import settings
from django.db import models


class OwnerAdminChallenge(models.Model):
    """Single-use Google nonce; no credentials or customer data are stored."""
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

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
    category = models.CharField(max_length=20, choices=[('support','Support'),('complaint','Complaint'),('privacy','Privacy')])
    status = models.CharField(max_length=20, default='open', choices=[('open','Open'),('resolved','Resolved')])
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

class GoogleIdentity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='google_identity')
    subject = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

def referral_code():
    return secrets.token_urlsafe(18)

class ReferralCode(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=24, default=referral_code, unique=True, editable=False)

class Referral(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='referrals_sent')
    invitee = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_received')
    status = models.CharField(max_length=20, default='pending', choices=[('pending','Awaiting verification'),('verified','Email verified')])
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(referrer=models.F('invitee')), name='referral_not_self')]

class AccountPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account_notifications = models.BooleanField(default=False)
