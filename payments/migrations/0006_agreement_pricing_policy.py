"""Protect historical Stripe amounts while enabling versioned new retail offers."""
from django.db import migrations, models
import payments.live_models


class Migration(migrations.Migration):
    dependencies = [('payments', '0005_owner_one_dollar_verification')]

    operations = [
        migrations.AddField(
            model_name='liveagreement',
            name='pricing_policy',
            field=models.CharField(default='legacy_v1', editable=False, max_length=16),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='liveagreement',
            name='pricing_policy',
            field=models.CharField(default=payments.live_models.default_price_policy,
                                   editable=False, max_length=16),
        ),
    ]
