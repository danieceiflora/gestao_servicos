from decimal import Decimal
from django.utils import timezone
from ..models import Billing, Installment, SystemConfig

def create_billing_for_os(service_order):
    """
    Gera um registro de Billing (e uma parcela padrão) para uma OS finalizada ou aguardando pagamento.
    """
    if hasattr(service_order, 'billing'):
        return service_order.billing

    config = SystemConfig.load()
    due_days = config.billing_default_due_days or 1
    due_date = timezone.now().date() + timezone.timedelta(days=due_days)

    billing = Billing.objects.create(
        client=service_order.client_property.client,
        service_order=service_order,
        total_amount=service_order.total_value,
        discount=service_order.discount,
        status=Billing.Status.PENDENTE
    )

    # Cria a parcela única padrão
    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=due_date,
        amount=service_order.balance_due,
        status=Installment.Status.PENDENTE
    )

    return billing

def create_billing_for_sale(sale, installments_data=None):
    """
    Gera um registro de Billing e parcelas para uma venda.
    installments_data deve ser uma lista de dicionários: [{'due_date': date, 'amount': decimal, 'payment_method_id': id}]
    """
    if hasattr(sale, 'billing'):
        # Se já existe, limpa as parcelas e recria
        sale.billing.installments.all().delete()
        billing = sale.billing
        billing.total_amount = sale.total_amount
        billing.discount = sale.discount
        billing.save()
    else:
        billing = Billing.objects.create(
            client=sale.client,
            sale=sale,
            total_amount=sale.total_amount,
            discount=sale.discount,
            status=Billing.Status.PENDENTE
        )

    if installments_data:
        for i, data in enumerate(installments_data, 1):
            Installment.objects.create(
                billing=billing,
                installment_number=i,
                due_date=data['due_date'],
                amount=data['amount'],
                payment_method_id=data.get('payment_method_id'),
                status=Installment.Status.PENDENTE
            )
    else:
        # Fallback para parcela única
        config = SystemConfig.load()
        due_days = config.billing_default_due_days or 1
        due_date = timezone.now().date() + timezone.timedelta(days=due_days)
        
        Installment.objects.create(
            billing=billing,
            installment_number=1,
            due_date=due_date,
            amount=sale.total_amount - sale.discount,
            status=Installment.Status.PENDENTE
        )

    return billing
