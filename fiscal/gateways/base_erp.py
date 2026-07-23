import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SANDBOX_URL = 'https://api-sandbox.baseerp.com.br/api/v1'
PRODUCTION_URL = 'https://api.baseerp.com.br/api/v1'

# (connect_timeout, read_timeout)
_TIMEOUT = (10, 60)

# Nome do banco/conta usado para lançar o recebível de cada pedido de venda —
# resolvido por NOME (não id) porque sandbox e produção são contas separadas
# com ids numéricos diferentes; cadastre um banco com esse nome exato em cada
# ambiente no painel do Base ERP (Financeiro > Contas).
DEFAULT_BANK_NAME = 'CAIXA INTERNO'


class BaseERPGateway:
    """Cliente HTTP para o Base ERP (Nota Fiscal de Produto — NF-e/NFC-e).

    Produto separado do Asaas Invoices (NFSe): mesma conta Asaas, mas API,
    autenticação e base URL próprias. A config fiscal da empresa (inscrição
    estadual, regime tributário, certificado A1/A3, grupo de impostos) é feita
    uma única vez no painel web do Base ERP — não existe endpoint para isso,
    então não tem equivalente ao `update_fiscal_info` da Asaas por aqui.

    Emitir uma NF-e é, na prática, 3 passos (ver fiscal/views.py quando
    implementado): garantir cliente (`/customers`) e produto (`/products`) no
    Base — criando se não existirem —, criar o pedido de venda (`/salesOrders`)
    e só então chamar `/salesOrders/{id}/invoice`.
    """

    def __init__(self):
        env = getattr(settings, 'BASEERP_ENVIRONMENT', 'SANDBOX')
        self.api_key = getattr(settings, 'BASEERP_API_KEY', '')
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
        logger.error('Base ERP API error %s on %s %s: %s', resp.status_code, resp.request.method, resp.url, body)
        detail = body
        try:
            parsed = resp.json()
            errors = parsed.get('errors', [])
            msgs = [e.get('description', '') for e in errors if e.get('description')]
            if msgs:
                detail = '; '.join(msgs)
            elif parsed.get('message'):
                detail = parsed['message']
        except Exception:
            pass
        raise Exception(f'Base ERP {resp.status_code}: {detail}')

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

    def get_or_create_customer(self, name: str, document: str, email: str = '', address: dict = None,
                                tax_info: dict = None) -> int:
        """Busca (por CPF/CNPJ) ou cria um cliente no Base ERP. Retorna o `id`
        (inteiro) do cliente no Base — diferente do Asaas, aqui os ids são
        numéricos, não strings tipo `cus_...`.

        `address` (opcional): dict pronto para `billingAddress` (address/
        addressNumber/complement/province/cityName/stateAbbrev/postalCode/
        country). Só é enviado se vier preenchido — a CustomerInput não exige
        endereço para *criar* o cliente, mas se o objeto billingAddress for
        enviado, TODOS os seus campos (exceto complement) são obrigatórios; a
        validação de endereço completo antes de emitir NF-e fica a cargo do
        builder (fiscal/builders.py), não deste gateway.

        `tax_info` (opcional): dict pronto para `taxInformation`
        (typeOfTaxPayer/finalConsumer/simpleTax/stateInscription/
        municipalInscription/ruralProducer). Descoberto na prática (rejeição
        SEFAZ "9051 - Tipo do Contribuinte do seu cliente inválido"): sem isso
        a SEFAZ rejeita a nota — sempre enviado via PUT mesmo pra cliente já
        existente, porque um cliente criado antes daqui (ou pelo `pagamentos`)
        nunca tem esse grupo preenchido."""
        doc_clean = self._clean_document(document)
        customer_id = None
        if doc_clean:
            result = self._get('customers', params={'cpfCnpj': doc_clean, 'size': 1})
            content = result.get('content') or []
            if content:
                customer_id = content[0]['id']

        payload = {'name': name[:60], 'cpfCnpj': doc_clean}
        if email:
            payload['email'] = email[:60]
        if address:
            payload['billingAddress'] = address
        if tax_info:
            payload['taxInformation'] = tax_info

        if customer_id:
            self._put(f'customers/{customer_id}', payload)
            return customer_id

        created = self._post('customers', payload)
        return created['id']

    def get_or_create_product(self, code: str, name: str, ncm: str, unit: str,
                               barcode: str = '', sale_price=None, cclass_trib: str = '') -> int:
        """Busca (por `code`) ou cria um produto no Base ERP. Retorna o `id`
        (inteiro) do produto no Base.

        Ao contrário do cliente, o produto NÃO é atualizado se já existir — só
        retorna o id encontrado. Preço/NCM podem mudar no nosso cadastro sem
        que isso deva alterar retroativamente um produto já usado em notas
        emitidas; se precisar propagar mudança, use `update_product` (ainda
        não implementado)."""
        result = self._get('products', params={'code': code, 'size': 1})
        content = result.get('content') or []
        if content:
            return content[0]['id']

        payload = {
            'code': code[:60],
            'name': name[:120],
            'ncm': ncm,
            'unit': unit,
        }
        if barcode:
            payload['barcode'] = barcode
        if sale_price is not None:
            payload['salePrice'] = float(sale_price)
        if cclass_trib:
            payload['cClassTrib'] = cclass_trib

        created = self._post('products', payload)
        return created['id']

    def get_bank_id_by_name(self, name: str = DEFAULT_BANK_NAME) -> int:
        """GET /api/v1/banks?name=... — resolve o id do banco pelo nome, em vez
        de hardcodar um id numérico (sandbox e produção são contas separadas,
        com ids diferentes para o mesmo banco/nome). Levanta erro claro se não
        encontrar — precisa existir um banco com esse nome exato cadastrado no
        painel do Base ERP (Financeiro > Contas) em cada ambiente."""
        result = self._get('banks', params={'name': name, 'size': 1})
        content = result.get('content') or []
        if not content:
            raise Exception(
                f'Banco "{name}" não encontrado na conta Base ERP — cadastre um banco com esse nome '
                'exato no painel (Financeiro > Contas) antes de emitir.'
            )
        return content[0]['id']

    def create_sales_order(self, customer_id: int, items: list, issue_date, payments: list = None,
                            external_reference: str = '', observations: str = '') -> int:
        """POST /api/v1/salesOrders — cria o pedido de venda que serve de base
        para a emissão da NF-e/NFC-e. `items`: lista de dicts
        `{'productId': int, 'quantity': float, 'unitPrice': float}` (mais
        `cClassTrib` opcional).

        `payments`: lista de dicts `{'bankId': int, 'billingType': str,
        'dueDate': str, 'value': float}` — descoberto na prática que é
        OBRIGATÓRIO (a API rejeita com "Cobrança não pode ser nula" sem isso),
        apesar de `orderPayments` não constar como campo obrigatório no schema
        documentado. Sem pelo menos uma cobrança, o Base ERP não sabe lançar o
        recebível do pedido nas Contas a Receber internas dele.

        Retorna o `id` do pedido criado."""
        payload = {
            'customerId': customer_id,
            'issueDate': issue_date.strftime('%Y-%m-%d'),
            'orderItems': items,
        }
        if payments:
            payload['orderPayments'] = payments
        if external_reference:
            payload['externalReference'] = external_reference[:255]
        if observations:
            payload['observations'] = observations[:255]

        created = self._post('salesOrders', payload)
        return created['id']

    def emit_invoice(self, sales_order_id: int, invoice_type: str = '55') -> dict:
        """POST /api/v1/salesOrders/{id}/invoice — emite a nota fiscal do
        pedido. `invoice_type`: '55' (NF-e) ou '65' (NFC-e). A emissão é
        assíncrona: a resposta traz `invoiceStatus` inicial (ex: PENDENTE,
        PROCESSANDO) — consultar `get_sales_order` depois para o status final
        (EMITIDA/REJEITADA/...)."""
        return self._post(f'salesOrders/{sales_order_id}/invoice', {'type': invoice_type})

    def get_sales_order(self, sales_order_id: int) -> dict:
        """GET /api/v1/salesOrders/{id} — consulta o pedido, incluindo
        invoiceId/invoiceNumber/invoiceStatus depois de emitir."""
        return self._get(f'salesOrders/{sales_order_id}')

    def cancel_invoice(self, sales_order_id: int, reason: str) -> dict:
        """PUT /api/v1/salesOrders/{id}/invoiceCancel — solicita o cancelamento
        da nota do pedido. `reason` precisa ter pelo menos 15 caracteres
        (exigido pelo schema — CancelInvoiceInputDto)."""
        return self._put(f'salesOrders/{sales_order_id}/invoiceCancel', {'reason': reason})
