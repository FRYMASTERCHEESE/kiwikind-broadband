"""Owner-only manual operations using the existing admin session and CSRF controls."""
import uuid
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import DraftPlan, AvailabilityEvidence, WholesaleOrder, WholesaleFault, WholesaleEvent, AuditEvent
from .wholesale import LAUNCH_BLOCKERS, ORDER_TRANSITIONS, FAULT_TRANSITIONS, price_breakdown, require_operator, transition


def dashboard(request):
    require_operator(request)
    return TemplateResponse(request, 'admin/wholesale/dashboard.html', {
        **admin.site.each_context(request), 'title': 'Wholesale preparation', 'blockers': LAUNCH_BLOCKERS,
        'plans': DraftPlan.objects.count(), 'checks': AvailabilityEvidence.objects.count(),
        'orders': WholesaleOrder.objects.count(), 'faults': WholesaleFault.objects.count(),
        'recent_events': WholesaleEvent.objects.select_related('actor').order_by('-created_at')[:10],
    })


class PrivateRecords(admin.ModelAdmin):
    actions = None

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'created_by_id') and not change:
            obj.created_by = request.user
        if isinstance(obj, AvailabilityEvidence):
            obj.checked_by = request.user
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='wholesale_record_saved', reference=f'{obj._meta.model_name}:{obj.pk}')


@admin.register(DraftPlan)
class Plans(PrivateRecords):
    list_display = ['name', 'review_status', 'address_specific', 'network', 'download_mbps', 'upload_mbps', 'wholesale_ex_gst', 'retail_ex_gst', 'valid_until']
    list_filter = ['review_status', 'address_specific', 'network']
    readonly_fields = ['gst_illustration', 'estimated_margin', 'updated_at', 'approved_by', 'approved_at']
    search_fields = ['name']
    fieldsets = [
        ('Quote and source', {'fields': ['name', 'source_reference', 'network', 'download_mbps',
            'upload_mbps', 'verified_at', 'valid_until', 'address_specific', 'notes']}),
        ('Wholesale costs', {'fields': ['wholesale_ex_gst', 'wholesale_inc_gst', 'setup_ex_gst', 'setup_inc_gst']}),
        ('Retail prices', {'fields': ['retail_ex_gst', 'retail_setup_ex_gst', 'gst_illustration', 'estimated_margin'],
            'description': 'Owner approval and a separate publication release are required. Saving does not charge anyone.'}),
        ('Owner review', {'fields': ['review_status', 'approved_by', 'approved_at', 'updated_at']}),
    ]

    def save_model(self, request, obj, form, change):
        from django.utils import timezone
        obj.approved_by = request.user if obj.review_status == 'approved' else None
        obj.approved_at = timezone.now() if obj.review_status == 'approved' else None
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='catalogue_' + obj.review_status,
                                  reference=f'plan:{obj.pk}')

    @admin.display(description='Draft NZD calculation — GST treatment must be approved')
    def gst_illustration(self, obj):
        values = price_breakdown(obj.retail_ex_gst)
        if values is None:
            return 'Not priced. No public plan or charge.'
        setup = price_breakdown(obj.retail_setup_ex_gst)
        return f"Monthly: ${values['ex_gst']} + ${values['gst']} GST (15%) = ${values['inc_gst']}. Setup incl. GST: {('$' + setup['inc_gst']) if setup else 'not priced'}. Draft only; not a bill."

    @admin.display(description='Monthly difference before other costs, excluding GST')
    def estimated_margin(self, obj):
        if obj.retail_ex_gst is None or obj.wholesale_ex_gst is None:
            return 'Not calculated: enter both draft amounts.'
        return f'NZD {obj.retail_ex_gst - obj.wholesale_ex_gst:.2f} before routers, support, billing, bad debt and other costs. Not net profit.'


@admin.register(AvailabilityEvidence)
class Checks(PrivateRecords):
    list_display = ['address', 'postcode', 'result', 'rehearsal', 'checked_at', 'valid_until']
    list_filter = ['rehearsal', 'result']
    readonly_fields = ['checked_by']

    def has_change_permission(self, request, obj=None):
        # Evidence is append-only. Rechecks create a new record and retain provenance.
        return obj is None and super().has_change_permission(request, obj)


class TransitionForm(forms.Form):
    target = forms.ChoiceField(label='Next status')
    revision = forms.IntegerField(widget=forms.HiddenInput)
    submission_key = forms.UUIDField(widget=forms.HiddenInput)
    reference = forms.CharField(max_length=160, required=False, help_text='Practice reference only for simulated supplier actions.')
    note = forms.CharField(max_length=2000, widget=forms.Textarea, help_text='Internal processing note. No passwords or payment details.')


class CaseEditForm(forms.ModelForm):
    edit_revision = forms.IntegerField(widget=forms.HiddenInput, initial=0)

    class Meta:
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['edit_revision'].initial = self.instance.revision

    def clean(self):
        cleaned = super().clean()
        if not self.instance._state.adding:
            # Django's change-form POST is atomic. Hold this lock until save completes.
            current = type(self.instance).objects.select_for_update().get(pk=self.instance.pk)
            if (cleaned.get('edit_revision') != current.revision or self.instance.revision != current.revision
                    or current.state not in ('draft', 'triage')):
                raise ValidationError('This case changed or is no longer editable. Reload before saving.')
        return cleaned


class CaseAdmin(PrivateRecords):
    form = CaseEditForm
    readonly_fields = ['state', 'revision', 'created_by', 'created_at', 'updated_at', 'processing', 'history']
    list_display = ['__str__', 'state', 'rehearsal', 'updated_at']
    list_filter = ['rehearsal', 'state']

    def save_model(self, request, obj, form, change):
        if change:
            obj.revision += 1
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [path('<uuid:pk>/process/', admin.site.admin_view(self.process), name=f'portal_{self.model._meta.model_name}_process')] + super().get_urls()

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            # Only draft records may be edited; status changes use the audited, versioned workflow.
            fields += ['rehearsal', 'customer_request' if self.model is WholesaleOrder else 'ticket']
            if obj.state not in ('draft', 'triage'):
                fields += [f.name for f in self.model._meta.fields if f.name not in fields]
        return fields

    def process(self, request, pk):
        require_operator(request)
        case = get_object_or_404(self.model, pk=pk)
        graph = ORDER_TRANSITIONS if self.model is WholesaleOrder else FAULT_TRANSITIONS
        states = dict(self.model.STATES)
        choices = [(key, states[key]) for key in graph[case.state]]
        form = TransitionForm(request.POST or None, initial={'revision': case.revision, 'submission_key': uuid.uuid4()})
        form.fields['target'].choices = choices
        if request.method == 'POST' and form.is_valid():
            try:
                transition(request, self.model, pk, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, 'Internal status recorded. Nothing was sent to Vetta.')
                return redirect(f'admin:portal_{self.model._meta.model_name}_change', pk)
        return TemplateResponse(request, 'admin/wholesale/process.html', {
            **admin.site.each_context(request), 'title': 'Process wholesale case', 'case': case,
            'form': form, 'has_next': bool(choices), 'opts': self.model._meta,
        })

    @admin.display(description='Manual workflow')
    def processing(self, obj):
        if not obj or not obj.pk or obj._state.adding:
            return 'Save the draft to start the workflow.'
        return format_html('<a href="{}">Review checklist and update status</a>', reverse(f'admin:portal_{self.model._meta.model_name}_process', args=[obj.pk]))

    @admin.display(description='Processing history')
    def history(self, obj):
        if not obj or obj._state.adding:
            return 'No history yet.'
        return '\n'.join(f'{event.created_at:%Y-%m-%d %H:%M} {event.from_state} → {event.to_state}: {event.note}' for event in obj.events.order_by('-created_at')[:30]) or 'No status updates yet.'


admin.site.register(WholesaleOrder, CaseAdmin)
admin.site.register(WholesaleFault, CaseAdmin)


@admin.register(WholesaleEvent)
class History(PrivateRecords):
    list_display = ['created_at', 'order', 'fault', 'from_state', 'to_state', 'actor']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
