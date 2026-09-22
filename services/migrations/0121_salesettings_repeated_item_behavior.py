from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0120_cashregister_paymentmethod_pos_behavior_sale_origin_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesettings',
            name='repeated_item_behavior',
            field=models.CharField(
                choices=[
                    ('SEPARATE_LINES', 'Criar uma nova linha'),
                    ('SUM_QUANTITY', 'Somar à quantidade da linha existente'),
                ],
                default='SEPARATE_LINES',
                max_length=20,
                verbose_name='Ao adicionar o mesmo produto',
            ),
        ),
    ]
