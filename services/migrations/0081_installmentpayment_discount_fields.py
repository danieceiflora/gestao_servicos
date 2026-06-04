from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0080_installment_payment_and_bankaccount'),
    ]

    operations = [
        migrations.AddField(
            model_name='installmentpayment',
            name='is_discount',
            field=models.BooleanField(default=False, verbose_name='É Desconto/Isenção'),
        ),
        migrations.AddField(
            model_name='installmentpayment',
            name='discount_reason',
            field=models.CharField(blank=True, max_length=255, verbose_name='Motivo do Desconto'),
        ),
    ]
