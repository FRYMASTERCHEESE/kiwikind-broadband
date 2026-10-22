from django import forms
from django.core.exceptions import ValidationError
from .live_models import LiveAgreement


class LiveAgreementForm(forms.ModelForm):
    confirm_live_offer = forms.BooleanField(required=False, label='I approve these calculated GST-inclusive totals and confirmed service terms for this customer')

    class Meta:
        model = LiveAgreement
        fields = ['user', 'label', 'service_reference', 'source_monthly_cents',
            'source_setup_cents', 'service_terms', 'bill_from', 'supplier_confirmed', 'reviewed']

    def clean(self):
        values = super().clean()
        if not self.instance._state.adding:
            current = LiveAgreement.objects.select_for_update().get(pk=self.instance.pk)
            if current.checkout_started_at:
                raise ValidationError('Checkout started; the agreed terms and amounts are locked.')
        if values.get('reviewed') and not values.get('confirm_live_offer'):
            self.add_error('confirm_live_offer', 'Confirm approval of this exact customer offer.')
        return values
