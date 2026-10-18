from django.contrib import admin
from django.conf import settings
from django.contrib.auth.models import User, Group
from .models import Order, Ticket, Message, Invoice, AuditEvent, PrivacyRequest, Customer
from django.urls import reverse
from django.utils.html import format_html

admin.site.site_header='KiwiKind Broadband operations · Pre-launch'

# Additional server-side identity restriction; this does not replace MFA or staff permissions.
ADMIN_OWNER_EMAIL = 'kiwikindbroadband@gmail.com'
_original_has_permission = admin.site.has_permission

def owner_only_admin_permission(request):
    from .owner_admin import owner_session
    return (_original_has_permission(request)
            and request.user.is_superuser
            and request.user.email.strip().casefold() == ADMIN_OWNER_EMAIL
            and (not settings.OWNER_GOOGLE_ADMIN_ENABLED or owner_session(request)))

admin.site.has_permission = owner_only_admin_permission
_original_login = admin.site.login

def owner_admin_login(request, extra_context=None):
    if settings.OWNER_GOOGLE_ADMIN_ENABLED:
        from .owner_admin import owner_login
        return owner_login(request, extra_context)
    return _original_login(request, extra_context)

admin.site.login = owner_admin_login

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(Customer)
class Customers(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_active', 'date_joined', 'last_login']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    list_filter = ['is_active', 'date_joined']
    ordering = ['-date_joined']
    actions = None
    fields = ['email', 'username', 'first_name', 'last_name', 'is_active',
              'date_joined', 'last_login', 'sign_in_method', 'customer_records']
    readonly_fields = ['email', 'username', 'date_joined', 'last_login',
                       'sign_in_method', 'customer_records']

    def get_queryset(self, request):
        # Owner and operator accounts must never be editable as customers.
        return super().get_queryset(request).filter(is_staff=False, is_superuser=False).exclude(
            email__iexact=ADMIN_OWNER_EMAIL).exclude(username='kiwikind-owner-admin')

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description='Sign-in method')
    def sign_in_method(self, obj):
        google = hasattr(obj, 'google_identity')
        password = obj.has_usable_password()
        return 'Google and password' if google and password else 'Google' if google else 'Password' if password else 'Not configured'

    @admin.display(description='Related customer records')
    def customer_records(self, obj):
        links = []
        for model, label in [('order', 'Broadband requests'), ('ticket', 'Support tickets'),
                             ('invoice', 'Invoices'), ('privacyrequest', 'Privacy requests')]:
            links.append(format_html('<a href="{}?user__id__exact={}">{}</a>',
                                     reverse('admin:portal_' + model + '_changelist'), obj.pk, label))
        return format_html('{} · {} · {} · {}', *links)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='customer_account_updated',
                                  reference=f'customer:{obj.pk};fields:{",".join(sorted(form.changed_data))}')

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
