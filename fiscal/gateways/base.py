from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class EmpresaData:
    razao_social: str
    cnpj: str
    inscricao_estadual: str
    inscricao_municipal: str
    regime_tributario: int
    logradouro: str
    numero: str
    complemento: str
    bairro: str
    municipio: str
    codigo_municipio_ibge: str
    uf: str
    cep: str
    habilita_nfe: bool = False
    habilita_nfce: bool = False
    habilita_nfse: bool = False
    certificado_base64: str = ''
    certificado_senha: str = ''


@dataclass
class EmpresaResult:
    focus_id: int
    token_producao: str
    token_homologacao: str
    certificado_valido_ate: Optional[object] = None
    raw: dict = field(default_factory=dict)


@dataclass
class EmissionResult:
    ref: str
    status: str  # 'processando_autorizacao' | 'autorizado' | 'erro_autorizacao' | 'cancelado'
    numero: str = ''
    serie: str = ''
    chave_acesso: str = ''
    codigo_verificacao: str = ''
    status_sefaz: str = ''
    mensagem_sefaz: str = ''
    xml_url: str = ''
    pdf_url: str = ''
    qrcode_url: str = ''
    error_details: Optional[list] = None
    raw: dict = field(default_factory=dict)


class BaseFiscalGateway(ABC):

    @abstractmethod
    def create_empresa(self, data: EmpresaData) -> EmpresaResult:
        ...

    @abstractmethod
    def update_empresa(self, focus_id: int, data: EmpresaData) -> EmpresaResult:
        ...

    @abstractmethod
    def emit_nfe(self, ref: str, payload: dict) -> EmissionResult:
        ...

    @abstractmethod
    def emit_nfce(self, ref: str, payload: dict) -> EmissionResult:
        ...

    @abstractmethod
    def emit_nfse(self, ref: str, payload: dict) -> EmissionResult:
        ...

    @abstractmethod
    def consultar_nfe(self, ref: str) -> EmissionResult:
        ...

    @abstractmethod
    def consultar_nfce(self, ref: str) -> EmissionResult:
        ...

    @abstractmethod
    def consultar_nfse(self, ref: str) -> EmissionResult:
        ...

    @abstractmethod
    def cancelar_nfe(self, ref: str, justificativa: str) -> EmissionResult:
        ...

    @abstractmethod
    def cancelar_nfce(self, ref: str, justificativa: str) -> EmissionResult:
        ...

    @abstractmethod
    def cancelar_nfse(self, ref: str, justificativa: str) -> EmissionResult:
        ...

    @abstractmethod
    def create_webhook(self, event: str, url: str, authorization: str, authorization_header: str) -> dict:
        ...
