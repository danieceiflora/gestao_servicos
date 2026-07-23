import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SANDBOX_URL = 'https://api-sandbox.asaas.com/v3'
PRODUCTION_URL = 'https://api.asaas.com/v3'

# (connect_timeout, read_timeout)
_TIMEOUT = (10, 60)


@dataclass
class InvoiceTaxes:
    """taxes (InvoiceTaxesRequestDTO) — alíquotas informadas na própria nota, ao
    contrário da Focus (onde o regime tributário vem do cadastro da empresa).

    nbs_code/tax_situation_code/tax_classification_code/operation_indicator_code:
    grupo IBS/CBS da Reforma Tributária — mesmos conceitos de
    codigo_nbs/ibs_cbs_situacao_tributaria/ibs_cbs_classificacao_tributaria/
    codigo_indicador_operacao já usados no payload da Focus (fiscal/builders.py),
    só que aqui vão DENTRO de `taxes`, por nota — não é config de conta (ver
    NFeConfig.default_codigo_nbs etc., reaproveitados como fonte). Descobrimos isso
    do jeito difícil: a prefeitura rejeitou por falta de NBS mesmo com
    GET/POST /fiscalInfo configurado — o `taxes.nbsCode` da resposta de um invoice
    real veio `null`, confirmando que fiscalInfo não propaga automaticamente."""
    retain_iss: bool = False
    iss: Decimal = field(default_factory=lambda: Decimal('0'))
    pis: Decimal = field(default_factory=lambda: Decimal('0'))
    cofins: Decimal = field(default_factory=lambda: Decimal('0'))
    csll: Decimal = field(default_factory=lambda: Decimal('0'))
    inss: Decimal = field(default_factory=lambda: Decimal('0'))
    ir: Decimal = field(default_factory=lambda: Decimal('0'))
    nbs_code: str = ''
    tax_situation_code: str = ''
    tax_classification_code: str = ''
    operation_indicator_code: str = ''


@dataclass
class InvoiceData:
    service_description: str
    value: Decimal
    effective_date: date
    municipal_service_name: str
    taxes: InvoiceTaxes
    observations: str = ''
    deductions: Decimal = field(default_factory=lambda: Decimal('0'))
    # Pelo menos um entre payment/installment/customer é obrigatório (é o que diz
    # a quem/qual cobrança a nota se refere) — validado em emit_invoice().
    payment: str = ''
    installment: str = ''
    customer: str = ''
    external_reference: str = ''
    municipal_service_id: str = ''
    municipal_service_code: str = ''
    update_payment: bool = False


@dataclass
class InvoiceResult:
    external_id: str
    status: str  # SCHEDULED | AUTHORIZED | PROCESSING_CANCELLATION | CANCELED | CANCELLATION_DENIED | ERROR
    status_description: str = ''
    pdf_url: str = ''
    xml_url: str = ''
    rps_serie: str = ''
    rps_number: str = ''
    number: str = ''
    validation_code: str = ''
    raw: dict = field(default_factory=dict)


class AsaasInvoiceGateway:
    """Cliente HTTP para emissão de NFSe via Asaas.

    Modelo diferente da Focus: aqui não existe conceito de "empresa"/certificado por
    chamada — a configuração fiscal (município, regime, série de RPS) fica associada
    à própria conta Asaas, via endpoint /fiscalInfo (fora de escopo por enquanto).
    Esta classe cobre só a emissão da nota em si.

    Emitir uma nota é, na prática, 2 passos:
      1. emit_invoice() — POST /v3/invoices ("agendar nota fiscal"). Se
         effective_date for hoje, o Asaas normalmente já processa a emissão no
         mesmo dia; se for uma data futura, a nota fica SCHEDULED até lá.
      2. authorize_invoice() — POST /v3/invoices/{id}/authorize ("emitir uma nota
         fiscal": https://docs.asaas.com/reference/emitir-uma-nota-fiscal),
         necessário só para antecipar a emissão de uma nota que ficou SCHEDULED.
    """

    def __init__(self):
        env = getattr(settings, 'ASAAS_ENVIRONMENT', 'SANDBOX')
        self.api_key = getattr(settings, 'ASAAS_API_KEY', '')
        self.base_url = SANDBOX_URL if env == 'SANDBOX' else PRODUCTION_URL

    def _headers(self):
        return {
            'Content-Type': 'application/json',
            'access_token': self.api_key,
        }

    def _raise_for_status(self, resp):
        if resp.ok:
            return
        body = resp.text[:1000]
        logger.error('Asaas Invoices API error %s on %s %s: %s', resp.status_code, resp.request.method, resp.url, body)
        detail = body
        try:
            parsed = resp.json()
            errors = parsed.get('errors', [])
            msgs = [e.get('description', '') for e in errors if e.get('description')]
            if msgs:
                detail = '; '.join(msgs)
        except Exception:
            pass
        raise Exception(f'Asaas {resp.status_code}: {detail}')

    def _get(self, path, params=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.get(url, headers=self._headers(), params=params, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path, data):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.post(url, headers=self._headers(), json=data, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _put(self, path, data):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.put(url, headers=self._headers(), json=data, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _clean_document(self, doc: str) -> str:
        import re
        return re.sub(r'\D', '', doc or '')

    def get_or_create_customer(self, name: str, document: str, email: str = '', address: dict = None) -> str:
        """Busca (por CPF/CNPJ) ou cria um cliente Asaas (conta master, mesma
        API key usada por pagamentos.gateways.asaas.AsaasGateway — clientes Asaas
        são por conta, não por gateway/produto, daí o mesmo cliente valer tanto
        para cobrança quanto para nota fiscal).

        `address` (opcional): dict com as chaves address/addressNumber/complement/
        province/postalCode. Sempre que informado, é enviado via PUT mesmo para um
        cliente já existente — um cliente criado antes por aqui ou pelo módulo de
        cobranças (pagamentos.gateways.asaas) nunca manda endereço, e a Asaas rejeita
        a emissão de NFSe com "endereço incompleto/CEP inválido" se o cadastro do
        cliente ficar sem CEP."""
        doc_clean = self._clean_document(document)
        customer_id = None
        if doc_clean:
            result = self._get('customers', params={'cpfCnpj': doc_clean, 'limit': 1})
            if result.get('data'):
                customer_id = result['data'][0]['id']

        payload = {'name': name}
        if email:
            payload['email'] = email
        if doc_clean:
            payload['cpfCnpj'] = doc_clean
        if address:
            payload.update({k: v for k, v in address.items() if v})

        if customer_id:
            self._put(f'customers/{customer_id}', payload)
            return customer_id

        created = self._post('customers', payload)
        return created['id']

    def _invoice_payload(self, data: InvoiceData) -> dict:
        if not (data.payment or data.installment or data.customer):
            raise ValueError('InvoiceData precisa de payment, installment ou customer preenchido.')

        payload = {
            'serviceDescription': data.service_description,
            'observations': data.observations,
            'value': float(data.value),
            'deductions': float(data.deductions),
            'effectiveDate': data.effective_date.strftime('%Y-%m-%d'),
            'municipalServiceName': data.municipal_service_name,
            'taxes': {
                'retainIss': data.taxes.retain_iss,
                'iss': float(data.taxes.iss),
                'pis': float(data.taxes.pis),
                'cofins': float(data.taxes.cofins),
                'csll': float(data.taxes.csll),
                'inss': float(data.taxes.inss),
                'ir': float(data.taxes.ir),
            },
        }
        # Grupo IBS/CBS (Reforma Tributária) — vai dentro de `taxes`, por nota.
        # Goiânia passou a rejeitar sem isso (cNBS obrigatório assim que o grupo
        # IBS/CBS é declarado); manda só o que estiver preenchido.
        if data.taxes.nbs_code:
            payload['taxes']['nbsCode'] = data.taxes.nbs_code
        if data.taxes.tax_situation_code:
            payload['taxes']['taxSituationCode'] = data.taxes.tax_situation_code
        if data.taxes.tax_classification_code:
            payload['taxes']['taxClassificationCode'] = data.taxes.tax_classification_code
        if data.taxes.operation_indicator_code:
            payload['taxes']['operationIndicatorCode'] = data.taxes.operation_indicator_code
        if data.payment:
            payload['payment'] = data.payment
        if data.installment:
            payload['installment'] = data.installment
        if data.customer:
            payload['customer'] = data.customer
        if data.external_reference:
            payload['externalReference'] = data.external_reference
        if data.municipal_service_id:
            payload['municipalServiceId'] = data.municipal_service_id
        if data.municipal_service_code:
            payload['municipalServiceCode'] = data.municipal_service_code
        if data.update_payment:
            payload['updatePayment'] = data.update_payment
        return payload

    def _invoice_result(self, raw: dict) -> InvoiceResult:
        # raw.get(key, '') só cai no default quando a chave está AUSENTE — o Asaas manda
        # essas chaves presentes com valor `null` enquanto a nota está SCHEDULED/PROCESSING
        # (pdfUrl, validationCode etc. só existem depois de autorizada), então `.get(x, '')`
        # sozinho deixa passar None e quebra o NOT NULL do banco. `or ''` cobre os dois casos.
        return InvoiceResult(
            external_id=raw.get('id') or '',
            status=raw.get('status') or '',
            status_description=raw.get('statusDescription') or '',
            pdf_url=raw.get('pdfUrl') or '',
            xml_url=raw.get('xmlUrl') or '',
            rps_serie=str(raw.get('rpsSerie') or ''),
            rps_number=str(raw.get('rpsNumber') or ''),
            number=str(raw.get('number') or ''),
            validation_code=raw.get('validationCode') or '',
            raw=raw,
        )

    def emit_invoice(self, data: InvoiceData) -> InvoiceResult:
        """POST /v3/invoices — agenda/emite a NFSe."""
        raw = self._post('invoices', self._invoice_payload(data))
        return self._invoice_result(raw)

    def authorize_invoice(self, invoice_id: str) -> InvoiceResult:
        """POST /v3/invoices/{id}/authorize — antecipa a emissão de uma nota
        agendada (status SCHEDULED) para agora."""
        raw = self._post(f'invoices/{invoice_id}/authorize', {})
        return self._invoice_result(raw)

    def get_invoice(self, invoice_id: str) -> InvoiceResult:
        """GET /v3/invoices/{id} — consulta status/artefatos (pdf/xml) da nota."""
        raw = self._get(f'invoices/{invoice_id}')
        return self._invoice_result(raw)

    def cancel_invoice(self, invoice_id: str) -> InvoiceResult:
        """POST /v3/invoices/{id}/cancel — solicita o cancelamento da nota. Nem
        todo município permite cancelamento automático via integração: o status
        pode ficar em PROCESSING_CANCELLATION até a prefeitura responder, ou
        voltar como CANCELLATION_DENIED."""
        raw = self._post(f'invoices/{invoice_id}/cancel', {})
        return self._invoice_result(raw)

    def list_municipal_services(self, description: str = '', limit: int = 20) -> list:
        """GET /v3/fiscalInfo/services — catálogo de serviços municipais já
        homologados pela Asaas (id + description + issTax). A doc recomenda
        emitir com `municipalServiceId` em vez de digitar nome/código à mão:
        texto digitado precisa bater exatamente com o cadastrado lá, e não tem
        como validar isso sem consultar o catálogo. Retorna a lista de
        dicts (id/description/issTax) já achatada — sem paginação (uso é
        alimentar um campo de busca, não listar tudo)."""
        params = {'limit': limit}
        if description:
            params['description'] = description
        raw = self._get('fiscalInfo/services', params=params)
        return raw.get('data', [])

    # Campos aceitos por POST /v3/fiscalInfo (configuração fiscal da CONTA, não da
    # nota) — usado só pra filtrar o que devolve em get_fiscal_info() antes de
    # remandar num update_fiscal_info(): a resposta do GET também traz campos
    # derivados/somente-leitura (object, passwordSent, accessTokenSent,
    # certificateSent) que não são inputs válidos do POST.
    _FISCAL_INFO_FIELDS = (
        'email', 'simplesNacional', 'municipalInscription', 'culturalProjectsPromoter',
        'cnae', 'specialTaxRegime', 'serviceListItem', 'nbsCode', 'rpsSerie', 'rpsNumber',
        'loteNumber', 'nationalPortalTaxCalculationRegime',
    )

    def get_fiscal_info(self) -> dict:
        """GET /v3/fiscalInfo — configuração fiscal da conta (CNAE, regime, RPS,
        NBS etc.) — é preenchida uma vez pra conta toda, não por nota."""
        return self._get('fiscalInfo')

    def update_fiscal_info(self, **fields) -> dict:
        """POST /v3/fiscalInfo — cria/atualiza a config fiscal da conta. Busca a
        config atual primeiro e sobrepõe só os campos passados: a Asaas não
        documenta um PATCH parcial, e reenviar um payload sem os campos já
        configurados por lá (CNAE, inscrição municipal, RPS...) arriscaria
        apagá-los sem querer."""
        current = self.get_fiscal_info()
        payload = {k: current.get(k) for k in self._FISCAL_INFO_FIELDS if current.get(k) is not None}
        payload.update({k: v for k, v in fields.items() if v not in (None, '')})
        return self._post('fiscalInfo', payload)
