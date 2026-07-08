from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0024_pushinpaysubscription_and_more'),
    ]

    operations = [
        migrations.RenameModel(old_name='PushinPaySubscription', new_name='PlatformSubscription'),
        migrations.RenameModel(old_name='PushinPaySubscriptionEvent', new_name='PlatformSubscriptionEvent'),
        migrations.RenameField(model_name='platformsubscription', old_name='frequency', new_name='cycle'),
        migrations.AlterField(
            model_name='platformsubscription',
            name='cycle',
            field=models.CharField(
                blank=True, max_length=20, verbose_name='Periodicidade',
                help_text='WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, SEMIANNUALLY ou YEARLY (vocabulário do Asaas)',
            ),
        ),
        migrations.RemoveField(model_name='platformsubscription', name='retry_policy'),
        migrations.AlterField(
            model_name='platformsubscription',
            name='subscription_id',
            field=models.CharField(blank=True, max_length=100, verbose_name='ID da Assinatura (Asaas)'),
        ),
        migrations.AlterModelOptions(
            name='platformsubscription',
            options={'verbose_name': 'Assinatura da Plataforma', 'verbose_name_plural': 'Assinatura da Plataforma'},
        ),
        migrations.AlterModelOptions(
            name='platformsubscriptionevent',
            options={'ordering': ['-created_at'], 'verbose_name': 'Evento da Assinatura', 'verbose_name_plural': 'Eventos da Assinatura'},
        ),
    ]
