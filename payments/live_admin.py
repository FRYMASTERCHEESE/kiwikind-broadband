"""Owner-MFA administration; no keys are accepted or shown in these forms."""
import uuid
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone
from portal.models import AuditEvent
from .live_models import LiveAgreement, LiveInvoice, LiveEvent


class LiveAgreementForm(forms.ModelForm):
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)
    confirm_review = forms.BooleanField(required=False,
        label='I approve these exact customer totals and service terms for real billing',
        help_text='This does not enable Stripe, publish a plan, or authorise a charge without customer consent.')

    class Meta:
        model = LiveAgreement
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['expected_version'] = str(self.instance.terms_version)

    def clean(self):
        values = super().clean()
        if self.instance.pk and not self.instance._state.adding:
            current = LiveAgreement.objects.select_for_update().get(pk=self.instance.pk)
            if current.checkout_started_at:
                raise ValidationError('Checkout has started. Its customer, price and terms are locked; reconcile the payment before replacement.')
            if values.get('expected_version') != str(current.terms_version):
                raise ValidationError('This offer changed. Reload before saving.')
        if values.get('reviewed') and not values.get('confirm_review'):
            self.add_error('confirm_review', 'Fresh explicit approval is required; otherwise save unreviewed.')
        return values


@admin.register(LiveAgreement)
class CustomerAgreements(admin.ModelAdmin):
    form = LiveAgreementForm
    actions = None
    list_display = ['label', 'user', 'monthly_cents', 'setup_cents', 'reviewed', 'status', 'bill_from']
    readonly_fields = ['terms_version', 'approved_by', 'approved_at', 'created_by', 'created_at',
        'checkout_started_at', 'checkout_email', 'checkout_id', 'customer_id', 'subscription_id',
        'status', 'cancel_at_period_end', 'updated_at']

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.checkout_started_at) and super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.checkout_started_at:
            return [f.name for f in LiveAgreement._meta.fields]
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        if change:
            obj.terms_version = uuid.uuid4()
        obj.approved_by = request.user if obj.reviewed else None
        obj.approved_at = timezone.now() if obj.reviewed else None
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='live_offer_review' if obj.reviewed else 'live_offer_draft', reference=str(obj.pk))


@admin.register(LiveInvoice)
class CustomerInvoices(admin.ModelAdmin):
    actions = None
    list_display = ['id', 'agreement', 'amount_cents', 'status', 'refunded_cents', 'dispute_status']
    readonly_fields = [f.name for f in LiveInvoice._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LiveEvent)
class LiveReceipts(admin.ModelAdmin):
    actions = None
    list_display = ['id', 'kind', 'received_at']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
