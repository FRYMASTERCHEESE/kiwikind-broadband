"""Private catalogue editing: explicit approval, server GST and stale-tab protection."""
from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import DraftPlan
from .wholesale import price_breakdown


class CataloguePlanForm(forms.ModelForm):
    expected_updated_at = forms.CharField(required=False, widget=forms.HiddenInput)
    confirm_current_approval = forms.BooleanField(
        required=False,
        label='I explicitly approve these current prices and verified general-offer terms',
        help_text='Required each time you save as Owner approved. This does not enable publication, payments or supplier orders.',
    )

    class Meta:
        model = DraftPlan
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.updated_at:
            self.initial['expected_updated_at'] = self.instance.updated_at.isoformat()
        for name in ('wholesale_inc_gst', 'setup_inc_gst'):
            if name in self.fields:
                self.fields[name].disabled = True
                self.fields[name].help_text = 'Calculated by the server from the exclusive price at 15% GST when saved. Blank is unknown, not free.'
        if 'notes' in self.fields:
            self.fields['notes'].help_text = (
                'Private evidence: quote/capture date, address or coverage scope, Direct/Layer 2 handover, '
                'churn/new-install conditions, contract term and outstanding supplier questions. '
                'Keep unknown facts explicitly unconfirmed. Never store passwords, ONT identifiers or payment details here.'
            )

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and not self.instance._state.adding:
            # Django wraps admin change POSTs in a transaction. Keep the row locked
            # through save_model so two browser tabs cannot silently overwrite a quote.
            current = DraftPlan.objects.select_for_update().get(pk=self.instance.pk)
            expected = cleaned.get('expected_updated_at')
            if not expected or expected != current.updated_at.isoformat():
                raise ValidationError('This quote changed or the edit version is missing. Reload the page before saving; nothing has been overwritten.')
        for net_name, gross_name in (('wholesale_ex_gst', 'wholesale_inc_gst'), ('setup_ex_gst', 'setup_inc_gst')):
            net = cleaned.get(net_name)
            if net_name in self.errors:
                continue
            try:
                values = price_breakdown(net)
                cleaned[gross_name] = Decimal(values['inc_gst']) if values else None
            except ValueError as exc:
                self.add_error(net_name, str(exc))
        if cleaned.get('review_status') == 'approved' and not cleaned.get('confirm_current_approval'):
            self.add_error('confirm_current_approval', 'Explicit owner confirmation is required for these current values. Otherwise save as Draft or Needs owner review.')
        elif cleaned.get('confirm_current_approval') and cleaned.get('review_status') != 'approved':
            self.add_error('confirm_current_approval', 'Leave this unchecked for a private draft/review record. Approval also requires selecting Owner approved and meeting all verification checks.')
        return cleaned


def catalogue_readiness(plan):
    """Private-only guidance; the public API independently validates every record."""
    if not plan or plan._state.adding:
        return 'New private draft. Save the source evidence first; no plan is published or charged.'
    blockers = []
    if not settings.PLAN_PUBLICATION_ENABLED:
        blockers.append('Plan publication is disabled for the whole service.')
    if plan.address_specific:
        blockers.append('Address-specific quote: cannot be published as a general plan.')
    if plan.review_status != 'approved' or not plan.approved_at or not plan.approved_by_id:
        blockers.append('No current recorded owner approval.')
    if not plan.network.strip():
        blockers.append('Verified network/LFC is missing; do not infer it from the address or speed.')
    if not plan.download_mbps or not plan.upload_mbps:
        blockers.append('Download and upload speeds must both be confirmed.')
    if not plan.source_reference.strip() or not plan.verified_at:
        blockers.append('Supplier source and verification time are not confirmed.')
    if not plan.valid_until:
        blockers.append('Supplier price validity is unknown.')
    elif plan.valid_until < timezone.localdate():
        blockers.append('Supplier price validity has expired.')
    if plan.retail_ex_gst is None or plan.retail_setup_ex_gst is None:
        blockers.append('Retail monthly/setup prices have not been chosen by the owner.')
    if any(getattr(plan, name) is None for name in ('wholesale_ex_gst', 'wholesale_inc_gst', 'setup_ex_gst', 'setup_inc_gst')):
        blockers.append('Wholesale monthly/setup costs are incomplete; a missing amount is not zero.')
    try:
        plan.full_clean()
    except (ValidationError, ValueError, TypeError):
        blockers.append('The stored quote also fails validation; review its amounts, source and dates.')
    if not blockers:
        return 'Recorded approval meets catalogue checks. Address availability is still unverified; live orders and billing remain separate disabled workflows.'
    return '\n'.join(blockers) + '\nSaving this record does not submit a Vetta order or collect a payment.'
