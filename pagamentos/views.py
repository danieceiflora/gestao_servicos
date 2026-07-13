import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from integracoes.models import SystemConfig
from services.models import Installment, PaymentMethod, User
from .gateways.asaas import AsaasGateway
from .gateways.base import ChargeData, SubaccountData
from .models import GatewayCharge, GatewayConfig, BillingChargeConfig

logger = logging.getLogger(__name__)


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


def _get_gateway():
    return AsaasGateway()


def _charge_description(base: str) -> str:
    company = SystemConfig.load().company_name
    return f'{base} — {company}' if company else base


# --- CONFIGURAÇÃO ---

@login_required
@user_passes_test(is_manager)
def gateway_config_view(request):
    config = GatewayConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        # Atualiza campos do formulário
        text_fields = [
            'company_name', 'company_type', 'cpf_cnpj', 'email', 'phone',
            'address_street', 'address_number', 'address_complement',
            'address_neighborhood', 'address_city', 'address_state', 'address_zip',
            'environment',
        ]
        for f in text_fields:
            val = request.POST.get(f, '').strip()
            if val:
                setattr(config, f, val)

        raw_income = request.POST.get('income_value', '').strip().replace(',', '.')
        if raw_income:
            try:
                config.income_value = Decimal(raw_income)
            except Exception:
                pass

        config.pix_enabled = 'pix_enabled' in request.POST
        config.boleto_enabled = 'boleto_enabled' in request.POST

        # webhook_token pode ser vazio intencionalmente (desabilitar validação)
        config.webhook_token = request.POST.get('webhook_token', '').strip()

        config.save()

        if action == 'create_subaccount':
            _handle_create_subaccount(request, config)
        elif action == 'refresh_status':
            _handle_refresh_status(request, config)
        else:
            messages.success(request, 'Configurações salvas.')

        return redirect('pagamentos:gateway_config')

    context = {
        'config': config,
        'title': 'Gateway de Pagamentos — Asaas',
        'active_menu': 'integracoes',
    }
    return render(request, 'pagamentos/gateway_config.html', context)


def _handle_create_subaccount(request, config: GatewayConfig):
    required = ['company_name', 'cpf_cnpj', 'email', 'phone',
                'address_street', 'address_number', 'address_city',
                'address_state', 'address_zip', 'address_neighborhood',
                'income_value']
    missing = [f for f in required if not getattr(config, f, None)]
    if missing:
        messages.error(request, f'Preencha os campos obrigatórios: {", ".join(missing)}')
        return

    try:
        gw = _get_gateway()
        data = SubaccountData(
            name=config.company_name,
            cpf_cnpj=config.cpf_cnpj,
            email=config.email,
            phone=config.phone,
            company_type=config.company_type or 'MEI',
            address_street=config.address_street,
            address_number=config.address_number,
            address_complement=config.address_complement,
            address_city=config.address_city,
            address_state=config.address_state,
            address_zip=config.address_zip,
            address_neighborhood=config.address_neighborhood,
            income_value=float(config.income_value or 0),
        )
        result = gw.create_subaccount(data)
        config.wallet_id = result.wallet_id
        config.status = result.status
        config.status_detail = result.detail
        if result.api_key:
            config.subaccount_api_key = result.api_key
        config.save()
        messages.success(request, f'Subconta criada! Status: {config.get_status_display()}')
    except Exception as e:
        logger.exception('Erro ao criar subconta Asaas')
        messages.error(request, f'Erro ao criar subconta: {e}')


def _handle_refresh_status(request, config: GatewayConfig):
    if not config.wallet_id:
        messages.warning(request, 'Nenhuma subconta configurada ainda.')
        return
    try:
        gw = _get_gateway()
        result = gw.get_subaccount_status(config.wallet_id, subaccount_api_key=config.subaccount_api_key)
        config.status = result.status
        config.status_detail = result.detail
        config.save()
        messages.success(request, f'Status atualizado: {config.get_status_display()}')
    except Exception as e:
        logger.exception('Erro ao consultar status Asaas')
        messages.error(request, f'Erro ao consultar status: {e}')


# --- COBRANÇAS ---

@login_required
@user_passes_test(is_manager)
@require_POST
def installment_create_charge(request, installment_pk):
    installment = get_object_or_404(Installment, pk=installment_pk)
    method = request.POST.get('method', 'PIX').upper()

    if method not in ['PIX', 'BOLETO']:
        messages.error(request, 'Método inválido.')
        return redirect('billing_detail', pk=installment.billing_id)

    existing = installment.gateway_charges.filter(
        status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.RECEIVED,
                    GatewayCharge.Status.CONFIRMED]
    ).first()
    if existing:
        messages.warning(request, f'Já existe uma cobrança {existing.get_method_display()} ativa para esta parcela.')
        return redirect('billing_detail', pk=installment.billing_id)

    config = GatewayConfig.load()
    if not config.can_generate_charges:
        messages.error(request, f'Gateway não habilitado (status: {config.get_status_display()}, wallet: {"configurada" if config.wallet_id else "não configurada"}). Acesse Configurações → Gateway de Pagamentos.')
        return redirect('billing_detail', pk=installment.billing_id)

    if method == 'PIX' and not config.pix_enabled:
        messages.error(request, 'PIX não está habilitado nas configurações do gateway.')
        return redirect('billing_detail', pk=installment.billing_id)
    if method == 'BOLETO' and not config.boleto_enabled:
        messages.error(request, 'Boleto não está habilitado nas configurações do gateway.')
        return redirect('billing_detail', pk=installment.billing_id)

    client = installment.billing.client
    client_doc = client.document or ''
    client_email = client.emails.values_list('email', flat=True).first() or ''

    if not client_doc.strip():
        messages.error(
            request,
            f'O cliente <strong>{client.name}</strong> não possui CPF/CNPJ cadastrado. '
            f'Adicione o documento antes de gerar a cobrança.'
        )
        return redirect('billing_detail', pk=installment.billing_id)

    try:
        with transaction.atomic():
            # Trava a parcela e refaz a checagem de cobrança ativa dentro da transação —
            # evita que duas requisições concorrentes (ex: staff pelo admin e cliente pela
            # página pública, quase ao mesmo tempo) criem 2 cobranças duplicadas no gateway.
            locked_installment = Installment.objects.select_for_update().get(pk=installment.pk)
            existing = locked_installment.gateway_charges.filter(
                status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.RECEIVED,
                            GatewayCharge.Status.CONFIRMED]
            ).first()
            if existing:
                messages.warning(request, f'Já existe uma cobrança {existing.get_method_display()} ativa para esta parcela.')
                return redirect('billing_detail', pk=installment.billing_id)

            gw = _get_gateway()
            billing_config = installment.billing.charge_config
            charge_kwargs = {}
            if billing_config:
                is_cash = installment.billing.installments.count() == 1
                apply_discount = billing_config.discount_applies_to_installments or is_cash
                charge_kwargs = _charge_config_to_kwargs(billing_config, apply_discount)
            data = ChargeData(
                customer_name=client.name,
                customer_document=client_doc,
                customer_email=client_email,
                description=_charge_description(f'Parcela {installment.installment_number} — Cobrança #{installment.billing.number}'),
                amount=installment.amount,
                due_date=installment.due_date,
                method=method,
                external_reference=str(installment.pk),
                **charge_kwargs,
            )
            result = gw.create_charge(data, wallet_id=config.wallet_id)

            GatewayCharge.objects.create(
                installment=installment,
                config=config,
                external_id=result.external_id,
                method=method,
                status=result.status,
                amount=result.amount,
                due_date=result.due_date,
                pix_qrcode=result.pix_qrcode,
                pix_copy_paste=result.pix_copy_paste,
                pix_expiration_date=result.pix_expiration_date,
                boleto_url=result.boleto_url,
                boleto_barcode=result.boleto_barcode,
                invoice_url=result.invoice_url,
                invoice_number=result.invoice_number,
            )
        messages.success(request, f'{method} gerado com sucesso!')
    except Exception as e:
        logger.exception('Erro ao criar cobrança no gateway')
        messages.error(request, f'Erro ao gerar cobrança: {e}')

    return redirect('billing_detail', pk=installment.billing_id)


@login_required
@user_passes_test(is_manager)
@require_POST
def installment_update(request, installment_pk):
    """Edita vencimento/valor de uma parcela já gerada. Se houver uma cobrança
    PENDING/OVERDUE ativa no gateway, atualiza a mesma cobrança (mesmo boleto/PIX)
    em vez de cancelar e reemitir."""
    from datetime import date as date_type
    from core.tz_utils import local_today

    installment = get_object_or_404(Installment, pk=installment_pk)

    if installment.status in [Installment.Status.PAGO, Installment.Status.CANCELADO]:
        messages.error(request, 'Não é possível editar uma parcela paga ou cancelada.')
        return redirect('billing_detail', pk=installment.billing_id)

    due_date_str = request.POST.get('due_date', '').strip()
    amount_str = request.POST.get('amount', '0').replace(',', '.').strip()
    try:
        new_due_date = date_type.fromisoformat(due_date_str)
        new_amount = Decimal(amount_str)
    except (ValueError, InvalidOperation):
        messages.error(request, 'Data ou valor inválido.')
        return redirect('billing_detail', pk=installment.billing_id)

    if new_amount <= 0:
        messages.error(request, 'O valor deve ser maior que zero.')
        return redirect('billing_detail', pk=installment.billing_id)

    already_paid = installment.get_total_paid()
    if new_amount < already_paid:
        messages.error(request, f'O valor não pode ser menor que o já recebido (R$ {already_paid}).')
        return redirect('billing_detail', pk=installment.billing_id)

    active_charge = installment.gateway_charges.filter(
        status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.OVERDUE]
    ).order_by('-created_at').first()

    try:
        with transaction.atomic():
            locked = Installment.objects.select_for_update().get(pk=installment.pk)

            if active_charge:
                gw = _get_gateway()
                client = locked.billing.client
                billing_config = locked.billing.charge_config
                charge_kwargs = {}
                if billing_config:
                    is_cash = locked.billing.installments.count() == 1
                    apply_discount = billing_config.discount_applies_to_installments or is_cash
                    charge_kwargs = _charge_config_to_kwargs(billing_config, apply_discount)
                data = ChargeData(
                    customer_name=client.name,
                    customer_document=client.document or '',
                    customer_email=client.emails.values_list('email', flat=True).first() or '',
                    description=_charge_description(f'Parcela {locked.installment_number} — Cobrança #{locked.billing.number}'),
                    amount=new_amount,
                    due_date=new_due_date,
                    method=active_charge.method,
                    external_reference=str(locked.pk),
                    **charge_kwargs,
                )
                result = gw.update_charge(active_charge.external_id, data)

                active_charge.status = result.status
                active_charge.amount = result.amount
                active_charge.due_date = result.due_date
                active_charge.pix_qrcode = result.pix_qrcode
                active_charge.pix_copy_paste = result.pix_copy_paste
                active_charge.pix_expiration_date = result.pix_expiration_date
                active_charge.boleto_url = result.boleto_url
                active_charge.boleto_barcode = result.boleto_barcode
                active_charge.invoice_url = result.invoice_url
                active_charge.invoice_number = result.invoice_number
                active_charge.save()

            locked.due_date = new_due_date
            locked.amount = new_amount
            if locked.status == Installment.Status.ATRASADO and new_due_date >= local_today():
                locked.status = Installment.Status.PENDENTE
            locked.save()

        messages.success(request, 'Parcela atualizada com sucesso.')
    except Exception as e:
        logger.exception('Erro ao atualizar parcela/cobrança no gateway')
        messages.error(request, f'Erro ao atualizar: {e}')

    return redirect('billing_detail', pk=installment.billing_id)


@login_required
@user_passes_test(is_manager)
@require_POST
def installment_cancel_charge(request, charge_pk):
    charge = get_object_or_404(GatewayCharge, pk=charge_pk)
    billing_pk = charge.installment.billing_id

    try:
        gw = _get_gateway()
        gw.cancel_charge(charge.external_id)
        charge.status = GatewayCharge.Status.CANCELLED
        charge.save()
        messages.success(request, 'Cobrança cancelada no gateway.')
    except Exception as e:
        logger.exception('Erro ao cancelar cobrança no gateway')
        messages.error(request, f'Erro ao cancelar cobrança: {e}')

    return redirect('billing_detail', pk=billing_pk)


@login_required
@user_passes_test(is_manager)
def charge_detail(request, charge_pk):
    charge = get_object_or_404(
        GatewayCharge.objects.select_related('installment__billing', 'config'),
        pk=charge_pk
    )
    # Atualiza status do Asaas antes de exibir
    if charge.status not in [GatewayCharge.Status.RECEIVED, GatewayCharge.Status.CONFIRMED,
                              GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED]:
        try:
            gw = _get_gateway()
            result = gw.get_charge(charge.external_id)
            if result.status != charge.status:
                charge.status = result.status
                charge.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass

    context = {
        'charge': charge,
        'title': f'Cobrança {charge.get_method_display()} — {charge.external_id}',
    }
    return render(request, 'pagamentos/charge_detail.html', context)


# --- WEBHOOK ---

@csrf_exempt
def asaas_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    config = GatewayConfig.load()
    
    if config.webhook_token:
        token_recebido = request.headers.get('asaas-access-token', '')
        if token_recebido != config.webhook_token:
            logger.warning(f'Webhook Asaas: token inválido recebido: {token_recebido!r}')
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
        gw = AsaasGateway()
        normalized = gw.parse_webhook(payload)

        external_id = normalized.get('external_id')
        if not external_id:
            return JsonResponse({'ok': True})

        charge = GatewayCharge.objects.filter(external_id=external_id).first()
        if not charge:
            # Não é uma cobrança de cliente — pode ser uma fatura manual ou a
            # assinatura recorrente da própria plataforma (mesmo webhook,
            # centralizado, sem rota nova no Asaas — só existe uma URL
            # cadastrada no painel).
            handled = _handle_platform_invoice_webhook(external_id, normalized)
            if not handled:
                handled = _handle_platform_subscription_webhook(external_id, normalized, payload)
            if not handled:
                logger.warning(f'Webhook Asaas: cobrança não encontrada para ID {external_id}')
            return JsonResponse({'ok': True})

        if not normalized['status']:
            # Evento que o sistema não mapeia para uma mudança de status (ex: PAYMENT_CREATED,
            # PAYMENT_UPDATED, PAYMENT_CHECKOUT_VIEWED) — não sobrescreve o status da cobrança.
            logger.info(f'Webhook Asaas ignorado (evento não mapeado): {external_id} → {normalized["event"]}')
            return JsonResponse({'ok': True})

        charge.status = normalized['status']
        if normalized.get('payment_date'):
            charge.paid_at = timezone.now()
        if normalized.get('net_value'):
            charge.net_value = Decimal(str(normalized['net_value']))
        charge.save()

        if normalized['status'] in ['RECEIVED', 'CONFIRMED']:
            _auto_baixa_installment(charge)

        logger.info(f'Webhook Asaas processado: {external_id} → {normalized["status"]}')
    except Exception as e:
        logger.exception(f'Erro ao processar webhook Asaas: {e}')

    return JsonResponse({'ok': True})


def _handle_platform_invoice_webhook(external_id: str, normalized: dict) -> bool:
    """Atualiza a fatura manual da plataforma (integracoes.PlatformInvoice)
    correspondente a este pagamento Asaas, se houver. Retorna True se uma
    fatura foi encontrada e tratada."""
    from integracoes.models import PlatformInvoice

    invoice = PlatformInvoice.objects.filter(asaas_charge_id=external_id).first()
    if not invoice:
        return False

    status_map = {
        'RECEIVED': PlatformInvoice.Status.PAGA,
        'CONFIRMED': PlatformInvoice.Status.PAGA,
        'OVERDUE': PlatformInvoice.Status.ATRASADA,
        'CANCELLED': PlatformInvoice.Status.CANCELADA,
        'REFUNDED': PlatformInvoice.Status.CANCELADA,
    }
    mapped = status_map.get(normalized.get('status', ''))
    if not mapped:
        return True

    invoice.status = mapped
    if mapped == PlatformInvoice.Status.PAGA and not invoice.paid_at:
        invoice.paid_at = timezone.now()
    invoice.save()
    logger.info(f'Webhook Asaas processado (fatura da plataforma): {external_id} → {normalized["status"]}')
    return True


def _handle_platform_subscription_webhook(external_id: str, normalized: dict, payload: dict) -> bool:
    """Atualiza a assinatura recorrente da plataforma
    (integracoes.PlatformSubscription), se este evento pertencer a ela.

    Roteado por subscription_id, não por external_id: diferente de uma
    fatura avulsa, os charge ids dos ciclos futuros da assinatura não são
    conhecidos com antecedência (o Asaas só cria a cobrança de cada ciclo
    perto do vencimento)."""
    from integracoes.models import PlatformSubscription, PlatformSubscriptionEvent

    subscription_id = normalized.get('subscription_id') or ''
    if not subscription_id:
        return False

    subscription = PlatformSubscription.objects.filter(subscription_id=subscription_id).first()
    if not subscription:
        return False

    status_map = {
        'RECEIVED': PlatformSubscription.Status.ATIVA,
        'CONFIRMED': PlatformSubscription.Status.ATIVA,
        'OVERDUE': PlatformSubscription.Status.ATRASADA,
        'CANCELLED': PlatformSubscription.Status.CANCELADA,
        'REFUNDED': PlatformSubscription.Status.CANCELADA,
    }
    mapped = status_map.get(normalized.get('status', ''))

    # O evento é sempre persistido, mesmo quando o status não é reconhecido —
    # histórico completo é obrigatório (ver plano de implementação original).
    PlatformSubscriptionEvent.objects.create(
        subscription=subscription,
        charge_id=external_id,
        raw_event=normalized.get('status', ''),
        mapped_status=mapped or '',
        payload=payload,
        notes='' if mapped else 'Evento não reconhecido — revisar manualmente.',
    )

    due_date_str = normalized.get('due_date')
    if due_date_str:
        try:
            subscription.next_due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass

    if mapped:
        subscription.status = mapped
        subscription.last_event_at = timezone.now()
        subscription.status_detail = ''
    else:
        subscription.status_detail = f"Evento de webhook não reconhecido: {normalized.get('status')!r}. Revisar manualmente."

    subscription.save()
    logger.info(f'Webhook Asaas processado (assinatura da plataforma): {external_id} → {normalized.get("status")}')
    return True


def _auto_baixa_installment(charge: GatewayCharge):
    from services.models import Installment as Inst, Billing, SalePayment, PaymentMethod
    from decimal import Decimal as D

    installment = charge.installment
    installment.status = Inst.Status.PAGO
    installment.paid_at = timezone.now()
    installment.save(update_fields=['status', 'paid_at'])

    # Cria SalePayment para que get_total_paid() / saldo devedor reflitam o recebimento
    method_label = 'PIX' if charge.method == 'PIX' else 'Boleto'
    payment_method = (
        PaymentMethod.objects.filter(descricao__icontains=method_label, ativo=True).first()
        or PaymentMethod.objects.filter(ativo=True).first()
    )
    if payment_method:
        valor_liquido = charge.net_value if charge.net_value else charge.amount
        valor_tarifa = max(charge.amount - valor_liquido, D('0.00'))
        SalePayment.objects.create(
            installment=installment,
            metodo_pagamento=payment_method,
            valor_bruto=charge.amount,
            valor_tarifa=valor_tarifa,
            valor_liquido=valor_liquido,
            data_pagamento=timezone.now(),
            data_previsao=timezone.now().date(),
            is_gateway_auto=True,
        )
    else:
        logger.warning('_auto_baixa_installment: nenhum PaymentMethod ativo encontrado; '
                       'SalePayment não criado para charge %s', charge.external_id)

    billing = installment.billing
    if not billing.installments.exclude(status=Inst.Status.PAGO).exists():
        billing.status = Billing.Status.PAGO
        billing.save(update_fields=['status'])


# --- REGRAS DE COBRANÇA ---

def _charge_config_to_kwargs(config: BillingChargeConfig, apply_discount: bool) -> dict:
    """Converte uma BillingChargeConfig nos kwargs extras de ChargeData.

    apply_discount controla se o desconto por antecipação é enviado — regras com
    discount_applies_to_installments=False só concedem desconto quando a cobrança
    for à vista (billing com 1 única parcela).
    """
    return {
        'discount_type': config.discount_type if (apply_discount and config.discount_type != 'NONE') else '',
        'discount_value': config.discount_value if apply_discount else Decimal('0'),
        'discount_due_days': config.discount_due_days,
        'interest_monthly': config.interest_monthly,
        'fine_type': config.fine_type if config.fine_type != 'NONE' else '',
        'fine_value': config.fine_value,
    }


def auto_create_charges_for_billing(billing):
    """Dispara cobranças no gateway para todas as parcelas pendentes de um billing.

    Chamado após a criação do billing se charge_config.auto_send_to_gateway=True.
    Silencia erros individualmente para não bloquear o fluxo do billing.
    """
    charge_config = billing.charge_config
    if not charge_config or not charge_config.auto_send_to_gateway:
        return

    gw_config = GatewayConfig.load()
    if not gw_config.can_generate_charges:
        logger.warning('auto_create_charges_for_billing: gateway não habilitado para billing %s', billing.number)
        return

    payment_method = charge_config.default_payment_method
    if not payment_method or payment_method.tipo_provedor not in ('PIX', 'BOLETO'):
        logger.warning('auto_create_charges_for_billing: regra sem método Pix/Boleto definido, pulando billing %s', billing.number)
        return
    if not payment_method.integra_gateway:
        logger.warning(
            'auto_create_charges_for_billing: método "%s" não integra com o gateway '
            '(integra_gateway=False), pulando billing %s', payment_method.descricao, billing.number
        )
        return
    method = payment_method.tipo_provedor
    if method == 'PIX' and not gw_config.pix_enabled:
        logger.warning('auto_create_charges_for_billing: PIX não habilitado, pulando billing %s', billing.number)
        return
    if method == 'BOLETO' and not gw_config.boleto_enabled:
        logger.warning('auto_create_charges_for_billing: Boleto não habilitado, pulando billing %s', billing.number)
        return

    client = billing.client
    client_doc = (client.document or '').strip()
    if not client_doc:
        logger.warning('auto_create_charges_for_billing: cliente sem documento, pulando billing %s', billing.number)
        return

    client_email = client.emails.values_list('email', flat=True).first() or ''
    gw = _get_gateway()

    is_cash = billing.installments.count() == 1
    apply_discount = charge_config.discount_applies_to_installments or is_cash
    charge_kwargs = _charge_config_to_kwargs(charge_config, apply_discount)

    for installment in billing.installments.filter(status='PENDENTE'):
        try:
            with transaction.atomic():
                # Trava a parcela e refaz a checagem dentro da transação — evita duplicar a
                # cobrança caso o staff gere manualmente (admin) quase ao mesmo tempo do disparo
                # automático, ou caso este método seja chamado mais de uma vez para o mesmo billing.
                locked_installment = Installment.objects.select_for_update().get(pk=installment.pk)
                if locked_installment.gateway_charges.filter(
                    status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.RECEIVED,
                                GatewayCharge.Status.CONFIRMED]
                ).exists():
                    continue

                data = ChargeData(
                    customer_name=client.name,
                    customer_document=client_doc,
                    customer_email=client_email,
                    description=_charge_description(f'Parcela {installment.installment_number} — Cobrança #{billing.number}'),
                    amount=installment.amount,
                    due_date=installment.due_date,
                    method=method,
                    external_reference=str(installment.pk),
                    **charge_kwargs,
                )
                result = gw.create_charge(data, wallet_id=gw_config.wallet_id)
                GatewayCharge.objects.create(
                    installment=installment,
                    config=gw_config,
                    external_id=result.external_id,
                    method=method,
                    status=result.status,
                    amount=result.amount,
                    due_date=result.due_date,
                    pix_qrcode=result.pix_qrcode,
                    pix_copy_paste=result.pix_copy_paste,
                    pix_expiration_date=result.pix_expiration_date,
                    boleto_url=result.boleto_url,
                    boleto_barcode=result.boleto_barcode,
                    invoice_url=result.invoice_url,
                    invoice_number=result.invoice_number,
                )
        except Exception:
            logger.exception('auto_create_charges_for_billing: erro ao criar cobrança para parcela %s', installment.pk)


@login_required
@user_passes_test(is_manager)
def charge_config_list(request):
    configs = BillingChargeConfig.objects.all()
    return render(request, 'pagamentos/charge_config_list.html', {
        'configs': configs,
        'title': 'Regras de Cobrança',
        'active_menu': 'integracoes',
    })


@login_required
@user_passes_test(is_manager)
def charge_config_create(request):
    return _charge_config_form(request, instance=None)


@login_required
@user_passes_test(is_manager)
def charge_config_edit(request, pk):
    instance = get_object_or_404(BillingChargeConfig, pk=pk)
    return _charge_config_form(request, instance=instance)


def _charge_config_form(request, instance):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Informe um nome para a regra.')
            return redirect('pagamentos:charge_config_list')

        method_id = request.POST.get('default_payment_method_id', '').strip()
        if not method_id:
            messages.error(request, 'Selecione um método de pagamento para a regra.')
            return redirect('pagamentos:charge_config_list')
        payment_method = PaymentMethod.objects.filter(pk=method_id, ativo=True).first()
        if not payment_method:
            messages.error(request, 'Método de pagamento inválido ou inativo.')
            return redirect('pagamentos:charge_config_list')

        obj = instance or BillingChargeConfig()
        obj.name = name
        obj.default_payment_method = payment_method
        obj.due_days = int(request.POST.get('due_days', 1) or 1)
        obj.discount_type = request.POST.get('discount_type', 'NONE')
        obj.discount_due_days = int(request.POST.get('discount_due_days', 0) or 0)
        obj.discount_applies_to_installments = 'discount_applies_to_installments' in request.POST
        obj.interest_monthly = Decimal(request.POST.get('interest_monthly', '0').replace(',', '.') or '0')
        obj.fine_type = request.POST.get('fine_type', 'NONE')
        # Disparo automático só é possível para métodos de fato integrados ao gateway —
        # ignora o valor do POST se o método não permitir, mesmo que alguém burle o JS do form.
        obj.auto_send_to_gateway = (
            'auto_send_to_gateway' in request.POST and payment_method.integra_gateway
        )
        obj.is_active = 'is_active' in request.POST

        raw_discount = request.POST.get('discount_value', '0').replace(',', '.')
        raw_fine = request.POST.get('fine_value', '0').replace(',', '.')
        try:
            obj.discount_value = Decimal(raw_discount or '0')
        except Exception:
            obj.discount_value = Decimal('0')
        try:
            obj.fine_value = Decimal(raw_fine or '0')
        except Exception:
            obj.fine_value = Decimal('0')

        if obj.is_active:
            other_active = BillingChargeConfig.objects.filter(
                default_payment_method=payment_method, is_active=True
            ).exclude(pk=obj.pk)
            if other_active.exists():
                messages.error(
                    request,
                    f'Já existe a regra "{other_active.first().name}" ativa para '
                    f'"{payment_method.descricao}". Desative-a antes de ativar esta.'
                )
                return redirect('pagamentos:charge_config_list')

        obj.save()
        action = 'atualizada' if instance else 'criada'
        messages.success(request, f'Regra "{obj.name}" {action} com sucesso.')
        return redirect('pagamentos:charge_config_list')

    return render(request, 'pagamentos/charge_config_form.html', {
        'instance': instance,
        'discount_types': BillingChargeConfig.DiscountType.choices,
        'fine_types': BillingChargeConfig.FineType.choices,
        'payment_methods': PaymentMethod.objects.filter(ativo=True).order_by('descricao'),
        'title': ('Editar' if instance else 'Nova') + ' Regra de Cobrança',
        'active_menu': 'integracoes',
    })


@login_required
@user_passes_test(is_manager)
@require_POST
def charge_config_toggle(request, pk):
    config = get_object_or_404(BillingChargeConfig, pk=pk)
    config.is_active = not config.is_active
    config.save(update_fields=['is_active', 'updated_at'])
    state = 'ativada' if config.is_active else 'desativada'
    messages.success(request, f'Regra "{config.name}" {state}.')
    return redirect('pagamentos:charge_config_list')
