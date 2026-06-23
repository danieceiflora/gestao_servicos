from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0094_serviceordertask_payment_preference'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceordertask',
            name='discount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Desconto (R$)'),
        ),
    ]
