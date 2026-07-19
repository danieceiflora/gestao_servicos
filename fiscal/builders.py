"""Monta os payloads JSON esperados pela API da Focus a partir dos modelos locais.

Funções puras — não fazem chamada de rede, só leitura de models já carregados —
para serem fáceis de testar isoladamente (ver fiscal/tests.py). Os valores
fiscais de item (NCM/CEST/origem/CFOP) já vêm "congelados" em SaleItem/ServiceItem
no momento da venda/execução (`ncm_ato`, `cest_ato`, `origem_ato`, `cfop_aplicado`),
então não há cálculo fiscal novo aqui — só remapeamento de campo.

Emissão de OS é por ETAPA (ServiceOrderTask), não pela OS inteira: cada etapa pode
ter produto e serviço misturados no mesmo faturamento, e o padrão de mercado (e a
própria LC 116/2003, item 7.02) exige documentos e tributação separados — nunca
somar produto e serviço no mesmo documento fiscal. Por isso:
  - build_nfe_or_nfce_payload_from_task() cobre só os itens com `product` da etapa.
  - build_nfse_nacional_payload() cobre só os itens com `service` da etapa.
O desconto único da etapa (ServiceOrderTask.discount, em R$) é rateado
proporcionalmente entre as duas partes (ver _task_value_split), para a soma dos
dois documentos continuar batendo com o valor total da etapa/cobrança.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import NFeConfig

BRASILIA_TZ = ZoneInfo('America/Sao_Paulo')

# Códigos de unidade comercial/tributável aceitos pelo layout da NFe (campo uCom/uTrib,
# maxLength=6) — Product.get_unit_type_display() retorna um rótulo longo (ex: "Unidade
# (un)"), que não cabe no limite e quebra a validação de schema na Focus.
UNIT_CODES = {
    'UNIDADE': 'UN',
    'METRO': 'MT',
    'M2': 'M2',
    'LITRO': 'LT',
    'QUILO': 'KG',
}


class FiscalValidationError(Exception):
    """Erro de pré-validação local — dados obrigatórios ausentes/incompletos antes
    mesmo de chamar a Focus. Mensagens acionáveis, em vez do erro genérico de
    validação de schema que a Focus devolve quando um campo obrigatório vem vazio
    ou fora do formato esperado."""

    def __init__(self, problems: list):
        self.problems = problems
        super().__init__('; '.join(problems))


def _now_iso() -> str:
    """Data/hora atual de Brasília em ISO 8601 com offset explícito (ex: -03:00),
    exigido pelo campo data_emissao da Focus/SEFAZ.

    Não usa django.utils.timezone.now(): este projeto roda com USE_TZ = DEBUG
    (core/settings.py) — em produção (DEBUG=False → USE_TZ=False) timezone.now()
    retorna um datetime *naive*, e formatar isso com strftime('%z') produz string
    vazia (sem offset). Sem offset, a SEFAZ assume UTC e interpreta o horário de
    Brasília como se já fosse UTC — ~3h "no futuro" — rejeitando a NFe com
    'Data-Hora de Emissão posterior ao horário de recebimento'. Usar zoneinfo
    direto evita essa ambiguidade independente de USE_TZ."""
    return datetime.now(BRASILIA_TZ).isoformat(timespec='seconds')


def _money(value) -> float:
    if value is None:
        value = Decimal('0')
    return float(Decimal(value).quantize(Decimal('0.01')))


def _unit_code(product) -> str:
    return UNIT_CODES.get(product.unit_type, 'UN')


def _local_destino_from_cfop(cfop: str) -> int:
    """idDest a partir do 1º dígito do CFOP já calculado no item (SaleItem/ServiceItem
    .cfop_aplicado, via fiscal_logic.get_cfop() — fonte única de verdade, não
    recalculamos aqui para não divergir). 5xxx = interna (1), 6xxx = interestadual (2),
    7xxx = exterior (3). A SEFAZ rejeita com 'CFOP de operação interestadual e idDest
    diferente de 2' se os dois não baterem."""
    if not cfop:
        return 1
    first_digit = cfop[0]
    if first_digit == '6':
        return 2
    if first_digit == '7':
        return 3
    return 1


def _is_contribuinte_icms(client) -> bool:
    """Considera contribuinte apenas PJ com Inscrição Estadual cadastrada. PF, ou PJ
    sem IE, é 'não contribuinte' — e nesse caso a SEFAZ exige indFinal=1 (operação
    com consumidor final), senão rejeita com 'Operação com não contribuinte deve
    indicar operação com consumidor final'."""
    return bool(client) and client.client_type == 'PJ' and bool(client.state_registration)


def _clean_doc(value) -> str:
    import re
    return re.sub(r'\D', '', value or '')


def _emitente_dict(config: NFeConfig) -> dict:
    return {
        'cnpj_emitente': _clean_doc(config.cnpj),
        'nome_emitente': config.razao_social,
        'nome_fantasia_emitente': config.nome_fantasia,
        'logradouro_emitente': config.logradouro,
        'numero_emitente': config.numero,
        'bairro_emitente': config.bairro,
        'municipio_emitente': config.municipio,
        'uf_emitente': config.uf,
        'cep_emitente': _clean_doc(config.cep),
        'inscricao_estadual_emitente': config.inscricao_estadual,
        'regime_tributario_emitente': config.regime_tributario,
    }


def _destinatario_dict(client) -> dict:
    if not client:
        return {}
    data = {'nome_destinatario': client.display_name}
    document = _clean_doc(client.document)
    if client.client_type == 'PJ':
        data['cnpj_destinatario'] = document
        data['inscricao_estadual_destinatario'] = client.state_registration or ''
        # indIEDest: 1 = Contribuinte ICMS, 9 = Não Contribuinte (sem IE)
        data['indicador_inscricao_estadual_destinatario'] = 1 if _is_contribuinte_icms(client) else 9
    else:
        data['cpf_destinatario'] = document
        data['indicador_inscricao_estadual_destinatario'] = 9  # PF é sempre não contribuinte

    prop = client.properties.first()
    if prop:
        data.update({
            'logradouro_destinatario': prop.address,
            'numero_destinatario': prop.number or 'S/N',
            'bairro_destinatario': prop.neighborhood,
            'municipio_destinatario': prop.city,
            'uf_destinatario': prop.state,
            'cep_destinatario': _clean_doc(prop.cep),
            'pais_destinatario': 'Brasil',
        })
    return data


def _item_dict(index: int, item) -> dict:
    """Funciona tanto para SaleItem (tem .subtotal/.discount próprios) quanto para
    ServiceItem (não tem — cai no cálculo via quantity*unit_price e desconto 0, já
    que o desconto do ServiceItem é só no nível da etapa, tratado à parte)."""
    product = item.product
    subtotal = getattr(item, 'subtotal', None)
    if subtotal is None:
        subtotal = item.quantity * item.unit_price
    discount = getattr(item, 'discount', None) or Decimal('0')
    return {
        'numero_item': index,
        'codigo_produto': product.code or str(product.pk),
        'descricao': product.name,
        'cfop': item.cfop_aplicado or product.cfop_padrao or '',
        'codigo_ncm': item.ncm_ato or product.ncm or '',
        'cest': item.cest_ato or product.cest or '',
        'origem': item.origem_ato if item.origem_ato is not None else product.origem_mercadoria,
        'quantidade_comercial': float(item.quantity),
        'quantidade_tributavel': float(item.quantity),
        'valor_unitario_comercial': _money(item.unit_price),
        'valor_unitario_tributavel': _money(item.unit_price),
        'valor_bruto': _money(subtotal),
        'valor_desconto': _money(discount),
        'unidade_comercial': _unit_code(product),
        'unidade_tributavel': _unit_code(product),
        'icms_situacao_tributaria': product.csosn or product.cst_icms or '',
        'pis_situacao_tributaria': product.cst_pis or '',
        'cofins_situacao_tributaria': product.cst_cofins or '',
    }


def _validate_client_for_emission(client, require_address: bool) -> list:
    problems = []
    if not client:
        problems.append('Nenhum cliente definido para esta operação.')
    elif not client.document:
        problems.append(f'Cliente "{client.display_name}" sem CPF/CNPJ cadastrado.')
    elif require_address and not client.properties.exists():
        problems.append(f'Cliente "{client.display_name}" sem endereço cadastrado (necessário para NFe).')
    return problems


def _validate_product_items(items) -> list:
    problems = []
    if not items:
        problems.append('Nenhum item de produto faturável encontrado — nada para emitir.')
    for item in items:
        product = item.product
        label = product.name
        if not (item.ncm_ato or product.ncm):
            problems.append(f'Produto "{label}": NCM não cadastrado.')
        if not (item.cfop_aplicado or product.cfop_padrao):
            problems.append(f'Produto "{label}": CFOP não cadastrado/calculado.')
        if not (product.csosn or product.cst_icms):
            problems.append(f'Produto "{label}": CSOSN/CST ICMS não cadastrado.')
        if not product.cst_pis:
            problems.append(f'Produto "{label}": CST PIS não cadastrado (a NF-e precisa do grupo PIS em todo item).')
        if not product.cst_cofins:
            problems.append(f'Produto "{label}": CST COFINS não cadastrado (a NF-e precisa do grupo COFINS em todo item).')
    return problems


def _build_nfe_or_nfce_common(*, config, client, items, document_type, header_desconto, header_total, header_produtos, modalidade_frete, natureza_operacao, extra_validation=None) -> dict:
    problems = _validate_client_for_emission(client, require_address=(document_type == 'NFE'))
    problems += _validate_product_items(items)
    if extra_validation:
        problems += extra_validation
    if problems:
        raise FiscalValidationError(problems)

    is_contribuinte = _is_contribuinte_icms(client)
    consumidor_final = 1 if (document_type == 'NFCE' or not is_contribuinte) else 0

    item_dicts = [_item_dict(i + 1, item) for i, item in enumerate(items)]
    # idDest precisa bater com o CFOP dos itens (interno x interestadual x exterior) —
    # todos os itens de uma mesma operação têm o mesmo destinatário, então o CFOP do
    # primeiro item já determina a operação toda.
    local_destino = _local_destino_from_cfop(item_dicts[0]['cfop']) if item_dicts else 1

    payload = {
        'natureza_operacao': natureza_operacao,
        'data_emissao': _now_iso(),
        'tipo_documento': 1,       # 1 = Saída
        'finalidade_emissao': 1,   # 1 = Normal
        'consumidor_final': consumidor_final,
        'local_destino': local_destino,
    }
    payload.update(_emitente_dict(config))
    payload.update(_destinatario_dict(client))

    payload['items'] = item_dicts
    payload['valor_desconto'] = _money(header_desconto)
    payload['valor_outras_despesas'] = _money(0)
    payload['valor_total'] = _money(header_total)
    payload['valor_produtos'] = _money(header_produtos)
    payload['modalidade_frete'] = modalidade_frete

    return payload


def build_nfe_or_nfce_payload(sale, document_type: str = 'NFE') -> dict:
    """document_type: 'NFE' ou 'NFCE'. A NFCe usa presenca_comprador/formas_pagamento
    a mais; o restante é idêntico. Levanta FiscalValidationError se algum campo
    obrigatório estiver ausente."""
    config = NFeConfig.load()
    items = list(sale.items.select_related('product'))
    produtos_total = sum((item.subtotal for item in items), Decimal('0'))

    payload = _build_nfe_or_nfce_common(
        config=config, client=sale.client, items=items, document_type=document_type,
        header_desconto=sale.discount, header_total=sale.total_amount,
        header_produtos=produtos_total, modalidade_frete=sale.modalidade_frete,
        natureza_operacao='Venda de mercadoria',
    )
    payload['valor_outras_despesas'] = _money(sale.surcharge)

    if document_type == 'NFCE':
        payload['presenca_comprador'] = sale.indicador_presenca
        payload['formas_pagamento'] = [{
            'forma_pagamento': sale.forma_pagamento_sefaz,
            'valor_pagamento': _money(sale.total_amount),
        }]

    return payload


def _task_value_split(task) -> dict:
    """Rateia o desconto único da etapa (ServiceOrderTask.discount, em R$)
    proporcionalmente entre a parte de produto e a parte de serviço do mesmo
    faturamento, para a soma dos dois documentos fiscais (NFe do produto + NFSe do
    serviço) continuar batendo com o valor total da etapa/cobrança já gerada."""
    items = list(task.items.filter(cobrar_cliente=True).select_related('product', 'service'))
    product_gross = sum((i.quantity * i.unit_price for i in items if i.product_id), Decimal('0'))
    service_gross = sum((i.quantity * i.unit_price for i in items if i.service_id), Decimal('0'))
    total_gross = product_gross + service_gross
    discount = task.discount or Decimal('0')

    if total_gross <= 0:
        return {'product_gross': Decimal('0'), 'product_net': Decimal('0'),
                'service_gross': Decimal('0'), 'service_net': Decimal('0')}

    product_discount = (discount * product_gross / total_gross)
    service_discount = discount - product_discount
    return {
        'product_gross': product_gross,
        'product_net': max(product_gross - product_discount, Decimal('0')),
        'service_gross': service_gross,
        'service_net': max(service_gross - service_discount, Decimal('0')),
    }


def build_nfe_or_nfce_payload_from_task(task, document_type: str = 'NFE') -> dict:
    """Emite NFe/NFCe só pelos itens de PRODUTO de uma etapa da OS (ServiceItem com
    `product` preenchido) — a parte de serviço da mesma etapa vai em NFSe separada
    (build_nfse_nacional_payload), nunca no mesmo documento."""
    config = NFeConfig.load()
    client = task.service_order.client_property.client
    items = list(task.items.filter(product__isnull=False, cobrar_cliente=True).select_related('product'))
    split = _task_value_split(task)

    payload = _build_nfe_or_nfce_common(
        config=config, client=client, items=items, document_type=document_type,
        header_desconto=split['product_gross'] - split['product_net'],
        header_total=split['product_net'], header_produtos=split['product_gross'],
        modalidade_frete=9,  # 9 = Sem ocorrência de transporte — instalação não é "frete"
        natureza_operacao='Venda de mercadoria com instalação',
    )

    if document_type == 'NFCE':
        sale_client = task.service_order.client_property.client
        payload['presenca_comprador'] = 1  # presencial — instalação é feita no local
        payload['formas_pagamento'] = [{
            'forma_pagamento': '99',  # 99 = Outros — OS não tem um campo próprio de forma de pagamento SEFAZ
            'valor_pagamento': _money(split['product_net']),
        }]

    return payload


def _data_competencia_task(task) -> str:
    if task.finished_at:
        return task.finished_at.astimezone(BRASILIA_TZ).date().isoformat()
    return datetime.now(BRASILIA_TZ).date().isoformat()


def _resolve_codigo_tributacao_iss_task(task, config: NFeConfig) -> str:
    codigo_tributacao = config.default_codigo_tributacao_iss
    for item in task.items.filter(service__isnull=False).select_related('service'):
        if item.service and item.service.codigo_tributacao_nacional_iss:
            codigo_tributacao = item.service.codigo_tributacao_nacional_iss
            break
    return codigo_tributacao or ''


def _resolve_codigo_tributacao_municipal_iss_task(task, config: NFeConfig) -> str:
    """cTribMun — código de tributação MUNICIPAL do ISS, distinto do nacional
    (cTribNac/codigo_tributacao_nacional_iss). Tabela própria da prefeitura, só
    exigida por município que a publica. Goiânia não usa: uma NFSe real emitida
    manualmente pelo Portal Nacional (mesmo CNPJ) foi autorizada (cStat=100) com
    <cServ><cTribNac>...</cTribNac><xDescServ>...</xDescServ></cServ> — sem cTribMun
    no meio. Mantido resolvível (por serviço/config) só para o dia em que isso for
    necessário; build_nfse_nacional_payload não envia mais esse campo."""
    codigo_tributacao = config.default_codigo_tributacao_municipal_iss
    for item in task.items.filter(service__isnull=False).select_related('service'):
        if item.service and item.service.codigo_tributacao_municipal_iss:
            codigo_tributacao = item.service.codigo_tributacao_municipal_iss
            break
    return codigo_tributacao or ''


def _resolve_codigo_indicador_operacao_task(task, config: NFeConfig) -> str:
    """cIndOp — indicador de operação da Reforma Tributária (Anexo VIII do Comitê
    Gestor da NFS-e: correlação item LC 116 x NBS x cIndOp x cClassTrib). Para o
    item 07.02 (execução de obras/instalação e montagem — calhas), o Anexo VIII usa
    uniformemente '020201' (local do imóvel), independente da sub-atividade."""
    codigo = config.default_codigo_indicador_operacao
    for item in task.items.filter(service__isnull=False).select_related('service'):
        if item.service and item.service.codigo_indicador_operacao:
            codigo = item.service.codigo_indicador_operacao
            break
    return codigo or ''


def _resolve_codigo_nbs_task(task, config: NFeConfig) -> str:
    """cNBS — código da Nomenclatura Brasileira de Serviços (Anexo VIII). Diferente
    do cIndOp, não é uniforme por item LC 116: cada tipo específico de serviço tem
    seu próprio NBS (ex: 010530000 para telhados/coberturas/impermeabilização —
    calhas —, 010632000 para ventilação/exaustão — smoke). SEFAZ rejeita a emissão
    com o grupo IBS/CBS presente sem um NBS informado ('É obrigatório informar na
    DPS um item da NBS se for declarada qualquer informação de IBS/CBS')."""
    codigo = config.default_codigo_nbs
    for item in task.items.filter(service__isnull=False).select_related('service'):
        if item.service and item.service.codigo_nbs:
            codigo = item.service.codigo_nbs
            break
    return codigo or ''


# Subitens da lista de serviços (LC 116) para os quais a NFSe Nacional exige o
# "grupo de informações de obra" (construção civil) — formato do
# codigo_tributacao_nacional_iss é o subitem sem pontos (ex: '070201' = 07.02.01).
# Confirmado via erro real da SEFAZ: "O grupo de informações de obra é obrigatório
# quando o código de tributação nacional pertencer a um dos subitens 07.02.01,
# 07.02.02, 07.04.01, 07.05.01, 07.05.02, 07.06.01, 07.06.02, 07.07.01, 07.08.01,
# 07.17.01, 07.19.01, 14.14.03 e 14.14.04".
_OBRA_SUBITENS_TRIBUTACAO_NACIONAL = {
    '070201', '070202', '070401', '070501', '070502', '070601', '070602',
    '070701', '070801', '071701', '071901', '141403', '141404',
}

# codigo_opcao_simples_nacional (opSimpNac): 1 = Não optante, 2 = Optante MEI,
# 3 = Optante ME/EPP. RegimeTributario.choices: 1=SIMPLES_NACIONAL, 2=SIMPLES_EXCESSO
# (ainda optante do SN, só paga ICMS/ISS de excesso fora dele), 3=NORMAL, 4=MEI.
_OPCAO_SIMPLES_NACIONAL = {1: '3', 2: '3', 3: '1', 4: '2'}


def build_nfse_nacional_payload(task) -> dict:
    """Emite NFSe Nacional só pelos itens de SERVIÇO de uma etapa da OS (ServiceItem
    com `service` preenchido) — a parte de produto da mesma etapa vai em NFe/NFCe
    separada (build_nfe_or_nfce_payload_from_task), nunca no mesmo documento."""
    config = NFeConfig.load()
    service_order = task.service_order
    client = service_order.client_property.client
    prop = service_order.client_property

    codigo_tributacao = _resolve_codigo_tributacao_iss_task(task, config)
    codigo_indicador_operacao = _resolve_codigo_indicador_operacao_task(task, config)
    codigo_nbs = _resolve_codigo_nbs_task(task, config)
    split = _task_value_split(task)

    problems = _validate_client_for_emission(client, require_address=False)
    if split['service_gross'] <= 0:
        problems.append('Esta etapa não tem itens de serviço faturáveis — nada para emitir em NFSe.')
    if not prop.ibge_code:
        problems.append(
            f'Imóvel do cliente "{client.display_name}" sem Código IBGE do Município cadastrado — '
            'edite o cadastro do imóvel antes de emitir.'
        )
    if not codigo_tributacao:
        problems.append(
            'Nenhum serviço faturado nesta etapa tem Código de Tributação Nacional do ISS, e não há '
            'um código padrão configurado em Integração Fiscal — cadastre um dos dois.'
        )
    if not config.default_ibs_cbs_situacao_tributaria or not config.default_ibs_cbs_classificacao_tributaria:
        problems.append(
            'A NFSe Nacional agora exige o grupo IBS/CBS (Reforma Tributária) — configure "CST IBS/CBS" e '
            '"Classificação Tributária IBS/CBS" em Integração Fiscal (confirme os códigos com seu contador).'
        )
    if not codigo_indicador_operacao:
        problems.append(
            'Nenhum serviço faturado nesta etapa tem Código Indicador de Operação (cIndOp), e não há um '
            'código padrão configurado em Integração Fiscal — cadastre um dos dois.'
        )
    if not codigo_nbs:
        problems.append(
            'Nenhum serviço faturado nesta etapa tem Código NBS, e não há um código padrão configurado '
            'em Integração Fiscal — a NFSe Nacional exige NBS sempre que o grupo IBS/CBS é informado '
            '(cadastre um dos dois; consulte o Anexo VIII do Comitê Gestor da NFS-e).'
        )
    if problems:
        raise FiscalValidationError(problems)

    payload = {
        'data_emissao': _now_iso(),
        'data_competencia': _data_competencia_task(task),
        # finNFSe (obrigatório): 0 = DPS normal — sem isso a Focus gera XML fora de
        # ordem e a validação rejeita bem mais adiante ("valores: Expected is finNFSe").
        'finalidade_emissao': 0,
        'codigo_municipio_emissora': config.codigo_municipio_ibge,
        'cnpj_prestador': _clean_doc(config.cnpj),
        # razao_social_prestador (xNome do prestador): mesma exigência que o nome do
        # tomador — sem isso a SEFAZ rejeita com "email not expected, expected CAEPF/IM"
        # (o parser espera o nome logo após o documento, antes de endereço/contato).
        'razao_social_prestador': config.razao_social,
        'codigo_municipio_prestador': config.codigo_municipio_ibge,
        'logradouro_prestador': config.logradouro,
        'numero_prestador': config.numero,
        'complemento_prestador': config.complemento or '',
        'bairro_prestador': config.bairro,
        'cep_prestador': _clean_doc(config.cep),
        # codigo_opcao_simples_nacional (opSimpNac): 1 = Não optante, 2 = Optante MEI,
        # 3 = Optante ME/EPP. Confirmado contra NFSe real autorizada (mesmo CNPJ,
        # optante Simples Nacional não-MEI) que veio com opSimpNac=3, não 1.
        'codigo_opcao_simples_nacional': _OPCAO_SIMPLES_NACIONAL.get(config.regime_tributario, '1'),
        'descricao_servico': (service_order.description or f'OS #{service_order.number} — {task.get_task_type_display()}')[:2000],
        'codigo_tributacao_nacional_iss': codigo_tributacao,
        'codigo_municipio_prestacao': prop.ibge_code or config.codigo_municipio_ibge,
        'valor_servico': _money(split['service_net']),
        # tributacao_iss: 1 = Operação tributável (exigível) — padrão para prestação normal.
        'tributacao_iss': 1,
        # tipo_retencao_iss: 1 = Não retido — o grupo tribMun exige pelo menos um dos
        # campos de situação especial (retenção/imunidade/suspensão/benefício); para a
        # operação padrão (sem nenhuma dessas condições), enviamos "não retido".
        'tipo_retencao_iss': 1,
        # Reforma Tributária (obrigatório na NFSe Nacional) — vem da config, sem valor chutado.
        'ibs_cbs_situacao_tributaria': config.default_ibs_cbs_situacao_tributaria,
        'ibs_cbs_classificacao_tributaria': config.default_ibs_cbs_classificacao_tributaria,
        # codigo_nbs (cNBS): SEFAZ rejeitava com "É obrigatório informar na DPS um item
        # da NBS se for declarada qualquer informação de IBS/CBS" — como o grupo
        # IBS/CBS acima é sempre enviado, o NBS também precisa ser sempre enviado.
        # String (não int): o schema exige exatamente 9 dígitos ('[0-9]{9}') incluindo
        # zero à esquerda (ex: '010530000') — int() descartava esse zero e a SEFAZ
        # rejeitava com "cNBS: value '10530000' not accepted by pattern '[0-9]{9}'".
        'codigo_nbs': codigo_nbs.zfill(9),
        # consumidor_final (indFinal, Reforma Tributária, obrigatório): 1 = Sim. O tomador
        # da instalação/manutenção de calhas sempre consome o serviço diretamente — nunca
        # revende a instalação como insumo de outra operação — por isso é fixo em 1.
        'consumidor_final': 1,
        # codigo_indicador_operacao (cIndOp, Reforma Tributária, obrigatório): tabela do
        # Anexo VIII do Comitê Gestor da NFS-e. SEFAZ rejeitava com "valores: Expected is
        # (cIndOp)" — indFinal sozinho não satisfaz, os dois são exigidos juntos.
        'codigo_indicador_operacao': codigo_indicador_operacao,
        # regime_especial_tributacao (regEspTrib): SEMPRE obrigatório, independente do
        # regime tributário do prestador (0 = Nenhum) — SEFAZ rejeitava com "regTrib:
        # Missing child element(s). Expected is (regEspTrib)" mesmo já enviando
        # regime_tributario_simples_nacional; os dois campos não são alternativos, são
        # cumulativos quando o prestador é optante pelo Simples Nacional.
        'regime_especial_tributacao': 0,
        # indicador_destinatario (indDest, Reforma Tributária, obrigatório): 0 = o
        # destinatário da operação (para fins de local de incidência do IBS/CBS) é o
        # mesmo que o tomador do serviço. Para instalação/manutenção de calhas o
        # tomador sempre recebe o serviço em seu próprio imóvel — nunca em nome de
        # terceiro — por isso é fixo em 0. SEFAZ rejeitava com "valores: Expected is
        # one of (tpOper, gRefNFSe, tpEnteGov, indDest)" por faltar.
        'indicador_destinatario': 0,
        'razao_social_tomador': client.display_name,
        # indTotTrib: grupo totTrib (Lei 12.741/2012, "Lei da Transparência") é
        # obrigatório — SEFAZ rejeitava com "trib: Missing child element(s). Expected
        # is one of (tribFed, totTrib)". 0 = emitente opta por não informar valor
        # estimado de tributos (confirmado contra NFSe real autorizada com
        # <totTrib><indTotTrib>0</indTotTrib></totTrib>). NOME DO CAMPO INCERTO: a
        # doc da Focus deu duas respostas diferentes em consultas separadas
        # ('indicador_total_tributos' e 'indicador_total_tributacao') — testando essa
        # variante agora; se não resolver, confirmar o nome certo direto com o
        # suporte da Focus em vez de continuar adivinhando.
        'indicador_total_tributacao': 0,
    }

    if config.regime_tributario in (1, 2):
        # regime_tributario_simples_nacional (regApTribSN): só se aplica a optante pelo
        # Simples Nacional. 1 = tributos federais e municipais recolhidos via SN — caso
        # padrão para prestador optante sem regra municipal que exija ISS fora do SN.
        payload['regime_tributario_simples_nacional'] = 1

    # inscricao_municipal_prestador: voltou a ser enviada. Histórico: chegamos a
    # omitir por causa de "Inscrição Municipal do prestador do serviço não
    # encontrada na base de dados do município" — mas isso aconteceu com
    # NFeConfig.environment=SANDBOX (homologação não replica o cadastro real dos
    # contribuintes). Depois de trocar pra produção, uma NFSe real emitida
    # manualmente pelo Portal Nacional com o mesmo CNPJ veio autorizada (cStat=100)
    # com <prest><IM>5468736</IM></prest> presente — confirma que a IM é válida e
    # deve ser enviada em produção. Se o erro de "IM não encontrada" voltar em
    # produção, o problema é outro (não a IM em si).
    if config.inscricao_municipal:
        payload['inscricao_municipal_prestador'] = config.inscricao_municipal

    document = _clean_doc(client.document)
    if client.client_type == 'PJ':
        payload['cnpj_tomador'] = document
    else:
        payload['cpf_tomador'] = document

    if prop:
        payload.update({
            'logradouro_tomador': prop.address,
            'numero_tomador': prop.number or 'S/N',
            'complemento_tomador': prop.complement or '',
            'bairro_tomador': prop.neighborhood,
            'codigo_municipio_tomador': prop.ibge_code or '',
            'cep_tomador': _clean_doc(prop.cep),
        })

    # grupo de informações de obra: exigido pela SEFAZ para os subitens em
    # _OBRA_SUBITENS_TRIBUTACAO_NACIONAL (ver comentário acima da função). Não
    # temos Inscrição Imobiliária nem CNO/CEI cadastrados (instalação de calha em
    # imóvel já construído não é uma "obra" registrada no INSS) — testando primeiro
    # só com o endereço do imóvel, que já temos, sem identificador da obra. Se a
    # SEFAZ continuar exigindo identificação (CNO/CEI/inscrição imobiliária), será
    # necessário cadastrar esse dado no imóvel do cliente.
    if codigo_tributacao in _OBRA_SUBITENS_TRIBUTACAO_NACIONAL and prop:
        cep_obra_digits = _clean_doc(prop.cep)
        payload.update({
            'logradouro_obra': prop.address,
            'numero_obra': prop.number or 'S/N',
            'complemento_obra': prop.complement or '',
            'bairro_obra': prop.neighborhood,
        })
        if cep_obra_digits:
            payload['cep_obra'] = int(cep_obra_digits)

    return payload
