"""Leitura do XML de NF-e emitida por um fornecedor, para pré-preencher uma
Nota de Entrada (compra) — mesmo papel do "Importar XML" do módulo de Nota
Fiscal de Entrada do Bling. Também cuida do cadastro automático de fornecedor
e produtos que ainda não existem no sistema, a partir dos dados do próprio XML."""
import re
import uuid as uuid_lib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree as ET

UNIT_MAP = {
    'UN': 'UNIDADE', 'UND': 'UNIDADE', 'PC': 'UNIDADE', 'PCT': 'UNIDADE',
    'CX': 'UNIDADE', 'PAR': 'UNIDADE', 'KIT': 'UNIDADE',
    'KG': 'QUILO', 'KILO': 'QUILO', 'G': 'QUILO',
    'M': 'METRO', 'MT': 'METRO',
    'M2': 'M2', 'M²': 'M2',
    'L': 'LITRO', 'LT': 'LITRO', 'LITRO': 'LITRO',
}


class NFeXMLParseError(Exception):
    pass


def _strip_namespaces(root):
    """Remove o namespace de todas as tags da árvore (`{uri}tag` -> `tag`).

    XMLs de NF-e "de verdade" variam bastante na prática: alguns vêm sem
    xmlns nenhum, outros com uma URI de versão diferente, outros ainda
    reencodados por algum ERP no meio do caminho. Em vez de depender de uma
    URI de namespace fixa (que quebra silenciosamente com qualquer variação
    e faz todo `find()` retornar None), a árvore inteira é normalizada uma
    vez e o resto do parser trabalha só com nomes de tag simples."""
    for el in root.iter():
        if isinstance(el.tag, str) and '}' in el.tag:
            el.tag = el.tag.split('}', 1)[1]
    return root


def _text(el, path):
    if el is None:
        return ''
    node = el.find(path)
    return node.text.strip() if node is not None and node.text else ''


def _first_group_text(det, group_name, leaf):
    """Pega a tag `leaf` dentro do primeiro filho de `group_name` no `<det>`
    (ex.: ICMS tem vários sub-grupos: ICMS00, ICMS10, ...). Retorna '' se não
    encontrar — não explode na importação por variações de layout de CST."""
    if det is None:
        return ''
    group = det.find(group_name)
    if group is None:
        return ''
    first_sub_group = next(iter(group), None)
    if first_sub_group is None:
        return ''
    node = first_sub_group.find(leaf)
    return node.text.strip() if node is not None and node.text else ''


def _decimal(value, default='0'):
    try:
        return Decimal(value or default)
    except InvalidOperation:
        return Decimal(default)


def round_money(value):
    """Arredonda pra 2 casas decimais — os campos do sistema (quantidade,
    custo) usam decimal_places=2, mas o XML costuma vir com 4 casas."""
    return Decimal(value or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def parse_nfe_xml(file_obj):
    """Extrai cabeçalho, fornecedor e itens de um XML de NF-e (padrão SEFAZ).

    Aceita tanto o XML "puro" (<NFe>) quanto o processado (<nfeProc><NFe>...).
    Retorna um dict:
        {
            'number': str, 'series': str, 'access_key': str, 'issue_date': 'YYYY-MM-DD',
            'supplier_cnpj': str, 'supplier_name': str, 'supplier_trade_name': str,
            'supplier_ie': str, 'supplier_phone': str, 'supplier_address': str,
            'items': [{'code': str, 'barcode': str, 'name': str, 'unit': str,
                       'ncm': str, 'cfop': str,
                       'quantity': Decimal, 'unit_cost': Decimal}, ...]
        }
    Levanta NFeXMLParseError se o arquivo não for um XML de NF-e válido.
    """
    try:
        tree = ET.parse(file_obj)
    except ET.ParseError as exc:
        raise NFeXMLParseError(f"Arquivo XML mal formado: {exc}") from exc
    except Exception as exc:
        raise NFeXMLParseError(f"Não foi possível ler o arquivo como XML: {exc}") from exc

    root = _strip_namespaces(tree.getroot())

    inf_nfe = root.find('.//infNFe')
    if inf_nfe is None:
        found_tags = sorted({el.tag for el in root.iter()})
        raise NFeXMLParseError(
            "XML não contém o nó <infNFe> — não parece ser uma NF-e válida. "
            f"Tags encontradas no arquivo: {', '.join(found_tags[:15])}"
            f"{'…' if len(found_tags) > 15 else ''}"
        )

    access_key = (inf_nfe.get('Id') or '').replace('NFe', '')

    ide = inf_nfe.find('ide')
    emit = inf_nfe.find('emit')
    ender_emit = emit.find('enderEmit') if emit is not None else None

    number = _text(ide, 'nNF')
    series = _text(ide, 'serie')
    dh_emi = _text(ide, 'dhEmi') or _text(ide, 'dEmi')
    issue_date = dh_emi[:10] if dh_emi else ''

    supplier_cnpj = _text(emit, 'CNPJ') or _text(emit, 'CPF')
    supplier_name = _text(emit, 'xNome')
    supplier_trade_name = _text(emit, 'xFant')
    supplier_ie = _text(emit, 'IE')
    supplier_phone = _text(ender_emit, 'fone')

    address_parts = [
        _text(ender_emit, 'xLgr'),
        _text(ender_emit, 'nro'),
    ]
    address_line = ', '.join(p for p in address_parts if p)
    city_uf = ' - '.join(p for p in [_text(ender_emit, 'xMun'), _text(ender_emit, 'UF')] if p)
    bairro = _text(ender_emit, 'xBairro')
    supplier_address = ' — '.join(p for p in [address_line, bairro, city_uf] if p)

    items = []
    for det in inf_nfe.findall('det'):
        prod = det.find('prod')
        if prod is None:
            continue
        code = _text(prod, 'cProd')
        barcode = _text(prod, 'cEAN')
        if barcode in ('SEM GTIN', ''):
            barcode = ''
        name = _text(prod, 'xProd')
        qty = round_money(_decimal(_text(prod, 'qCom')))

        v_prod = _decimal(_text(prod, 'vProd'))
        v_frete = _decimal(_text(prod, 'vFrete'))
        v_seg = _decimal(_text(prod, 'vSeg'))
        v_outro = _decimal(_text(prod, 'vOutro'))
        # Custo líquido do fornecedor: (vProd + vFrete + vSeg + vOutro) / qCom.
        # Desconto (vDesc) não entra — alinhado ao fluxo Bling e padrão ERP.
        extras = v_frete + v_seg + v_outro
        if qty and qty != 0:
            unit_cost = round_money((v_prod + extras) / qty)
        else:
            unit_cost = round_money(_decimal(_text(prod, 'vUnCom')))

        origem_txt = _first_group_text(det, 'imposto/ICMS', 'orig')
        try:
            origem = int(origem_txt) if origem_txt else 0
        except (TypeError, ValueError):
            origem = 0
        icms_raw = _first_group_text(det, 'imposto/ICMS', 'CST') or _first_group_text(det, 'imposto/ICMS', 'CSOSN')
        pis_cst = _first_group_text(det, 'imposto/PIS', 'CST')
        cofins_cst = _first_group_text(det, 'imposto/COFINS', 'CST')

        items.append({
            'code': code,
            'barcode': barcode,
            'name': name,
            'unit': _text(prod, 'uCom'),
            'ncm': _text(prod, 'NCM'),
            'cfop': _text(prod, 'CFOP'),
            'cest': _text(prod, 'CEST'),
            'quantity': qty,
            'unit_cost': unit_cost,
            'extra_cost': extras,
            'origem': origem,
            'icms_raw': icms_raw,
            'pis_cst': pis_cst,
            'cofins_cst': cofins_cst,
        })

    if not items:
        raise NFeXMLParseError("O XML foi lido, mas nenhum item (tag <det>) foi encontrado dentro de <infNFe>.")

    return {
        'number': number,
        'series': series,
        'access_key': access_key,
        'issue_date': issue_date,
        'supplier_cnpj': supplier_cnpj,
        'supplier_name': supplier_name,
        'supplier_trade_name': supplier_trade_name,
        'supplier_ie': supplier_ie,
        'supplier_phone': supplier_phone,
        'supplier_address': supplier_address,
        'items': items,
    }


def match_products(items):
    """Para cada item extraído do XML, tenta casar com um Product existente
    pelo código (cProd) e, se não achar, pelo código de barras (cEAN).
    Retorna (matched_items, unmatched_labels) — matched_items é a lista de
    dicts originais acrescida de 'product' (instância ou None)."""
    from .models import Product

    matched_items = []
    unmatched_labels = []
    for item in items:
        product = None
        if item['code']:
            product = Product.objects.filter(code=item['code']).first()
        if product is None and item['barcode']:
            product = Product.objects.filter(barcode=item['barcode']).first()
        if product is None:
            unmatched_labels.append(f"{item['code'] or 's/código'} — {item['name']}")
        matched_items.append({**item, 'product': product})

    return matched_items, unmatched_labels


def find_supplier_by_cnpj(cnpj):
    """Casa um CNPJ (formatado ou não) com um Supplier já cadastrado,
    comparando só os dígitos — o campo `cnpj` é salvo formatado."""
    from .models import Supplier

    digits = re.sub(r'\D', '', cnpj or '')
    if not digits:
        return None
    for supplier in Supplier.objects.exclude(cnpj__isnull=True).exclude(cnpj=''):
        if re.sub(r'\D', '', supplier.cnpj or '') == digits:
            return supplier
    return None


def format_cnpj(digits):
    if len(digits) != 14:
        return digits
    return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def get_or_create_supplier_from_xml(parsed):
    """Retorna (supplier, created) — casa pelo CNPJ do emitente do XML e, se
    não achar ninguém cadastrado, cria um Fornecedor novo com os dados do
    próprio XML (CNPJ, razão social, nome fantasia, IE, telefone, endereço)."""
    from .models import Supplier

    supplier = find_supplier_by_cnpj(parsed['supplier_cnpj'])
    if supplier:
        return supplier, False

    digits = re.sub(r'\D', '', parsed['supplier_cnpj'] or '')
    if not digits:
        return None, False

    supplier = Supplier.objects.create(
        client_type='PJ',
        name=parsed['supplier_name'] or f"Fornecedor {format_cnpj(digits)}",
        trade_name=parsed.get('supplier_trade_name') or None,
        cnpj=format_cnpj(digits),
        state_registration=parsed.get('supplier_ie') or None,
        phone=parsed.get('supplier_phone') or None,
        address=parsed.get('supplier_address') or None,
    )
    return supplier, True


def _fiscal_kwargs_for_product(item):
    """Devolve kwargs para Product incluindo campos fiscais, resolvendo CST vs
    CSOSN conforme o regime tributário da empresa (NFeConfig.regime_tributario).
    ICMS Raw de 2 dígitos → CST ICMS (Regime Normal); 3 dígitos → CSOSN (Simples).
    Se tipo diverge do regime da empresa, NÃO preenchemos o campo (o usuário
    revisa manualmente) e o preview marca 'regime_mismatch'."""
    from fiscal.models import NFeConfig

    fiscal = dict(
        ncm=item.get('ncm') or None,
        cest=item.get('cest') or None,
        cfop_padrao=item.get('cfop') or None,
        cst_pis=item.get('pis_cst') or None,
        cst_cofins=item.get('cofins_cst') or None,
    )
    origem = item.get('origem')
    if origem is not None:
        fiscal['origem_mercadoria'] = origem

    try:
        cfg = NFeConfig.load()
        is_simples = cfg.regime_tributario in (1, 2)
    except Exception:
        is_simples = None

    icms_raw = item.get('icms_raw') or ''
    fiscal['tax_field'] = None
    if icms_raw and len(icms_raw) == 3 and is_simples is not False:
        fiscal['csosn'] = icms_raw
        fiscal['tax_field'] = 'csosn'
    elif icms_raw and len(icms_raw) == 2 and is_simples is not True:
        fiscal['cst_icms'] = icms_raw
        fiscal['tax_field'] = 'cst_icms'
    return fiscal


def _update_product_fiscal(product, item):
    """Preenche campos fiscais vazios do `product` com os dados do `item`
    (CST/CSOSN já resolvido por _fiscal_kwargs_for_product). Retorna lista de
    campos atualizados, ou [] se nada foi mudado."""
    kwargs = _fiscal_kwargs_for_product(item)
    # Remover chaves não-fields (sentinel 'tax_field') antes de checar.
    changed = []
    for field, value in kwargs.items():
        if field == 'tax_field':
            continue
        current = getattr(product, field, None)
        # normalize empty
        if (current is None or current == '') and value is not None:
            setattr(product, field, value)
            changed.append(field)
    # campos fiscais StringField com None — cuidamos na validação de update_fields
    if changed:
        product.save(update_fields=changed)
    return [f for f in changed if f != 'tax_field']


def create_missing_products(matched_items, supplier=None, user=None):
    """Cadastra automaticamente, no catálogo, os produtos do XML que não
    casaram com nenhum produto existente (por código ou EAN). Preenche
    `item['product']` com o produto recém-criado. Retorna a lista de
    produtos criados, para avisar o usuário e ele revisar depois (categoria,
    preço de venda, estoque mínimo etc. não vêm do XML)."""
    from django.db import IntegrityError
    from .models import Product

    created = []
    for item in matched_items:
        if item['product'] is not None:
            continue

        code = item['code'] or None
        name = item['name'] or (f"Produto {code}" if code else "Produto sem nome (importado)")
        unit_type = UNIT_MAP.get((item.get('unit') or '').upper(), 'UNIDADE')
        fiscal_kwargs = _fiscal_kwargs_for_product(item)
        # Remove sentinel pra não passar como product field.
        fiscal_kwargs.pop('tax_field', None)
        base_kwargs = dict(
            barcode=item['barcode'] or None,
            unit_type=unit_type,
            supplier=supplier,
            default_unit_price=item['unit_cost'],
            preco_custo=item['unit_cost'],
            registration_source=Product.RegistrationSource.XML,
            created_by=user,
            **fiscal_kwargs,
        )
        try:
            product = Product.objects.create(name=name, code=code, **base_kwargs)
        except IntegrityError:
            # Nome ou código já em uso por outro produto (não casado antes por
            # falta de EAN/código correspondente) — usa um sufixo pra não travar a importação.
            suffix = code or uuid_lib.uuid4().hex[:6]
            product = Product.objects.create(name=f"{name} ({suffix})", code=None, **base_kwargs)

        item['product'] = product
        created.append(product)

    return created
