from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0093_serviceordertask_confirmation_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceordertask',
            name='preferred_payment_method',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_tasks',
                to='services.paymentmethod',
                verbose_name='Método de Pagamento Preferido (cliente)',
            ),
        ),
        migrations.AddField(
            model_name='serviceordertask',
            name='preferred_installments',
            field=models.PositiveIntegerField(
                blank=True,
                default=1,
                null=True,
                verbose_name='Parcelas Preferidas (cliente)',
            ),
        ),
    ]
