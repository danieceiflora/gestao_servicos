import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseFiscalGateway, EmpresaData, EmpresaResult, EmissionResult

logger = logging.getLogger(__name__)

SANDBOX_URL = 'https://homologacao.focusnfe.com.br/v2'
PRODUCTION_URL = 'https://api.focusnfe.com.br/v2'

# (connect_timeout, read_timeout)
_TIMEOUT = (10, 60)


class FocusNFeError(Exception):
    """Erro estruturado da Focus — preserva codigo/mensagem/correcao para exibir
    uma mensagem acionável na UI, em vez de só o texto bruto da resposta."""

    def __init__(self, status_code, codigo='', mensagem='', correcao=''):
        self.status_code = status_code
        self.codigo = codigo
        self.mensagem = mensagem or 'Erro desconhecido na Focus NFe'
        self.correcao = correcao
        super().__init__(f'FocusNFe {status_code}: {self.mensagem}')


class FocusNFeGateway(BaseFiscalGateway):
    """Cliente HTTP para a API da FocusNFe. Cada instância opera sobre um único
    ambiente/token — para emitir em produção e homologação simultaneamente,
    crie duas instâncias."""

    def __init__(self, token: str, environment: str = 'SANDBOX'):
        self.token = token
        self.base_url = SANDBOX_URL if environment == 'SANDBOX' else PRODUCTION_URL
        # Domínio para servir arquivos (DANFE/XML) — mesmo host da API, sem o /v2.
        self.file_base_url = self.base_url[:-len('/v2')] if self.base_url.endswith('/v2') else self.base_url

    def _full_url(self, path: str) -> str:
        """caminho_danfe/caminho_xml_nota_fiscal vêm da Focus como caminho RELATIVO
        (ex: '/arquivos_development/.../DANFEs/....pdf'), não URL completa. Sem
        prefixar o domínio da Focus, o navegador resolve o link contra a origem da
        página atual (ex: localhost:8000) e dá 404."""
        if not path:
            return ''
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return f"{self.file_base_url}/{path.lstrip('/')}"

    def _auth(self):
        return HTTPBasicAuth(self.token, '')

    def _raise_for_status(self, resp):
        if resp.ok:
            return
        body_text = resp.text[:1000]
        logger.error('FocusNFe API error %s on %s %s: %s', resp.status_code, resp.request.method, resp.url, body_text)
        codigo = mensagem = correcao = ''
        try:
            parsed = resp.json()
            if isinstance(parsed, list) and parsed:
                # Respostas de erro de emissão vêm como array de {codigo, mensagem, correcao}
                first = parsed[0]
                codigo = first.get('codigo', '')
                mensagem = first.get('mensagem', '')
                correcao = first.get('correcao', '')
            elif isinstance(parsed, dict):
                codigo = str(parsed.get('codigo', ''))
                mensagem = parsed.get('mensagem', '') or parsed.get('erro', '') or body_text
                correcao = parsed.get('correcao', '')
        except Exception:
            mensagem = body_text
        raise FocusNFeError(resp.status_code, codigo, mensagem, correcao)

    def _get(self, path, params=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.get(url, auth=self._auth(), params=params, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path, data=None, params=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.post(url, auth=self._auth(), json=data, params=params, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _put(self, path, data=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.put(url, auth=self._auth(), json=data, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _delete(self, path, data=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.delete(url, auth=self._auth(), json=data, timeout=_TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    # --- Empresas ---

    def _empresa_payload(self, data: EmpresaData) -> dict:
        payload = {
            'nome': data.razao_social,
            'cnpj': data.cnpj,
            'inscricao_estadual': data.inscricao_estadual,
            'inscricao_municipal': data.inscricao_municipal,
            'regime_tributario': data.regime_tributario,
            'logradouro': data.logradouro,
            'numero': data.numero,
            'complemento': data.complemento,
            'bairro': data.bairro,
            'municipio': data.municipio,
            'uf': data.uf,
            'cep': data.cep,
            'habilita_nfe': data.habilita_nfe,
            'habilita_nfce': data.habilita_nfce,
            'habilita_nfsen_producao': data.habilita_nfse,
            'habilita_nfsen_homologacao': data.habilita_nfse,
        }
        if data.certificado_base64:
            payload['arquivo_certificado_base64'] = data.certificado_base64
            payload['senha_certificado'] = data.certificado_senha
        return payload

    def _empresa_result(self, raw: dict) -> EmpresaResult:
        return EmpresaResult(
            focus_id=raw.get('id'),
            token_producao=raw.get('token_producao', ''),
            token_homologacao=raw.get('token_homologacao', ''),
            certificado_valido_ate=raw.get('certificado_valido_ate'),
            raw=raw,
        )

    def create_empresa(self, data: EmpresaData) -> EmpresaResult:
        raw = self._post('empresas', self._empresa_payload(data))
        return self._empresa_result(raw)

    def update_empresa(self, focus_id: int, data: EmpresaData) -> EmpresaResult:
        raw = self._put(f'empresas/{focus_id}', self._empresa_payload(data))
        return self._empresa_result(raw)

    # --- Emissão ---

    def _emission_result(self, ref: str, raw: dict) -> EmissionResult:
        return EmissionResult(
            ref=ref,
            status=raw.get('status', ''),
            numero=str(raw.get('numero', '') or ''),
            serie=str(raw.get('serie', '') or ''),
            chave_acesso=raw.get('chave_nfe', ''),
            codigo_verificacao=raw.get('codigo_verificacao', ''),
            status_sefaz=str(raw.get('status_sefaz', '') or ''),
            mensagem_sefaz=raw.get('mensagem_sefaz', ''),
            xml_url=self._full_url(raw.get('caminho_xml_nota_fiscal', '') or raw.get('url', '')),
            pdf_url=self._full_url(raw.get('caminho_danfe', '') or raw.get('url_danfse', '')),
            qrcode_url=self._full_url(raw.get('qrcode_url', '')),
            error_details=raw.get('erros'),
            raw=raw,
        )

    def emit_nfe(self, ref: str, payload: dict) -> EmissionResult:
        raw = self._post('nfe', payload, params={'ref': ref})
        return self._emission_result(ref, raw)

    def emit_nfce(self, ref: str, payload: dict) -> EmissionResult:
        raw = self._post('nfce', payload, params={'ref': ref})
        return self._emission_result(ref, raw)

    def emit_nfse(self, ref: str, payload: dict) -> EmissionResult:
        raw = self._post('nfsen', payload, params={'ref': ref})
        return self._emission_result(ref, raw)

    def consultar_nfe(self, ref: str) -> EmissionResult:
        raw = self._get(f'nfe/{ref}')
        return self._emission_result(ref, raw)

    def consultar_nfce(self, ref: str) -> EmissionResult:
        raw = self._get(f'nfce/{ref}')
        return self._emission_result(ref, raw)

    def consultar_nfse(self, ref: str) -> EmissionResult:
        raw = self._get(f'nfse/{ref}')
        return self._emission_result(ref, raw)

    # --- Cancelamento ---

    def cancelar_nfe(self, ref: str, justificativa: str) -> EmissionResult:
        raw = self._delete(f'nfe/{ref}', {'justificativa': justificativa})
        return self._emission_result(ref, raw)

    def cancelar_nfce(self, ref: str, justificativa: str) -> EmissionResult:
        raw = self._delete(f'nfce/{ref}', {'justificativa': justificativa})
        return self._emission_result(ref, raw)

    def cancelar_nfse(self, ref: str, justificativa: str) -> EmissionResult:
        raw = self._delete(f'nfse/{ref}', {'justificativa': justificativa})
        return self._emission_result(ref, raw)

    # --- Webhooks ---

    def create_webhook(self, event: str, url: str, authorization: str, authorization_header: str) -> dict:
        return self._post('hooks', {
            'event': event,
            'url': url,
            'authorization': authorization,
            'authorization_header': authorization_header,
        })
