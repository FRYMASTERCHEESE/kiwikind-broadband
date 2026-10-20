from decimal import Decimal
from django.db import migrations


def seed_quote(apps, schema_editor):
    apps.get_model('portal', 'DraftPlan').objects.using(schema_editor.connection.alias).get_or_create(
        name='Direct UFB 500/100 — address-specific quote',
        defaults={
            'download_mbps': 500, 'upload_mbps': 100,
            'wholesale_ex_gst': Decimal('69.92'), 'wholesale_inc_gst': Decimal('80.41'),
            'setup_ex_gst': Decimal('35.00'), 'setup_inc_gst': Decimal('40.25'),
            'source_reference': 'User-transcribed Vetta screenshot quote, supplied 20 October 2026',
            'notes': 'Private draft for one address. Original screenshot and service address not attached. '
                     'Confirm source, network, validity and terms with Vetta. Not approved for general publication. '
                     'No retail price, availability or supplier order is authorised.',
            'address_specific': True, 'review_status': 'draft',
        })


class Migration(migrations.Migration):
    dependencies = [('portal', '0010_owner_mfa_catalogue')]
    operations = [migrations.RunPython(seed_quote, migrations.RunPython.noop)]
