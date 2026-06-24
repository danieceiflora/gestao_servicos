import uuid
from django.db import migrations, models


def populate_public_token(apps, schema_editor):
    Billing = apps.get_model('services', 'Billing')
    for billing in Billing.objects.filter(public_token__isnull=True):
        billing.public_token = uuid.uuid4()
        billing.save(update_fields=['public_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0097_add_tarifa_minima_to_paymentmethod'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='public_token',
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.RunPython(populate_public_token, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='billing',
            name='public_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
