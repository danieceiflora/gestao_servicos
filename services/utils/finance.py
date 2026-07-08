from datetime import date as date_type
from decimal import Decimal
from django.utils import timezone
from ..models import Billing, Installment, SystemConfig


def _get_due_date(charge_config=None):
    """Data de vencimento da 1ª parcela: usa charge_config.due_days se informado,
    caso contrário cai para SystemConfig.billing_default_due_days."""
    if charge_config is not None:
        due_days = charge_config.due_days
    else:
        config = SystemConfig.load()
        due_days = config.billing_default_due_days or 1
    return timezone.now().date() + timezone.timedelta(days=due_days)


def resolve_charge_config_for_payment_method(payment_method):
    """Resolve a BillingChargeConfig ativa cujo default_payment_method seja exatamente
    o método informado. Retorna None se não houver método ou nenhuma regra ativa o mira."""
    from pagamentos.models import BillingChargeConfig

    if not payment_method:
        return None
    return (
        BillingChargeConfig.objects
        .filter(default_payment_method=payment_method, is_active=True)
        .order_by('-updated_at')
        .first()
    )


def resolve_charge_config_from_post(request):
    """Resolve a BillingChargeConfig ativa a partir de request.POST['charge_config_id']."""
    from pagamentos.models import BillingChargeConfig
    config_id = request.POST.get('charge_config_id', '').strip()
    if not config_id:
        return None
    try:
        return BillingChargeConfig.objects.get(pk=int(config_id), is_active=True)
    except (BillingChargeConfig.DoesNotExist, ValueError):
        return None


def parse_installments_from_post(request):
    """Lê amount[]/due_date[]/payment_method_id[] do POST e retorna lista de dicts
    [{'amount': Decimal, 'due_date': date, 'payment_method_id': int|None}]."""
    amounts = request.POST.getlist('amount[]')
    due_dates = request.POST.getlist('due_date[]')
    methods = request.POST.getlist('payment_method_id[]')

    installments_data = []
    for amt, dt, mid in zip(amounts, due_dates, methods):
        amt = amt.strip().replace(',', '.')
        dt = dt.strip()
        if not amt or not dt:
            continue
        try:
            amount = Decimal(amt)
            due_date = date_type.fromisoformat(dt)
        except (Exception,):
            continue
        pm_id = None
        if mid and mid.strip():
            try:
                pm_id = int(mid.strip())
            except ValueError:
                pass
        installments_data.append({'amount': amount, 'due_date': due_date, 'payment_method_id': pm_id})

    return installments_data


def create_billing_for_task(task, charge_config=None):
    """
    Gera um Billing vinculado a uma etapa concluída (EXECUCAO, GARANTIA ou RETORNO).
    Aplica task.discount como desconto da cobrança.
    Impede duplicata por etapa. Retorna None se o valor bruto for zero.

    Se charge_config não for informado, resolve pela forma de pagamento preferida da etapa
    (task.preferred_payment_method).
    """
    if task.billings.exists():
        return task.billings.first()

    value = task.billing_value
    if not value:
        return None

    discount = task.discount or Decimal('0')
    net_value = max(value - discount, Decimal('0'))

    if charge_config is None:
        charge_config = resolve_charge_config_for_payment_method(task.preferred_payment_method)

    billing = Billing.objects.create(
        client=task.service_order.client_property.client,
        service_order=task.service_order,
        task=task,
        charge_config=charge_config,
        total_amount=value,
        discount=discount,
        status=Billing.Status.PENDENTE
    )

    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=_get_due_date(charge_config),
        amount=net_value,
        payment_method=task.preferred_payment_method,
        status=Installment.Status.PENDENTE
    )

    return billing


def create_billing_for_os(service_order):
    """
    Gera um Billing no nível da OS (sem etapa vinculada).
    Mantido para compatibilidade com OSs antigas e fluxos legados.
    Impede duplicata por OS (considera apenas billings sem task).
    """
    if service_order.billings.filter(task__isnull=True).exists():
        return service_order.billings.filter(task__isnull=True).first()

    billing = Billing.objects.create(
        client=service_order.client_property.client,
        service_order=service_order,
        task=None,
        total_amount=service_order.total_value,
        discount=service_order.discount,
        status=Billing.Status.PENDENTE
    )

    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=_get_due_date(),
        amount=service_order.balance_due,
        status=Installment.Status.PENDENTE
    )

    return billing


def create_billing_for_sale(sale, installments_data=None, charge_config=None):
    """
    Gera um Billing e parcelas para uma venda.
    installments_data: lista de dicts [{'due_date': date, 'amount': decimal, 'payment_method_id': id}]
    """
    if hasattr(sale, 'billing'):
        sale.billing.installments.all().delete()
        billing = sale.billing
        billing.total_amount = sale.total_amount
        billing.discount = sale.discount
        billing.charge_config = charge_config
        billing.save()
    else:
        billing = Billing.objects.create(
            client=sale.client,
            sale=sale,
            charge_config=charge_config,
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
        Installment.objects.create(
            billing=billing,
            installment_number=1,
            due_date=_get_due_date(charge_config),
            amount=sale.total_amount - sale.discount,
            status=Installment.Status.PENDENTE
        )

    return billing
