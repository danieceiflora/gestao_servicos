from decimal import Decimal

from django.db import migrations


def backfill_returns(apps, schema_editor):
    SaleReturn = apps.get_model('services', 'SaleReturn')
    SaleRefund = apps.get_model('services', 'SaleRefund')
    for ret in SaleReturn.objects.filter(status='APROVADA').iterator():
        refund, created = SaleRefund.objects.get_or_create(
            sale_return_id=ret.pk,
            defaults={
                'sale_id': ret.sale_id,
                'kind': 'RETURN',
                'due_amount': ret.total_refund or Decimal('0.00'),
                'balance_reduction': Decimal('0.00'),
                'review_required': True,
                'created_by_id': ret.user_id,
            },
        )
        if created:
            SaleRefund.objects.filter(pk=refund.pk).update(created_at=ret.created_at)


class Migration(migrations.Migration):
    dependencies = [('services', '0128_salerefund_salerefundattachment_salerefundpayment')]
    operations = [migrations.RunPython(backfill_returns, migrations.RunPython.noop)]
