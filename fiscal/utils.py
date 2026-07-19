import logging
import re

import requests

logger = logging.getLogger(__name__)


def resolve_ibge_code_from_cep(cep: str) -> str:
    """Consulta o ViaCEP e retorna o código IBGE do município (7 dígitos), ou ''
    se o CEP for inválido, não for encontrado, ou a consulta falhar.

    Mesma API pública já usada no autofill de endereço dos formulários de imóvel/
    cliente (property_form.html, client_form.html, client_reg_form.html) — a
    resposta do ViaCEP já inclui o campo `ibge`, só não estava sendo aproveitado.
    Esta função é o fallback para cadastros antigos que não tinham esse campo
    preenchido — chamada na hora da emissão (fiscal/views.py), nunca dentro de
    fiscal/builders.py, que é propositalmente livre de chamada de rede."""
    digits = re.sub(r'\D', '', cep or '')
    if len(digits) != 8:
        return ''
    try:
        resp = requests.get(f'https://viacep.com.br/ws/{digits}/json/', timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get('erro'):
            return ''
        return data.get('ibge', '') or ''
    except Exception:
        logger.warning('Falha ao consultar ViaCEP para CEP %r', cep, exc_info=True)
        return ''
