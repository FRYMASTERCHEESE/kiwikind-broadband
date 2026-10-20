import uuid
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import path, reverse
from django.utils.html import format_html
from portal.models import AuditEvent
from .models import TestAgreement, TestInvoice, TestEvent


class TestAgreementForm(forms.ModelForm):
    class Meta:
        model = TestAgreement
        fields = '__all__'

    def clean(self):
        values = super().clean()
        if self.instance.pk and not self.instance._state.adding:
            current = TestAgreement.objects.select_for_update().get(pk=self.instance.pk)
            if current.checkout_started_at:
                raise ValidationError('A checkout has started. Its reviewed terms are immutable; reconcile before any replacement.')
        return values


@admin.register(TestAgreement)
class Agreements(admin.ModelAdmin):
    form = TestAgreementForm
    actions = None
    list_display = ['label','user','monthly_cents','setup_cents','reviewed','status']
    readonly_fields = ['terms_version','created_by','created_at','checkout_started_at','checkout_email','checkout_id',
        'customer_id','subscription_id','status','cancel_at_period_end','updated_at']

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.checkout_started_at:
            return [f.name for f in self.model._meta.fields]
        return self.readonly_fields

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.checkout_started_at) and super().has_change_permission(request,obj)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        if change:
            obj.terms_version = uuid.uuid4()
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='sandbox_agreement_review',reference=str(obj.pk))


@admin.register(TestEvent)
class ReadOnlyRecords(admin.ModelAdmin):
    actions = None
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False


@admin.register(TestInvoice)
class Invoices(ReadOnlyRecords):
    list_display = ['id','agreement','amount_cents','status','refunded_cents','dispute_status']
    readonly_fields = [f.name for f in TestInvoice._meta.fields] + ['refund_link']
    def get_urls(self):
        from .views import refund_page
        return [path('<uuid:invoice_id>/refund/',admin.site.admin_view(refund_page),name='sandbox-invoice-refund')] + super().get_urls()
    @admin.display(description='Test refund')
    def refund_link(self,obj):
        if not obj or obj.status != 'paid':
            return 'Only a verified paid TEST invoice can be refunded.'
        return format_html('<a href="{}">Review and confirm full TEST refund</a>',reverse('admin:sandbox-invoice-refund',args=[obj.pk]))
