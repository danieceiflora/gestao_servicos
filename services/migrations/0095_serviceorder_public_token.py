import uuid
from django.db import migrations, models


def populate_public_tokens(apps, schema_editor):
    ServiceOrder = apps.get_model('services', 'ServiceOrder')
    for order in ServiceOrder.objects.filter(public_token__isnull=True):
        order.public_token = uuid.uuid4()
        order.save(update_fields=['public_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0094_serviceordertask_payment_preference'),
    ]

    operations = [
        # Passo 1: adiciona como nullable, sem unique
        migrations.AddField(
            model_name='serviceorder',
            name='public_token',
            field=models.UUIDField(
                null=True,
                blank=True,
                editable=False,
                verbose_name='Token da Página Pública',
            ),
        ),
        # Passo 2: popula registros existentes com UUIDs únicos
        migrations.RunPython(populate_public_tokens, reverse_code=migrations.RunPython.noop),
        # Passo 3: torna não-nulo, único, com default para novos registros
        migrations.AlterField(
            model_name='serviceorder',
            name='public_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='Token da Página Pública',
            ),
        ),
    ]
