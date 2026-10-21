import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies=[('payments','0001_initial'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[migrations.CreateModel(name='OwnerSandboxRun',fields=[
        ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
        ('scenario',models.CharField(max_length=20,choices=[('renewal','Renewal'),('decline-3ds','Decline and 3DS')])),
        ('clock_id',models.CharField(max_length=255,blank=True)),
        ('customer_id',models.CharField(max_length=255,blank=True)),
        ('advance_to',models.BigIntegerField(null=True,blank=True)),
        ('evidence',models.JSONField(default=dict,blank=True)),
        ('checked_at',models.DateTimeField(null=True,blank=True)),
        ('created_at',models.DateTimeField(auto_now_add=True)),
        ('owner',models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT)),
        ('agreement',models.OneToOneField(to='payments.testagreement',on_delete=django.db.models.deletion.PROTECT)),
    ])]
