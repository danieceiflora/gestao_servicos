from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0035_notificationconfig_sale_type_filter'),
    ]

    operations = [
        migrations.AddField(
            model_name='manualmessageconfig',
            name='recipient_type',
            field=models.CharField(choices=[('CLIENT', 'Número do cliente'), ('FIXED', 'Número fixo')], default='CLIENT', max_length=20, verbose_name='Tipo de Destinatário'),
        ),
        migrations.AddField(
            model_name='manualmessageconfig',
            name='fixed_phone',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Telefone Fixo'),
        ),
    ]
