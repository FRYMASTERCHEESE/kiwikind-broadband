# Account-specific wholesale rates are stored only in the private database.
# This schema migration intentionally includes no supplier prices or source exports.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('portal', '0012_broadband_order_catalogue')]
    operations = [
        migrations.CreateModel(
            name='VerifiedSupplierOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_id', models.CharField(max_length=40)),
                ('group_id', models.CharField(max_length=40)),
                ('option_id', models.CharField(max_length=40)),
                ('label', models.CharField(max_length=160)),
                ('monthly_ex_gst_cents', models.PositiveIntegerField()),
                ('setup_ex_gst_cents', models.PositiveIntegerField(blank=True, null=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('verified', models.BooleanField(default=False)),
                ('verified_on', models.DateField(blank=True, null=True)),
                ('source_ref', models.CharField(blank=True, max_length=120)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='verifiedsupplieroption',
            constraint=models.UniqueConstraint(fields=('product_id', 'group_id', 'option_id'), name='verified_supplier_option_unique'),
        ),
        migrations.AddIndex(
            model_name='verifiedsupplieroption',
            index=models.Index(fields=['product_id', 'group_id', 'verified'], name='supplier_option_lookup'),
        ),
    ]
