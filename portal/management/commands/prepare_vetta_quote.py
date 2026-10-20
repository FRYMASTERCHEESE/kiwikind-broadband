from decimal import Decimal
from django.core.management.base import BaseCommand
from portal.models import PricePlan

class Command(BaseCommand):
    help = 'Stage the supplied address-specific quote as an unpublished draft; never update existing records.'
    def handle(self,*args,**options):
        plan,created=PricePlan.objects.get_or_create(name='Direct UFB 500/100 — unconfirmed address quote',defaults={
            'source':'User-transcribed screenshot: monthly $69.92 ex / $80.41 incl GST; setup $35 ex / $40.25 incl GST. Original screenshot and supplier validity not yet verified.',
            'network':'Direct UFB — LFC unconfirmed','download_mbps':500,'upload_mbps':100,
            'wholesale_ex_gst':Decimal('69.92'),'wholesale_incl_gst':Decimal('80.41'),
            'setup_ex_gst':Decimal('35.00'),'setup_incl_gst':Decimal('40.25'),
            'address_specific':True,'status':'draft'})
        self.stdout.write('Draft staged.' if created else 'Existing quote left unchanged.')
