import uuid
from django.db import migrations, models


def populate_confirmation_tokens(apps, schema_editor):
    ServiceOrderTask = apps.get_model('services', 'ServiceOrderTask')
    for task in ServiceOrderTask.objects.all():
        task.confirmation_token = uuid.uuid4()
        task.save(update_fields=['confirmation_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0092_financesettings_auto_billing_on_task_completion_and_more'),
    ]

    operations = [
        # Passo 1: adiciona sem unique e com NULL permitido para não quebrar linhas existentes
        migrations.AddField(
            model_name='serviceordertask',
            name='confirmation_token',
            field=models.UUIDField(
                null=True,
                blank=True,
                editable=False,
                verbose_name='Token de Confirmação Pública',
            ),
        ),
        # Passo 2: popula UUIDs únicos em todas as linhas existentes
        migrations.RunPython(populate_confirmation_tokens, migrations.RunPython.noop),
        # Passo 3: aplica NOT NULL + unique + default para novas linhas
        migrations.AlterField(
            model_name='serviceordertask',
            name='confirmation_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='Token de Confirmação Pública',
            ),
        ),
    ]
