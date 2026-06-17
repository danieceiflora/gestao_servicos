from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pagamentos', '0002_gatewayconfig_income_value'),
    ]

    operations = [
        migrations.AddField(
            model_name='gatewayconfig',
            name='subaccount_api_key',
            field=models.CharField(
                blank=True,
                help_text='Chave da subconta — usada para emitir cobranças no nome do cliente',
                max_length=255,
                verbose_name='API Key da Subconta',
            ),
        ),
    ]
