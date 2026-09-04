from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0117_paymentmethod_pix_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importhistory',
            name='operation_type',
            field=models.CharField(
                choices=[
                    ('CATALOG', 'Gestão de Catálogo'),
                    ('STOCK', 'Atualização de Estoque'),
                    ('BLING', 'Importação Bling'),
                ],
                default='BLING',
                max_length=10,
                verbose_name='Tipo de Operação',
            ),
        ),
    ]
