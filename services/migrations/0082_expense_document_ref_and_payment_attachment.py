import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0081_installmentpayment_discount_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='expenseinstallment',
            name='document_ref',
            field=models.CharField(blank=True, max_length=100, verbose_name='Nº Documento (NF/Boleto/PIX)'),
        ),
        migrations.CreateModel(
            name='PaymentAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='payment_attachments/%Y/%m/%d/', verbose_name='Arquivo')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='Descrição')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='services.installmentpayment', verbose_name='Baixa')),
            ],
            options={
                'verbose_name': 'Comprovante de Pagamento',
                'verbose_name_plural': 'Comprovantes de Pagamento',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
