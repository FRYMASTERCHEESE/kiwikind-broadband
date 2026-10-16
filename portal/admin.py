from django.contrib import admin
from django.contrib.auth.models import User, Group
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest

admin.site.site_header='KiwiKind Broadband operations · Pre-launch'

# Additional server-side identity restriction; this does not replace MFA or staff permissions.
ADMIN_OWNER_EMAIL = 'kiwikindbroadband@gmail.com'
_original_has_permission = admin.site.has_permission

def owner_only_admin_permission(request):
    return (_original_has_permission(request)
            and request.user.is_superuser
            and request.user.email.strip().casefold() == ADMIN_OWNER_EMAIL)

admin.site.has_permission = owner_only_admin_permission

admin.site.unregister(User)
admin.site.unregister(Group)

class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

@admin.register(Invoice, AuditEvent)
class Ledger(ReadOnly): pass

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
