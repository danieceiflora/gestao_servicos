import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from services.models import Sale, ServiceOrderTask, User

from .builders import (
    FiscalValidationError, build_asaas_invoice_data, build_base_erp_sales_order_data,
    build_base_erp_sales_order_data_from_task,
)
from .gateways.asaas import AsaasInvoiceGateway
from .gateways.base import EmpresaData
from .gateways.base_erp import BaseERPGateway
from .gateways.focusnfe import FocusNFeError, FocusNFeGateway
from .models import NFeConfig, NFeDocument

logger = logging.getLogger(__name__)


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


def _get_gateway(config: NFeConfig) -> FocusNFeGateway:
    """Focus está aposentada por enquanto — só segue em uso aqui para consultar/
    cancelar NFe/NFCe emitidas no passado (novas emissões desse tipo estão
    desabilitadas na UI). NFSe passou a ser emitida via _get_asaas_gateway();
    NFe/NFCe de produto novas via _get_base_erp_gateway()."""
    return FocusNFeGateway(token=config.active_token, environment=config.environment)


def _get_asaas_gateway() -> AsaasInvoiceGateway:
    return AsaasInvoiceGateway()


def _get_base_erp_gateway() -> BaseERPGateway:
    return BaseERPGateway()


# --- CONFIGURAÇÃO ---

@login_required
@user_passes_test(is_manager)
def nfe_config_view(request):
    config = NFeConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        text_fields = [
            'environment', 'razao_social', 'nome_fantasia', 'cnpj',
            'inscricao_estadual', 'inscricao_municipal',
            'logradouro', 'numero', 'complemento', 'bairro', 'municipio',
            'codigo_municipio_ibge', 'uf', 'cep',
            'token_producao', 'token_homologacao', 'account_token',
            'webhook_token', 'default_codigo_tributacao_iss', 'default_codigo_tributacao_municipal_iss',
            'default_codigo_indicador_operacao',
            'default_ibs_cbs_situacao_tributaria', 'default_ibs_cbs_classificacao_tributaria',
            'default_codigo_nbs',
            'asaas_municipal_service_name', 'asaas_municipal_service_code',
            'asaas_municipal_service_id', 'asaas_municipal_service_label',
            'asaas_fiscal_email', 'asaas_cnae', 'asaas_special_tax_regime',
            'asaas_service_list_item', 'asaas_national_portal_tax_calc_regime', 'asaas_rps_serie',
            'base_erp_webhook_token',
        ]
        for f in text_fields:
            if f in request.POST:
                setattr(config, f, request.POST.get(f, '').strip())

        decimal_fields = [
            'asaas_iss_aliquota', 'asaas_pis_aliquota', 'asaas_cofins_aliquota',
            'asaas_csll_aliquota', 'asaas_inss_aliquota', 'asaas_ir_aliquota',
        ]
        for f in decimal_fields:
            if f in request.POST:
                raw = request.POST.get(f, '').strip().replace(',', '.')
                try:
                    setattr(config, f, Decimal(raw) if raw else Decimal('0'))
                except InvalidOperation:
                    messages.error(request, f'Valor inválido em "{f}" — use um número (ex: 2.5).')

        integer_fields = ['asaas_rps_number', 'asaas_lote_number']
        for f in integer_fields:
            if f in request.POST:
                raw = request.POST.get(f, '').strip()
                try:
                    setattr(config, f, int(raw) if raw else None)
                except ValueError:
                    messages.error(request, f'Valor inválido em "{f}" — use um número inteiro.')

        if request.POST.get('regime_tributario'):
            config.regime_tributario = int(request.POST['regime_tributario'])

        config.habilita_nfe = 'habilita_nfe' in request.POST
        config.habilita_nfce = 'habilita_nfce' in request.POST
        config.habilita_nfse = 'habilita_nfse' in request.POST
        config.asaas_retain_iss = 'asaas_retain_iss' in request.POST
        config.asaas_cultural_projects_promoter = 'asaas_cultural_projects_promoter' in request.POST
        config.asaas_simples_nacional = 'asaas_simples_nacional' in request.POST

        if config.status == NFeConfig.Status.NAO_CONFIGURADO and config.active_token:
            config.status = NFeConfig.Status.ATIVO

        config.save()

        if action == 'create_empresa':
            _handle_create_empresa(request, config)
        elif action == 'register_webhook':
            _handle_register_webhook(request, config)
        elif action == 'sync_asaas_fiscal_info':
            _handle_sync_asaas_fiscal_info(request, config)
        elif action == 'fetch_asaas_fiscal_info':
            _handle_fetch_asaas_fiscal_info(request, config)
        else:
            messages.success(request, 'Configurações salvas.')

        return redirect('fiscal:nfe_config')

    from django.conf import settings as dj_settings
    context = {
        'config': config,
        'title': 'Integração Fiscal — Asaas (NFSe)',
        'active_menu': 'integracoes',
        'asaas_api_key_set': bool(getattr(dj_settings, 'ASAAS_CLIENT_API_KEY', '')),
        'asaas_environment': getattr(dj_settings, 'ASAAS_CLIENT_ENVIRONMENT', 'SANDBOX'),
        'base_erp_api_key_set': bool(getattr(dj_settings, 'BASEERP_API_KEY', '')),
        'base_erp_environment': getattr(dj_settings, 'BASEERP_ENVIRONMENT', 'SANDBOX'),
        'base_erp_webhook_url': f"{dj_settings.SITE_URL.rstrip('/')}{reverse('fiscal:base_erp_webhook')}",
    }
    return render(request, 'fiscal/config.html', context)


def _handle_create_empresa(request, config: NFeConfig):
    if not config.account_token:
        messages.error(request, 'Informe o Token de Conta/Revenda da Focus para cadastrar a empresa por aqui '
                                 '(ou cole os tokens de produção/homologação manualmente se já cadastrou a '
                                 'empresa pelo painel da Focus).')
        return

    data = EmpresaData(
        razao_social=config.razao_social,
        cnpj=config.cnpj,
        inscricao_estadual=config.inscricao_estadual,
        inscricao_municipal=config.inscricao_municipal,
        regime_tributario=config.regime_tributario,
        logradouro=config.logradouro,
        numero=config.numero,
        complemento=config.complemento,
        bairro=config.bairro,
        municipio=config.municipio,
        codigo_municipio_ibge=config.codigo_municipio_ibge,
        uf=config.uf,
        cep=config.cep,
        habilita_nfe=config.habilita_nfe,
        habilita_nfce=config.habilita_nfce,
        habilita_nfse=config.habilita_nfse,
    )
    gw = FocusNFeGateway(token=config.account_token, environment=config.environment)
    try:
        result = gw.create_empresa(data) if not config.focus_empresa_id else gw.update_empresa(config.focus_empresa_id, data)
        config.focus_empresa_id = result.focus_id
        config.token_producao = result.token_producao or config.token_producao
        config.token_homologacao = result.token_homologacao or config.token_homologacao
        config.status = NFeConfig.Status.PENDENTE_CERTIFICADO
        config.status_detail = ''
        config.save()
        messages.success(request, 'Empresa cadastrada/atualizada na Focus! Agora anexe o certificado digital A1 '
                                   'pelo painel da Focus ("Serviços > Minhas Empresas > Anexar Certificado") — '
                                   'a Focus custodia o certificado, não fazemos upload por aqui.')
    except FocusNFeError as e:
        config.status = NFeConfig.Status.ERRO
        config.status_detail = f'{e.codigo}: {e.mensagem}'
        config.save()
        messages.error(request, f'Erro ao cadastrar empresa na Focus: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao cadastrar empresa na Focus')
        messages.error(request, f'Erro inesperado: {e}')


def _handle_register_webhook(request, config: NFeConfig):
    if not config.active_token:
        messages.error(request, 'Configure o token da empresa antes de registrar o webhook.')
        return
    if not config.webhook_token:
        config.webhook_token = uuid.uuid4().hex
        config.save(update_fields=['webhook_token'])

    from django.urls import reverse
    from django.conf import settings as dj_settings
    webhook_url = f"{dj_settings.SITE_URL.rstrip('/')}{reverse('fiscal:focusnfe_webhook')}"

    gw = _get_gateway(config)
    events = []
    if config.habilita_nfe:
        events.append('nfe')
    if config.habilita_nfce:
        events.append('nfce')
    if config.habilita_nfse:
        events.append('nfsen')

    errors = []
    for event in events:
        try:
            gw.create_webhook(event, webhook_url, config.webhook_token, 'X-Fiscal-Webhook-Token')
        except FocusNFeError as e:
            errors.append(f'{event}: {e.mensagem}')

    if errors:
        messages.warning(request, 'Webhook registrado com ressalvas: ' + '; '.join(errors))
    else:
        messages.success(request, f'Webhook registrado para: {", ".join(events) or "nenhum tipo habilitado"}.')


def _handle_sync_asaas_fiscal_info(request, config: NFeConfig):
    """Envia os dados fiscais DA CONTA (POST /fiscalInfo) — email de notificação,
    CNAE, Simples Nacional, regime especial, item da lista de serviços, série/
    número de RPS e lote. Razão social/CNPJ ficam de fora de propósito: são
    registro da própria conta Asaas (endpoint diferente, tipicamente com
    verificação de identidade), não algo pra reescrever por aqui. Ação explícita
    (botão próprio) porque grava direto na conta Asaas — não dispara sozinho."""
    try:
        gw = _get_asaas_gateway()
        gw.update_fiscal_info(
            email=config.asaas_fiscal_email,
            municipalInscription=config.inscricao_municipal,
            culturalProjectsPromoter=config.asaas_cultural_projects_promoter,
            cnae=config.asaas_cnae,
            simplesNacional=config.asaas_simples_nacional,
            specialTaxRegime=config.asaas_special_tax_regime,
            serviceListItem=config.asaas_service_list_item,
            nationalPortalTaxCalculationRegime=config.asaas_national_portal_tax_calc_regime,
            nbsCode=config.default_codigo_nbs,
            rpsSerie=config.asaas_rps_serie,
            rpsNumber=config.asaas_rps_number,
            loteNumber=config.asaas_lote_number,
        )
        messages.success(request, 'Dados fiscais enviados para a conta Asaas.')
    except Exception as e:
        logger.exception('Erro ao atualizar fiscalInfo na Asaas')
        messages.error(request, f'Erro ao enviar dados fiscais para a Asaas: {e}')


def _handle_fetch_asaas_fiscal_info(request, config: NFeConfig):
    """Busca o estado atual do fiscalInfo na Asaas e reflete nos campos locais —
    útil se alguém mexeu direto no painel da Asaas (ex: anexou certificado,
    ajustou RPS depois de emitir manualmente) e o cadastro local ficou desatualizado."""
    try:
        gw = _get_asaas_gateway()
        info = gw.get_fiscal_info()
        config.asaas_fiscal_email = info.get('email') or ''
        config.inscricao_municipal = info.get('municipalInscription') or ''
        config.asaas_cultural_projects_promoter = bool(info.get('culturalProjectsPromoter'))
        config.asaas_cnae = info.get('cnae') or ''
        config.asaas_simples_nacional = bool(info.get('simplesNacional'))
        config.asaas_special_tax_regime = info.get('specialTaxRegime') or ''
        config.asaas_service_list_item = info.get('serviceListItem') or ''
        config.asaas_national_portal_tax_calc_regime = info.get('nationalPortalTaxCalculationRegime') or ''
        config.default_codigo_nbs = info.get('nbsCode') or config.default_codigo_nbs
        config.asaas_rps_serie = info.get('rpsSerie') or ''
        config.asaas_rps_number = info.get('rpsNumber')
        config.asaas_lote_number = info.get('loteNumber')
        config.save()
        messages.success(request, 'Dados fiscais atualizados a partir da conta Asaas.')
    except Exception as e:
        logger.exception('Erro ao buscar fiscalInfo na Asaas')
        messages.error(request, f'Erro ao buscar dados fiscais da Asaas: {e}')


@login_required
@user_passes_test(is_manager)
def asaas_search_municipal_services(request):
    """GET usado via HTMX pela tela de config — busca no catálogo de serviços já
    homologados na conta Asaas (fiscal/gateways/asaas.py::list_municipal_services),
    pra referenciar o serviço por ID em vez de o usuário redigitar nome/código à
    mão (risco de não bater com o que está cadastrado lá — ver conversa que gerou
    isso: "Você precisa informar suas informações fiscais..." e depois notas
    rejeitadas por serviço não encontrado)."""
    query = request.GET.get('q', '').strip()
    results, error = [], ''
    if len(query) >= 3:
        try:
            results = _get_asaas_gateway().list_municipal_services(description=query, limit=15)
        except Exception as e:
            logger.exception('Erro ao buscar serviços municipais na Asaas')
            error = str(e)
    return render(request, 'fiscal/_municipal_service_results.html', {
        'results': results, 'query': query, 'error': error,
    })


# --- PAINEL (incluído em sale_form.html) ---

@login_required
def sale_nfe_panel(request, number):
    from django.conf import settings as dj_settings

    sale = get_object_or_404(Sale, number=number)
    config = NFeConfig.load()
    documents = NFeDocument.objects.filter(sale=sale).order_by('-created_at')
    return render(request, 'fiscal/_nfe_panel.html', {
        'nfe_config': config, 'sale': sale, 'documents': documents,
        'base_erp_sandbox': getattr(dj_settings, 'BASEERP_ENVIRONMENT', 'SANDBOX') == 'SANDBOX',
    })


# --- EMISSÃO ---

def _new_ref(prefix: str, number) -> str:
    return f'{prefix}-{number}-{uuid.uuid4().hex[:8]}'


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfe(request, number):
    return _emit_sale_document(request, number, 'NFE')


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfce(request, number):
    return _emit_sale_document(request, number, 'NFCE')


_BASE_ERP_INVOICE_TYPE = {'NFE': '55', 'NFCE': '65'}


def _run_base_erp_emission(gw, data, invoice_type: str, ref: str):
    """Garante cliente e cada produto no Base ERP (get_or_create), resolve o
    banco do recebível por nome, cria o pedido de venda e só então emite a
    nota. Compartilhado entre Sale (_emit_sale_document) e ServiceOrderTask
    (_emit_task_document) — o `data` (BaseERPSalesOrderData) já vem pronto do
    builder correspondente, só muda a origem dos itens/cliente.

    Retorna (sales_order_id, invoice_result)."""
    customer_id = gw.get_or_create_customer(
        name=data.client_name,
        document=data.client_document,
        address=data.client_address,
        tax_info=data.client_tax_info,
    )
    order_items = []
    for item in data.items:
        product_id = gw.get_or_create_product(
            code=item.product_code,
            name=item.product_name,
            ncm=item.product_ncm,
            unit=item.product_unit,
            barcode=item.product_barcode,
        )
        order_items.append({
            'productId': product_id,
            'quantity': float(item.quantity),
            'unitPrice': float(item.unit_price),
        })

    bank_id = gw.get_bank_id_by_name()
    payments = [{
        'bankId': bank_id,
        'billingType': data.billing_type,
        'dueDate': data.issue_date.strftime('%Y-%m-%d'),
        'value': float(data.payment_value),
    }]

    sales_order_id = gw.create_sales_order(
        customer_id=customer_id, items=order_items, issue_date=data.issue_date,
        payments=payments, external_reference=ref, observations=data.observations,
    )
    invoice_result = gw.emit_invoice(sales_order_id, invoice_type)
    return sales_order_id, invoice_result


def _emit_sale_document(request, number, document_type):
    """NFe/NFCe de produto de uma Venda — emitida via Base ERP (Focus está
    aposentada, ver build_base_erp_sales_order_data/BaseERPGateway)."""
    sale = get_object_or_404(Sale, number=number)
    config = NFeConfig.load()

    can_emit = config.can_emit_nfe if document_type == 'NFE' else config.can_emit_nfce
    if not can_emit:
        messages.error(request, 'Emissão de nota fiscal não está habilitada. Configure a integração primeiro.')
        return redirect('sale_detail', number=number)

    invoice_type = _BASE_ERP_INVOICE_TYPE[document_type]
    ref = _new_ref('venda', sale.number)
    doc = NFeDocument.objects.create(document_type=document_type, sale=sale, ref=ref)

    try:
        data = build_base_erp_sales_order_data(sale, invoice_type)
        gw = _get_base_erp_gateway()
        sales_order_id, invoice_result = _run_base_erp_emission(gw, data, invoice_type, ref)
        _apply_base_erp_result(doc, sales_order_id, invoice_result)
        messages.success(request, f'{doc.get_document_type_display()} enviada para emissão (pedido Base ERP #{sales_order_id}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save(update_fields=['status', 'mensagem_sefaz', 'error_details', 'updated_at'])
        for problem in e.problems:
            messages.error(request, problem)
    except Exception as e:
        logger.exception('Erro inesperado ao emitir documento fiscal para Sale #%s', number)
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save(update_fields=['status', 'mensagem_sefaz', 'updated_at'])
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('sale_detail', args=[number])}#fiscal")


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfse(request, task_id):
    """NFSe cobre só os itens de SERVIÇO da etapa — ver build_asaas_invoice_data.
    Emitida via Asaas (Focus está aposentada por enquanto)."""
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order_id = task.service_order_id
    config = NFeConfig.load()

    if not config.can_emit_nfse:
        messages.error(request, 'Emissão de NFSe não está habilitada. Configure a integração Asaas primeiro.')
        return redirect('service_order_detail', order_id=order_id)

    ref = _new_ref('etapa', str(task.id)[:8])
    doc = NFeDocument.objects.create(document_type=NFeDocument.DocumentType.NFSE, task=task, ref=ref)

    try:
        invoice_data = build_asaas_invoice_data(task)
        invoice_data.external_reference = ref

        prop = task.service_order.client_property
        client = prop.client
        gw = _get_asaas_gateway()
        invoice_data.customer = gw.get_or_create_customer(
            name=client.display_name,
            document=client.document or '',
            email=client.emails.values_list('email', flat=True).first() or '',
            address={
                'address': prop.address,
                'addressNumber': prop.number or 'S/N',
                'complement': prop.complement or '',
                'province': prop.neighborhood,
                'postalCode': re.sub(r'\D', '', prop.cep or ''),
            },
        )

        result = gw.emit_invoice(invoice_data)
        _apply_asaas_result(doc, result)
        messages.success(request, f'NFSe enviada para autorização (ref {ref}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save(update_fields=['status', 'mensagem_sefaz', 'error_details', 'updated_at'])
        for problem in e.problems:
            messages.error(request, problem)
    except Exception as e:
        logger.exception('Erro inesperado ao emitir NFSe para etapa #%s', task_id)
        # update_fields (em vez de save() completo): se a falha veio de
        # _apply_asaas_result já ter deixado algum campo None em memória antes de
        # estourar o IntegrityError (ex: codigo_verificacao), um save() completo
        # repete a mesma violação NOT NULL — dessa vez sem try/except em volta.
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save(update_fields=['status', 'mensagem_sefaz', 'updated_at'])
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('service_order_detail', args=[order_id])}#nota-fiscal")


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_task_nfe(request, task_id):
    return _emit_task_document(request, task_id, 'NFE')


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_task_nfce(request, task_id):
    return _emit_task_document(request, task_id, 'NFCE')


def _emit_task_document(request, task_id, document_type):
    """NFe/NFCe da etapa cobre só os itens de PRODUTO — ver
    build_base_erp_sales_order_data_from_task. Emitida via Base ERP (Focus
    está aposentada), mesma migração que _emit_sale_document já fez."""
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order_id = task.service_order_id
    config = NFeConfig.load()

    can_emit = config.can_emit_nfe if document_type == 'NFE' else config.can_emit_nfce
    if not can_emit:
        messages.error(request, 'Emissão de nota fiscal não está habilitada. Configure a integração primeiro.')
        return redirect('service_order_detail', order_id=order_id)

    invoice_type = _BASE_ERP_INVOICE_TYPE[document_type]
    ref = _new_ref('etapa', str(task.id)[:8])
    doc = NFeDocument.objects.create(document_type=document_type, task=task, ref=ref)

    try:
        data = build_base_erp_sales_order_data_from_task(task, invoice_type)
        gw = _get_base_erp_gateway()
        sales_order_id, invoice_result = _run_base_erp_emission(gw, data, invoice_type, ref)
        _apply_base_erp_result(doc, sales_order_id, invoice_result)
        messages.success(request, f'{doc.get_document_type_display()} enviada para emissão (pedido Base ERP #{sales_order_id}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save(update_fields=['status', 'mensagem_sefaz', 'error_details', 'updated_at'])
        for problem in e.problems:
            messages.error(request, problem)
    except Exception as e:
        logger.exception('Erro inesperado ao emitir documento fiscal para etapa #%s', task_id)
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save(update_fields=['status', 'mensagem_sefaz', 'updated_at'])
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('service_order_detail', args=[order_id])}#nota-fiscal")


def _apply_result(doc: NFeDocument, result):
    status_map = {
        'processando_autorizacao': NFeDocument.Status.PROCESSANDO,
        'autorizado': NFeDocument.Status.AUTORIZADO,
        'erro_autorizacao': NFeDocument.Status.ERRO,
        'cancelado': NFeDocument.Status.CANCELADO,
    }
    doc.status = status_map.get(result.status, NFeDocument.Status.PROCESSANDO)
    doc.numero = result.numero
    doc.serie = result.serie
    doc.chave_acesso = result.chave_acesso
    doc.codigo_verificacao = result.codigo_verificacao
    doc.status_sefaz = result.status_sefaz
    doc.mensagem_sefaz = result.mensagem_sefaz
    doc.xml_url = result.xml_url or ''
    doc.pdf_url = result.pdf_url or ''
    doc.qrcode_url = result.qrcode_url or ''
    doc.error_details = result.error_details
    doc.raw_response = result.raw
    doc.save()


_ASAAS_STATUS_MAP = {
    'SCHEDULED': NFeDocument.Status.PROCESSANDO,
    'SYNCHRONIZED': NFeDocument.Status.PROCESSANDO,
    'AUTHORIZED': NFeDocument.Status.AUTORIZADO,
    'PROCESSING_CANCELLATION': NFeDocument.Status.PROCESSANDO,
    'CANCELED': NFeDocument.Status.CANCELADO,
    'CANCELLATION_DENIED': NFeDocument.Status.AUTORIZADO,
    'ERROR': NFeDocument.Status.ERRO,
}


def _apply_asaas_result(doc: NFeDocument, result):
    doc.gateway_id = result.external_id or doc.gateway_id
    doc.status = _ASAAS_STATUS_MAP.get(result.status, NFeDocument.Status.PROCESSANDO)
    doc.numero = result.number
    doc.serie = result.rps_serie
    doc.codigo_verificacao = result.validation_code
    doc.status_sefaz = result.status
    doc.mensagem_sefaz = result.status_description
    doc.xml_url = result.xml_url or ''
    doc.pdf_url = result.pdf_url or ''
    doc.raw_response = result.raw
    doc.save()


# invoiceStatus (Base ERP) — enum documentado, mas sem endpoint de download de
# XML/PDF/chave de acesso na API deles (só disponível pelo painel web, até onde
# vimos na doc de referência) — por isso xml_url/pdf_url/chave_acesso ficam
# vazios aqui, diferente de Focus/Asaas.
_BASE_ERP_STATUS_MAP = {
    'EMITIDA': NFeDocument.Status.AUTORIZADO,
    'NOTA_AUTORIZADA_DFE': NFeDocument.Status.AUTORIZADO,
    'CANCELADA': NFeDocument.Status.CANCELADO,
    'INUTILIZADA': NFeDocument.Status.CANCELADO,
    'NEGADA': NFeDocument.Status.ERRO,
    'DENEGADA': NFeDocument.Status.ERRO,
    'CANCELAMENTO_NEGADO': NFeDocument.Status.ERRO,
    'ERRO_ENVIO': NFeDocument.Status.ERRO,
    'REJEITADA': NFeDocument.Status.ERRO,
    'AJUSTES_NECESSARIOS': NFeDocument.Status.ERRO,
}


def _apply_base_erp_result(doc: NFeDocument, sales_order_id, result: dict):
    """`result` é a resposta de POST /salesOrders/{id}/invoice
    (SalesOrderInvoiceOutputDto: id/invoiceId/invoiceNumber/invoiceStatus).
    `gateway_id` guarda o id do PEDIDO (salesOrder), não o da nota — é o que
    `refresh_nfe_status`/`cancel_nfe` vão precisar para consultar/cancelar
    depois (GET/PUT /salesOrders/{id}/...), igual ao papel que o id da invoice
    Asaas tem para NFSe."""
    doc.gateway_id = str(sales_order_id)
    status = result.get('invoiceStatus') or ''
    doc.status = _BASE_ERP_STATUS_MAP.get(status, NFeDocument.Status.PROCESSANDO)
    doc.numero = str(result.get('invoiceNumber') or '')
    doc.status_sefaz = status
    # cancel_invoice devolve AsyncResponseDto (id/status/message), sem
    # invoiceStatus — `message` cobre esse caso ("Aguarde a confirmação de
    # cancelamento"), sem sobrescrever à toa quando vier vazio.
    if result.get('message'):
        doc.mensagem_sefaz = result['message']
    doc.raw_response = result
    doc.save()


@login_required
@user_passes_test(is_manager)
@require_POST
def refresh_nfe_status(request, pk):
    doc = get_object_or_404(NFeDocument, pk=pk)

    try:
        if doc.document_type == NFeDocument.DocumentType.NFSE:
            result = _get_asaas_gateway().get_invoice(doc.gateway_id)
            _apply_asaas_result(doc, result)
        elif doc.gateway_id:
            # NFe/NFCe emitida via Base ERP — gateway_id guarda o id do
            # salesOrder (docs antigos da Focus nunca preenchem esse campo,
            # só `ref`, daí o fallback no else abaixo).
            result = _get_base_erp_gateway().get_sales_order(doc.gateway_id)
            _apply_base_erp_result(doc, doc.gateway_id, result)
        else:
            # NFe/NFCe (Focus) — emissão nova está desabilitada, mas documentos
            # antigos continuam consultáveis pelo gateway que os emitiu.
            config = NFeConfig.load()
            gw = _get_gateway(config)
            result = gw.consultar_nfe(doc.ref) if doc.document_type == NFeDocument.DocumentType.NFE else gw.consultar_nfce(doc.ref)
            _apply_result(doc, result)
        messages.success(request, f'Status atualizado: {doc.get_status_display()}.')
    except FocusNFeError as e:
        messages.error(request, f'Erro ao consultar status: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao consultar status do documento fiscal #%s', pk)
        messages.error(request, f'Erro inesperado: {e}')

    return _redirect_to_owner(doc)


@login_required
@user_passes_test(is_manager)
@require_POST
def cancel_nfe(request, pk):
    doc = get_object_or_404(NFeDocument, pk=pk)
    justificativa = request.POST.get('justificativa', '').strip()

    if len(justificativa) < 15:
        messages.error(request, 'A justificativa de cancelamento precisa ter pelo menos 15 caracteres.')
        return _redirect_to_owner(doc)

    try:
        if doc.document_type == NFeDocument.DocumentType.NFSE:
            result = _get_asaas_gateway().cancel_invoice(doc.gateway_id)
            _apply_asaas_result(doc, result)
        elif doc.gateway_id:
            result = _get_base_erp_gateway().cancel_invoice(doc.gateway_id, justificativa)
            _apply_base_erp_result(doc, doc.gateway_id, result)
        else:
            config = NFeConfig.load()
            gw = _get_gateway(config)
            result = gw.cancelar_nfe(doc.ref, justificativa) if doc.document_type == NFeDocument.DocumentType.NFE else gw.cancelar_nfce(doc.ref, justificativa)
            _apply_result(doc, result)
        doc.cancelled_at = timezone.now()
        doc.cancel_justificativa = justificativa
        doc.save(update_fields=['cancelled_at', 'cancel_justificativa'])
        messages.success(request, 'Documento fiscal cancelado.')
    except FocusNFeError as e:
        messages.error(request, f'Erro ao cancelar: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao cancelar documento fiscal #%s', pk)
        messages.error(request, f'Erro inesperado: {e}')

    return _redirect_to_owner(doc)


def _redirect_to_owner(doc: NFeDocument):
    if doc.sale_id:
        return redirect(f"{reverse('sale_detail', args=[doc.sale.number])}#fiscal")
    return redirect(f"{reverse('service_order_detail', args=[doc.task.service_order_id])}#nota-fiscal")


# --- WEBHOOK ---

@csrf_exempt
def focusnfe_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    config = NFeConfig.load()
    if config.webhook_token:
        received = request.headers.get('X-Fiscal-Webhook-Token', '')
        if received != config.webhook_token:
            logger.warning('Webhook FocusNFe: token inválido recebido: %r', received)
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
        ref = payload.get('ref')
        if not ref:
            return JsonResponse({'ok': True})

        doc = NFeDocument.objects.filter(ref=ref).first()
        if not doc:
            logger.warning('Webhook FocusNFe: documento não encontrado para ref %r', ref)
            return JsonResponse({'ok': True})

        status_map = {
            'processando_autorizacao': NFeDocument.Status.PROCESSANDO,
            'autorizado': NFeDocument.Status.AUTORIZADO,
            'erro_autorizacao': NFeDocument.Status.ERRO,
            'cancelado': NFeDocument.Status.CANCELADO,
        }
        new_status = status_map.get(payload.get('status'))
        if new_status:
            doc.status = new_status
        doc.numero = str(payload.get('numero', '') or doc.numero)
        doc.chave_acesso = payload.get('chave_nfe', '') or doc.chave_acesso
        doc.codigo_verificacao = payload.get('codigo_verificacao', '') or doc.codigo_verificacao
        doc.status_sefaz = str(payload.get('status_sefaz', '') or doc.status_sefaz)
        doc.mensagem_sefaz = payload.get('mensagem_sefaz', '') or doc.mensagem_sefaz
        doc.xml_url = payload.get('caminho_xml_nota_fiscal', '') or doc.xml_url
        doc.pdf_url = payload.get('caminho_danfe', '') or doc.pdf_url
        doc.error_details = payload.get('erros') or doc.error_details
        doc.raw_response = payload
        doc.save()
        logger.info('Webhook FocusNFe processado: %s → %s', ref, doc.status)
    except Exception:
        logger.exception('Erro ao processar webhook FocusNFe')

    return JsonResponse({'ok': True})


@csrf_exempt
def base_erp_webhook(request):
    """Webhook de NF-e/NFC-e do Base ERP — cadastrado MANUALMENTE no painel deles
    (Menu do usuário > Configurações > Integrações > Webhooks), não por API (o
    POST /webhooks se mostrou instável no sandbox ao tentar automatizar isso).
    Eventos relevantes: INVOICE_NFE_CREATED, INVOICE_NFE_AUTHORIZED,
    INVOICE_NFE_ERROR, INVOICE_NFE_CANCELED (ver AsaasApiWebHookCreateDto na
    doc de referência do Base ERP).

    Formato real confirmado com um evento de produção (payload não é
    documentado no OpenAPI deles, só o nome do evento):
    {
      "event": "INVOICE_NFE_AUTHORIZED",
      "invoiceNfe": {
        "status": "EMITIDA", "number": "260", "serie": "1",
        "invoiceId": "...", "salesOrderId": "100194680",
        "pdfUrl": "https://api.../link/download/...",
        "xmlUrl": "https://api.../link/download/..."
      }
    }
    `salesOrderId` é o que casa com o `gateway_id` que gravamos em
    NFeDocument. Mantém alguns nomes alternativos como fallback defensivo
    (payloads de outros eventos podem variar) e sempre grava o payload cru em
    `raw_response`/log."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    config = NFeConfig.load()
    if config.base_erp_webhook_token:
        received = request.headers.get('asaas-access-token', '')
        if received != config.base_erp_webhook_token:
            logger.warning('Webhook Base ERP: token inválido recebido: %r', received)
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except Exception:
        logger.exception('Webhook Base ERP: payload não é JSON válido: %r', request.body[:500])
        return JsonResponse({'ok': True})

    logger.info('Webhook Base ERP recebido: %s', json.dumps(payload, ensure_ascii=False)[:2000])

    try:
        event = payload.get('event') or payload.get('type') or ''
        inner = payload.get('invoiceNfe') or payload.get('salesOrder') or payload.get('order') or payload.get('invoice') or payload
        sales_order_id = (
            inner.get('salesOrderId') or inner.get('orderId') or inner.get('id')
            or payload.get('salesOrderId') or payload.get('orderId')
        )
        if not sales_order_id:
            logger.warning('Webhook Base ERP: não encontrei id do pedido no payload (evento %s)', event)
            return JsonResponse({'ok': True})

        doc = NFeDocument.objects.filter(gateway_id=str(sales_order_id)).first()
        if not doc:
            logger.warning('Webhook Base ERP: documento não encontrado para pedido #%s (evento %s)', sales_order_id, event)
            return JsonResponse({'ok': True})

        status = inner.get('status') or inner.get('invoiceStatus') or ''
        if status:
            doc.status = _BASE_ERP_STATUS_MAP.get(status, doc.status)
            doc.status_sefaz = status
        if 'ERROR' in event or 'ERRO' in event:
            doc.status = NFeDocument.Status.ERRO
            doc.mensagem_sefaz = inner.get('message') or inner.get('reason') or doc.mensagem_sefaz

        numero = inner.get('number') or inner.get('invoiceNumber')
        if numero:
            doc.numero = str(numero)
        if inner.get('serie'):
            doc.serie = str(inner['serie'])
        for key in ('pdfUrl', 'danfeUrl', 'urlPdf', 'pdf'):
            if inner.get(key):
                doc.pdf_url = inner[key]
                break
        for key in ('xmlUrl', 'urlXml', 'xml'):
            if inner.get(key):
                doc.xml_url = inner[key]
                break
        for key in ('accessKey', 'chaveAcesso', 'chave', 'key'):
            if inner.get(key):
                doc.chave_acesso = inner[key]
                break

        doc.raw_response = payload
        doc.save()
        logger.info('Webhook Base ERP processado: pedido #%s → %s (evento %s)', sales_order_id, doc.status, event)
    except Exception:
        logger.exception('Erro ao processar webhook Base ERP')

    return JsonResponse({'ok': True})
