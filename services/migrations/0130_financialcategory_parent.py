from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0129_backfill_sale_refunds'),
    ]

    operations = [
        migrations.AddField(
            model_name='financialcategory',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                help_text='Opcional. Subcategorias usam o mesmo tipo da categoria principal.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='subcategories',
                to='services.financialcategory',
                verbose_name='Categoria principal',
            ),
        ),
    ]
