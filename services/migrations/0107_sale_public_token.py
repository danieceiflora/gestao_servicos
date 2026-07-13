import uuid
from django.db import migrations, models


def populate_public_tokens(apps, schema_editor):
    Sale = apps.get_model('services', 'Sale')
    for sale in Sale.objects.filter(public_token__isnull=True):
        sale.public_token = uuid.uuid4()
        sale.save(update_fields=['public_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0106_paymentmethod_integra_gateway'),
    ]

    operations = [
        # Passo 1: adiciona como nullable, sem unique
        migrations.AddField(
            model_name='sale',
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
            model_name='sale',
            name='public_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='Token da Página Pública',
            ),
        ),
    ]
