from django.db import migrations, models
import django.db.models.deletion


def backfill_audit(apps, schema_editor):
    Product = apps.get_model('services', 'Product')
    ImportHistory = apps.get_model('services', 'ImportHistory')
    ImportItem = apps.get_model('services', 'ImportItem')

    ImportHistory.objects.filter(completed_at__isnull=True).update(completed_at=models.F('created_at'))

    # Only explicit import logs are evidence. Everything else remains LEGACY.
    histories = ImportHistory.objects.filter(operation_type='BLING', status='CONCLUIDA').order_by('created_at', 'pk')
    for history in histories.iterator():
        items = ImportItem.objects.filter(import_history=history, product_id__isnull=False, is_error=False)
        for item in items.iterator():
            action = (item.action or '').casefold()
            if action in {'criado', 'atualizado', 'estoque'}:
                updates = {'last_import_id': history.pk}
                if action == 'criado':
                    product = Product.objects.filter(pk=item.product_id).first()
                    if product and product.registration_source == 'LEGACY' and product.source_import_id is None:
                        updates.update(
                            registration_source='BLING',
                            source_import_id=history.pk,
                            created_by_id=history.user_id,
                        )
                Product.objects.filter(pk=item.product_id).update(**updates)


class Migration(migrations.Migration):
    dependencies = [('services', '0115_bling_product_import')]

    operations = [
        migrations.AddField(
            model_name='importhistory', name='completed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Conclusão'),
        ),
        migrations.AddField(
            model_name='importitem', name='changes',
            field=models.JSONField(blank=True, default=list, verbose_name='Alterações estruturadas'),
        ),
        migrations.AddField(
            model_name='product', name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products_created', to='services.user', verbose_name='Cadastrado por'),
        ),
        migrations.AddField(
            model_name='product', name='last_import',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products_last_affected', to='services.importhistory', verbose_name='Última importação'),
        ),
        migrations.AddField(
            model_name='product', name='registration_source',
            field=models.CharField(choices=[('MANUAL', 'Manual'), ('BLING', 'Bling'), ('CATALOG', 'Catálogo CSV/XLSX'), ('XML', 'XML de nota'), ('LEGACY', 'Legado')], default='LEGACY', max_length=10, verbose_name='Origem do cadastro'),
        ),
        migrations.AddField(
            model_name='product', name='source_import',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products_created', to='services.importhistory', verbose_name='Importação de origem'),
        ),
        migrations.AddField(
            model_name='product', name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True, verbose_name='Última alteração'),
        ),
        migrations.RunPython(backfill_audit, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product', name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Última alteração'),
        ),
    ]
