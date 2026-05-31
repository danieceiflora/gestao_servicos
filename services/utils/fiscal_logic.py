from decimal import Decimal

def get_cfop(origem_uf, destino_uf, tem_st=False):
    """
    Retorna o CFOP baseado na origem, destino e se tem Substituição Tributária.
    """
    origem_uf = (origem_uf or '').strip().upper()
    destino_uf = (destino_uf or '').strip().upper()
    
    # Se UF Destino não informada, assume operação interna
    if not destino_uf:
        destino_uf = origem_uf

    if origem_uf == destino_uf:
        # Operação Interna (5xxx)
        return '5405' if tem_st else '5102'
    else:
        # Operação Interestadual (6xxx)
        return '6403' if tem_st else '6102'

def calculate_ibpt(valor_total, aliquota_fed=0, aliquota_est=0, aliquota_mun=0):
    """
    Retorna a soma dos impostos aproximados baseada no valor total do item e alíquotas IBPT.
    """
    valor_total = Decimal(str(valor_total or 0))
    aliquota_fed = Decimal(str(aliquota_fed or 0))
    aliquota_est = Decimal(str(aliquota_est or 0))
    aliquota_mun = Decimal(str(aliquota_mun or 0))
    
    total_aliquota = aliquota_fed + aliquota_est + aliquota_mun
    
    vlr_tributos = (valor_total * total_aliquota) / Decimal('100')
    return vlr_tributos.quantize(Decimal('0.01'))
