# Isolated one-time verification. No broadband agreement, plan or supplier order is created.
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0004_liveagreement_gst_rate_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OneDollarVerification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('checkout_id', models.CharField(blank=True, editable=False, max_length=255, null=True, unique=True)),
                ('payment_intent_id', models.CharField(blank=True, editable=False, max_length=255, null=True, unique=True)),
                ('state', models.CharField(default='not_started', editable=False, max_length=30)),
                ('refunded_cents', models.PositiveIntegerField(default=0, editable=False)),
                ('dispute_status', models.CharField(blank=True, editable=False, max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,
                    related_name='one_dollar_verification', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Owner one-dollar payment verification'},
        ),
        migrations.AddConstraint(
            model_name='onedollarverification',
            constraint=models.CheckConstraint(condition=models.Q(refunded_cents__lte=100),
                name='owner_dollar_refund_bound'),
        ),
    ]
