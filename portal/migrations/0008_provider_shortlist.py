from django.db import migrations


def seed(apps, schema_editor):
    Provider = apps.get_model('portal', 'Provider')
    entries = [
        ('Devoli', 'https://devoli.com/retail-service-provider',
         'Own-brand broadband platform with provisioning, customer management and end-user billing. Ask about startup minimums and integration access.'),
        ('Wholesale Group', 'https://wholesalegroup.nz/white-label-services/',
         'White-label virtual ISP resources with provisioning and customer invoices under your brand. Ask about residential startup onboarding and external app integration.'),
        ('2talk', 'https://www.2talk.co.nz/partners',
         'White-label broadband and voice partnerships with customer portals and billing/rating options. Ask for the white-label agreement rather than a sales-agent arrangement.'),
        ('Vetta', 'https://vetta.nz/wholesale/',
         'Wholesale fibre/DSL, rural connectivity and provisioning/testing/fault tools. White-label delivery where possible. Confirm residential startup eligibility and API access.'),
    ]
    for name, website, summary in entries:
        Provider.objects.get_or_create(name=name, defaults={'website': website, 'summary': summary})


class Migration(migrations.Migration):
    dependencies = [('portal', '0007_providers')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
