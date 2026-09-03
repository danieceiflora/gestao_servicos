from django.db import migrations, models


def classify_existing_pix_methods(apps, schema_editor):
    PaymentMethod = apps.get_model('services', 'PaymentMethod')
    PaymentMethod.objects.filter(tipo_provedor='PIX', integra_gateway=True).update(pix_type='DYNAMIC')
    PaymentMethod.objects.filter(tipo_provedor='PIX', integra_gateway=False).update(pix_type='STATIC')


def clear_pix_classification(apps, schema_editor):
    PaymentMethod = apps.get_model('services', 'PaymentMethod')
    PaymentMethod.objects.update(pix_type='', pix_key='')


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0116_product_audit_provenance'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentmethod',
            name='pix_type',
            field=models.CharField(
                blank=True,
                choices=[('STATIC', 'Estático'), ('DYNAMIC', 'Dinâmico')],
                default='',
                help_text='PIX estático usa uma chave cadastrada; PIX dinâmico é gerado pelo gateway.',
                max_length=10,
                verbose_name='Tipo de PIX',
            ),
        ),
        migrations.AddField(
            model_name='paymentmethod',
            name='pix_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Obrigatória para métodos PIX estáticos.',
                max_length=255,
                verbose_name='Chave PIX',
            ),
        ),
        migrations.RunPython(classify_existing_pix_methods, clear_pix_classification),
    ]
