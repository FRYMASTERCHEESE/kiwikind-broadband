from django.contrib import admin
from django.contrib.auth.models import User, Group
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest
from .models import PricePlan, BillingAgreement, StripePayment, StripeEvent
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

# MFA enrolment/recovery is an offline operator action, never a web admin edit.
if admin.site.is_registered(TOTPDevice):
    admin.site.unregister(TOTPDevice)

@admin.register(PricePlan)
class Prices(admin.ModelAdmin):
    list_display = ['name','network','status','address_specific','valid_until']
    readonly_fields = ['approved_by','approved_at','updated_at']
    def has_delete_permission(self, request, obj=None): return False
    def save_model(self, request, obj, form, change):
        obj.full_clean()
        obj.approved_by = request.user if obj.status == 'approved' else None
        obj.approved_at = timezone.now() if obj.status == 'approved' else None
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='price_'+obj.status,reference=str(obj.pk))

admin.site.site_header='KiwiKind Broadband operations · Pre-launch'
admin.site.unregister(User)
admin.site.unregister(Group)

class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

@admin.register(Invoice, AuditEvent)
class Ledger(ReadOnly): pass

@admin.register(StripePayment)
class Payments(ReadOnly):
    list_display=['id','invoice','amount_cents','paid','refunded_cents']
    actions=['request_full_test_refund']
    @admin.action(description='Request FULL refund of selected synthetic Stripe payments',permissions=['view'])
    def request_full_test_refund(self,request,queryset):
        import stripe
        from .stripe_staging import configured, gateway_options
        if not configured():
            self.message_user(request,'Sandbox Stripe is disabled.',level='ERROR');return
        for payment in queryset.select_related('invoice'):
            if not payment.invoice or not payment.invoice.sandbox or not payment.paid or not payment.payment_intent:
                self.message_user(request,'Only settled synthetic payments can be refunded.',level='ERROR');continue
            try:
                stripe.Refund.create(payment_intent=payment.payment_intent,
                    idempotency_key='kiwikind-test-refund-'+str(payment.pk),**gateway_options())
                AuditEvent.objects.create(actor=request.user,action='test_refund_requested',reference=str(payment.pk))
                self.message_user(request,'Test refund submitted; webhook reconciliation is required.')
            except stripe.StripeError:self.message_user(request,'Stripe unavailable. Retry safely after reviewing provider state.',level='ERROR')

admin.site.register(StripeEvent,ReadOnly)

@admin.register(BillingAgreement)
class SyntheticAgreements(admin.ModelAdmin):
    list_display=['id','user','monthly_cents','synthetic_reviewed','status']
    readonly_fields=['id','subscription_id','checkout_id','checkout_url','status','consent_at','created_at']
    def has_delete_permission(self,request,obj=None):return False
    def has_change_permission(self,request,obj=None):
        return super().has_change_permission(request,obj) and (obj is None or not obj.checkout_id)
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='synthetic_agreement_review',reference=str(obj.pk))

class Audited(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='admin_update',reference=f'{obj._meta.model_name}:{obj.pk}')

@admin.register(Order)
class Orders(Audited):
    list_display=['id','status','created_at']
    readonly_fields=['id','user','address','postcode','contact_name','phone','idempotency_key','consent_version','created_at']
    list_filter=['status']

class Replies(admin.TabularInline):
    model=Message
    fields=['author','body','created_at']
    readonly_fields=['author','created_at']
    extra=1
    can_delete=False
    def has_change_permission(self,request,obj=None): return False

@admin.register(Ticket)
class Tickets(Audited):
    list_display=['id','category','status','created_at']
    readonly_fields=['id','user','subject','category','created_at']
    inlines=[Replies]
    def save_formset(self,request,form,formset,change):
        for item in formset.save(commit=False):
            item.author=request.user; item.save()
            AuditEvent.objects.create(actor=request.user,action='support_reply',reference=str(item.ticket_id))

@admin.register(PrivacyRequest)
class PrivacyRequests(Audited):
    list_display=['id','status','created_at']
    readonly_fields=['user','created_at']
