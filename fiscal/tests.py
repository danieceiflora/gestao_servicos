from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from services.models import (
    Client as ServiceClient, Product, Property, Sale, SaleItem,
    Service, ServiceItem, ServiceOrder, ServiceOrderTask,
)

from .builders import (
    FiscalValidationError, build_nfe_or_nfce_payload, build_nfe_or_nfce_payload_from_task,
    build_nfse_nacional_payload,
)
from .gateways.focusnfe import FocusNFeGateway
from .models import NFeConfig, NFeDocument
from .utils import resolve_ibge_code_from_cep

User = get_user_model()


class ResolveIbgeCodeFromCepTest(TestCase):
    """As pessoas não digitam o código IBGE manualmente — resolvemos pelo CEP via
    ViaCEP (mesma API já usada pro autofill de endereço nos formulários)."""

    @patch('fiscal.utils.requests.get')
    def test_returns_ibge_code_on_success(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {
            'cep': '74891-000', 'localidade': 'Goiânia', 'uf': 'GO', 'ibge': '5208707', 'erro': False,
        })
        mock_get.return_value.raise_for_status = lambda: None
        self.assertEqual(resolve_ibge_code_from_cep('74891-000'), '5208707')

    @patch('fiscal.utils.requests.get')
    def test_returns_empty_when_cep_not_found(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {'erro': True})
        mock_get.return_value.raise_for_status = lambda: None
        self.assertEqual(resolve_ibge_code_from_cep('00000-000'), '')

    def test_returns_empty_for_invalid_cep_without_network_call(self):
        self.assertEqual(resolve_ibge_code_from_cep('123'), '')
        self.assertEqual(resolve_ibge_code_from_cep(''), '')
        self.assertEqual(resolve_ibge_code_from_cep(None), '')

    @patch('fiscal.utils.requests.get', side_effect=Exception('timeout'))
    def test_returns_empty_on_network_error(self, mock_get):
        self.assertEqual(resolve_ibge_code_from_cep('74891-000'), '')


class FocusNFeGatewayUrlTest(TestCase):
    """caminho_danfe/caminho_xml_nota_fiscal vêm da Focus como caminho relativo, não
    URL completa — sem prefixar o domínio, o link resolve contra a origem da própria
    página (localhost:8000) e dá 404 ao clicar em 'Ver DANFE/PDF'."""

    def test_full_url_prefixes_relative_path_with_sandbox_domain(self):
        gw = FocusNFeGateway(token='fake-token', environment='SANDBOX')
        result = gw._full_url('/arquivos_development/12345/202607/DANFEs/x.pdf')
        self.assertEqual(result, 'https://homologacao.focusnfe.com.br/arquivos_development/12345/202607/DANFEs/x.pdf')

    def test_full_url_prefixes_relative_path_with_production_domain(self):
        gw = FocusNFeGateway(token='fake-token', environment='PRODUCTION')
        result = gw._full_url('arquivos/12345/202607/DANFEs/x.pdf')
        self.assertEqual(result, 'https://api.focusnfe.com.br/arquivos/12345/202607/DANFEs/x.pdf')

    def test_full_url_leaves_absolute_url_untouched(self):
        gw = FocusNFeGateway(token='fake-token', environment='SANDBOX')
        absolute = 'https://outra-origem.com/arquivo.pdf'
        self.assertEqual(gw._full_url(absolute), absolute)

    def test_full_url_handles_empty_path(self):
        gw = FocusNFeGateway(token='fake-token', environment='SANDBOX')
        self.assertEqual(gw._full_url(''), '')


def _make_config():
    config = NFeConfig.load()
    config.razao_social = 'Dourados Calhas Ltda'
    config.cnpj = '12.345.678/0001-99'
    config.regime_tributario = NFeConfig.RegimeTributario.SIMPLES_NACIONAL
    config.logradouro = 'Avenida Aragoiana'
    config.numero = '97'
    config.bairro = 'Garavelo'
    config.municipio = 'Goiânia'
    config.codigo_municipio_ibge = '5208707'
    config.uf = 'GO'
    config.cep = '74891-000'
    config.default_codigo_tributacao_iss = '140101'
    config.default_codigo_tributacao_municipal_iss = '801'
    config.default_codigo_indicador_operacao = '020201'
    config.default_ibs_cbs_situacao_tributaria = '000'
    config.default_ibs_cbs_classificacao_tributaria = '000001'
    config.save()
    return config


class SaleFiscalBuilderTest(TestCase):
    def setUp(self):
        _make_config()
        self.user = User.objects.create_user(username='seller', password='x', role=User.Roles.COLLABORATOR)
        self.client_obj = ServiceClient.objects.create(
            name='Empresa Cliente Ltda', client_type='PJ', cnpj='98.765.432/0001-11',
        )
        Property.objects.create(
            client=self.client_obj, address='Rua das Flores', number='10',
            neighborhood='Centro', city='Goiânia', state='GO', cep='74000-000', ibge_code='5208707',
        )
        self.product = Product.objects.create(
            name='Calha de Alumínio', code='CALHA-01', default_unit_price=Decimal('50.00'),
            ncm='76109000', cest='2100100', cfop_padrao='5102', csosn='102',
            cst_pis='07', cst_cofins='07',
        )
        self.sale = Sale.objects.create(user=self.user, client=self.client_obj)
        self.item = SaleItem.objects.create(
            sale=self.sale, product=self.product, quantity=Decimal('3.00'), unit_price=Decimal('50.00'),
        )
        self.sale.total_amount = self.item.subtotal
        self.sale.save()

    def test_build_nfe_payload_has_emitente_destinatario_and_items(self):
        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')

        self.assertEqual(payload['cnpj_emitente'], '12345678000199')
        self.assertEqual(payload['cnpj_destinatario'], '98765432000111')
        self.assertEqual(payload['municipio_destinatario'], 'Goiânia')
        self.assertEqual(len(payload['items']), 1)

        item_payload = payload['items'][0]
        self.assertEqual(item_payload['codigo_produto'], 'CALHA-01')
        # CFOP é recalculado em SaleItem.save() via fiscal_logic.get_cfop() (depende de
        # SystemConfig.state x UF do cliente) — o builder deve refletir o valor congelado,
        # não necessariamente o cfop_padrao "cru" do produto.
        self.item.refresh_from_db()
        self.assertEqual(item_payload['cfop'], self.item.cfop_aplicado)
        self.assertTrue(item_payload['cfop'])
        self.assertEqual(item_payload['codigo_ncm'], '76109000')
        self.assertEqual(item_payload['quantidade_comercial'], 3.0)
        self.assertEqual(item_payload['valor_unitario_comercial'], 50.0)
        self.assertEqual(payload['valor_total'], float(self.sale.total_amount))
        self.assertNotIn('presenca_comprador', payload)

    def test_build_nfce_payload_adds_consumer_fields(self):
        payload = build_nfe_or_nfce_payload(self.sale, 'NFCE')

        self.assertEqual(payload['consumidor_final'], 1)
        self.assertIn('presenca_comprador', payload)
        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'], self.sale.forma_pagamento_sefaz)

    def test_build_nfe_payload_uses_frozen_fiscal_snapshot_over_product_defaults(self):
        # Simula uma mudança fiscal cadastral do produto após a venda: o payload
        # deve continuar usando o que foi congelado em SaleItem no momento da venda.
        self.item.cfop_aplicado = '6102'
        self.item.ncm_ato = '99999999'
        self.item.save()
        self.product.cfop_padrao = '5101'
        self.product.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        item_payload = payload['items'][0]
        self.assertEqual(item_payload['cfop'], '6102')
        self.assertEqual(item_payload['codigo_ncm'], '99999999')

    def test_unidade_comercial_uses_short_sefaz_code_not_full_label(self):
        # Bug corrigido: get_unit_type_display() retorna "Unidade (un)" (7+ chars),
        # que estoura o limite de 6 caracteres do campo uCom/uTrib da NFe e derruba a
        # validação de schema na Focus ("erro_validacao_schema"). Deve mandar "UN".
        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        item_payload = payload['items'][0]
        self.assertEqual(item_payload['unidade_comercial'], 'UN')
        self.assertEqual(item_payload['unidade_tributavel'], 'UN')
        self.assertLessEqual(len(item_payload['unidade_comercial']), 6)

    def test_raises_validation_error_when_product_missing_ncm(self):
        self.product.ncm = ''
        self.product.save()
        self.item.ncm_ato = ''
        self.item.save()

        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertTrue(any('NCM' in p for p in ctx.exception.problems))

    def test_raises_validation_error_when_product_missing_pis_cofins(self):
        # Bug corrigido: campos vazios eram mandados como string vazia no payload,
        # e a Focus rejeitava com "NF-e sem grupo do PIS" — sem apontar o produto.
        self.product.cst_pis = ''
        self.product.cst_cofins = ''
        self.product.save()

        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertTrue(any('CST PIS' in p for p in ctx.exception.problems))
        self.assertTrue(any('CST COFINS' in p for p in ctx.exception.problems))

    def test_raises_validation_error_when_client_has_no_document(self):
        self.client_obj.cnpj = None
        self.client_obj.save()

        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertTrue(any('CPF/CNPJ' in p for p in ctx.exception.problems))

    def test_raises_validation_error_when_no_items(self):
        self.item.delete()
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertTrue(any('Nenhum item' in p for p in ctx.exception.problems))

    def test_nfe_to_non_contribuinte_pj_requires_consumidor_final(self):
        # Bug corrigido: NFe sempre mandava consumidor_final=0, e a SEFAZ rejeita com
        # "Operação com não contribuinte deve indicar operação com consumidor final"
        # quando o destinatário (PJ sem Inscrição Estadual, ou PF) não é contribuinte.
        self.client_obj.state_registration = ''
        self.client_obj.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertEqual(payload['consumidor_final'], 1)
        self.assertEqual(payload['indicador_inscricao_estadual_destinatario'], 9)

    def test_nfe_to_contribuinte_pj_is_not_consumidor_final(self):
        self.client_obj.state_registration = '123456789'
        self.client_obj.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertEqual(payload['consumidor_final'], 0)
        self.assertEqual(payload['indicador_inscricao_estadual_destinatario'], 1)

    def test_nfe_to_pf_is_always_consumidor_final(self):
        pf_client = ServiceClient.objects.create(name='Fulano de Tal', client_type='PF', cpf='111.222.333-44')
        Property.objects.create(
            client=pf_client, address='Rua C', neighborhood='Centro',
            city='Goiânia', state='GO', ibge_code='5208707',
        )
        self.sale.client = pf_client
        self.sale.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertEqual(payload['consumidor_final'], 1)
        self.assertEqual(payload['indicador_inscricao_estadual_destinatario'], 9)

    def test_nfce_is_always_consumidor_final_regardless_of_client(self):
        self.client_obj.state_registration = '123456789'  # contribuinte
        self.client_obj.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFCE')
        self.assertEqual(payload['consumidor_final'], 1)

    def test_data_emissao_has_explicit_brasilia_offset(self):
        # Bug corrigido: com USE_TZ=False (produção, DEBUG=False) o antigo código usava
        # timezone.now().strftime('%z'), que produz string vazia para datetime naive —
        # data_emissao saía sem offset, a SEFAZ assumia UTC e rejeitava a NFe com
        # "Data-Hora de Emissão posterior ao horário de recebimento" (Brasília lido
        # como se já fosse UTC, ~3h no futuro). Agora deve sempre vir com -03:00.
        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertTrue(payload['data_emissao'].endswith('-03:00'), payload['data_emissao'])

    def test_local_destino_matches_interstate_cfop(self):
        # Bug corrigido: local_destino (idDest) estava fixo em 1 (operação interna),
        # mas o CFOP do item pode ser interestadual (6xxx) quando a UF do cliente
        # difere da UF da empresa — a SEFAZ rejeita com "CFOP de operação
        # interestadual e idDest diferente de 2" se os dois não baterem.
        self.item.cfop_aplicado = '6102'
        self.item.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertEqual(payload['local_destino'], 2)

    def test_local_destino_matches_internal_cfop(self):
        self.item.cfop_aplicado = '5102'
        self.item.save()

        payload = build_nfe_or_nfce_payload(self.sale, 'NFE')
        self.assertEqual(payload['local_destino'], 1)


class ServiceOrderFiscalBuilderTest(TestCase):
    """Emissão de OS é por ETAPA (ServiceOrderTask), não pela OS inteira — cada etapa
    pode ter produto e serviço misturados, e cada tipo vai para um documento fiscal
    separado (NFSe pro serviço, NFe/NFCe pro produto), nunca somados."""

    def setUp(self):
        _make_config()
        self.client_obj = ServiceClient.objects.create(
            name='Maria da Silva', client_type='PF', cpf='123.456.789-00',
        )
        self.property_obj = Property.objects.create(
            client=self.client_obj, address='Rua B', neighborhood='Setor Sul',
            city='Goiânia', state='GO', ibge_code='5208707',
        )
        self.order = ServiceOrder.objects.create(
            client_property=self.property_obj, description='Instalação de calhas residenciais',
        )
        self.task = ServiceOrderTask.objects.create(
            service_order=self.order, task_type='EXECUCAO', scheduled_at=timezone.now(),
        )
        self.service = Service.objects.create(
            name='Instalação de Calha', base_price=Decimal('800.00'),
            codigo_tributacao_nacional_iss='140101', codigo_nbs='010530000',
        )
        self.service_item = ServiceItem.objects.create(
            service_order=self.order, task=self.task, service=self.service,
            description='Instalação de Calha', quantity=1, unit_price=Decimal('800.00'),
        )
        self.product = Product.objects.create(
            name='Calha de Alumínio', code='CALHA-01', default_unit_price=Decimal('50.00'),
            ncm='76109000', cest='2100100', cfop_padrao='5102', csosn='102',
            cst_pis='07', cst_cofins='07',
        )

    def test_build_nfse_payload_maps_prestador_tomador_and_servico(self):
        payload = build_nfse_nacional_payload(self.task)

        self.assertEqual(payload['cnpj_prestador'], '12345678000199')
        self.assertEqual(payload['cpf_tomador'], '12345678900')
        self.assertEqual(payload['codigo_municipio_emissora'], '5208707')
        self.assertEqual(payload['codigo_municipio_prestacao'], '5208707')
        self.assertEqual(payload['codigo_tributacao_nacional_iss'], '140101')
        self.assertEqual(payload['valor_servico'], 800.0)
        self.assertIn('Instalação de calhas', payload['descricao_servico'])

    def test_build_nfse_payload_never_sends_codigo_tributacao_municipal(self):
        # cTribMun (código de tributação municipal): uma NFSe real emitida
        # manualmente pelo Portal Nacional (mesmo CNPJ, mesmo item de serviço) foi
        # autorizada (cStat=100) com <cServ><cTribNac>...</cTribNac><xDescServ>...
        # sem cTribMun no meio — Goiânia não usa esse campo. Não enviamos mais, e a
        # emissão não deve mais falhar por falta dele mesmo sem nenhum valor
        # configurado em Service/NFeConfig.
        payload = build_nfse_nacional_payload(self.task)
        self.assertNotIn('codigo_tributacao_municipal_iss', payload)

    def test_build_nfse_payload_includes_regime_especial_tributacao_always(self):
        # Bug corrigido (2 rounds): 1º round, SEFAZ rejeitava com "regTrib: Missing
        # child element(s). Expected is one of (regApTribSN, regEspTrib)" — nenhum dos
        # dois era enviado. Depois de enviar só regApTribSN (condicional ao Simples
        # Nacional), a rejeição mudou para "Expected is (regEspTrib)" — os dois campos
        # não são alternativos, regEspTrib é sempre obrigatório (0 = Nenhum),
        # independente do regime tributário do prestador.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['regime_especial_tributacao'], 0)
        self.assertEqual(payload['regime_tributario_simples_nacional'], 1)

    def test_build_nfse_payload_omits_regime_tributario_simples_nacional_for_non_sn(self):
        config = NFeConfig.load()
        config.regime_tributario = NFeConfig.RegimeTributario.NORMAL
        config.save()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['regime_especial_tributacao'], 0)
        self.assertNotIn('regime_tributario_simples_nacional', payload)

    def test_build_nfse_payload_includes_consumidor_final(self):
        # Bug corrigido: SEFAZ rejeitava com "valores not expected, expected one of
        # (indFinal, cIndOp)" — a NFSe Nacional (Reforma Tributária) também exige um
        # indicador de consumidor final, assim como a NFe/NFCe já exigia (indFinal).
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['consumidor_final'], 1)

    def test_build_nfse_payload_includes_codigo_indicador_operacao(self):
        # Bug corrigido: depois de enviar indFinal, a rejeição mudou para "valores not
        # expected, expected (cIndOp)" — os dois campos são exigidos juntos, não
        # alternativos. Para o item 07.02 (instalação de calhas), o Anexo VIII do
        # Comitê Gestor da NFS-e usa uniformemente '020201'.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_indicador_operacao'], '020201')

    def test_build_nfse_payload_includes_indicador_total_tributos(self):
        # Bug corrigido: SEFAZ rejeitava com "trib: Missing child element(s). Expected
        # is one of (tribFed, totTrib)" — faltava o grupo totTrib (Lei 12.741/2012).
        # 0 = não informa valor estimado de tributos, confirmado contra NFSe real
        # autorizada com <totTrib><indTotTrib>0</indTotTrib></totTrib>.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['indicador_total_tributacao'], 0)

    def test_build_nfse_payload_includes_indicador_destinatario(self):
        # Bug corrigido: SEFAZ rejeitava com "valores not expected, expected one of
        # (tpOper, gRefNFSe, tpEnteGov, indDest)" — faltava o indicador de destinatário
        # do grupo Reforma Tributária. 0 = destinatário é o mesmo que o tomador.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['indicador_destinatario'], 0)

    def test_build_nfse_payload_includes_codigo_nbs(self):
        # Bug corrigido: SEFAZ rejeitava com "É obrigatório informar na DPS um item
        # da NBS se for declarada qualquer informação de IBS/CBS" — como o grupo
        # IBS/CBS é sempre enviado, o NBS (cNBS, Anexo VIII) também precisa ser.
        # Diferente do cIndOp, o NBS não é uniforme por item LC 116 — cada serviço
        # tem o seu (010530000 para calhas, por exemplo).
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_nbs'], '010530000')

    def test_nfse_raises_when_no_codigo_nbs_available(self):
        self.service.codigo_nbs = ''
        self.service.save()
        config = NFeConfig.load()
        config.default_codigo_nbs = ''
        config.save()
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfse_nacional_payload(self.task)
        self.assertTrue(any('Código NBS' in p for p in ctx.exception.problems))

    def test_nfse_raises_when_no_codigo_indicador_operacao_available(self):
        config = NFeConfig.load()
        config.default_codigo_indicador_operacao = ''
        config.save()
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfse_nacional_payload(self.task)
        self.assertTrue(any('Código Indicador de Operação' in p for p in ctx.exception.problems))

    def test_build_nfse_payload_includes_tomador_name_and_address(self):
        # Bug corrigido: sem razao_social_tomador (xNome no XML), a Focus rejeita com
        # "toma: Missing child element(s)" e um "email" aparece fora de ordem no lugar
        # esperado do nome — a NFSe Nacional exige o nome do tomador.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['razao_social_tomador'], self.client_obj.display_name)
        self.assertEqual(payload['logradouro_tomador'], 'Rua B')
        self.assertEqual(payload['bairro_tomador'], 'Setor Sul')
        self.assertEqual(payload['codigo_municipio_tomador'], '5208707')

    def test_build_nfse_payload_includes_tributacao_iss_and_ibs_cbs(self):
        # Bugs corrigidos: tributacao_iss nunca era enviado (obrigatório) e o grupo
        # IBS/CBS (Reforma Tributária) é exigido pela NFSe Nacional desde 2026 —
        # "infDPS: Missing child element(s). Expected is IBSCBS".
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['tributacao_iss'], 1)
        self.assertEqual(payload['ibs_cbs_situacao_tributaria'], '000')
        self.assertEqual(payload['ibs_cbs_classificacao_tributaria'], '000001')

    def test_build_nfse_payload_includes_prestador_name_address_and_finalidade(self):
        # Bugs corrigidos: razao_social_prestador nunca era enviado — mesma exigência
        # do nome do tomador (xNome) — e a SEFAZ rejeitava com "email not expected,
        # expected CAEPF/IM" na seção do prestador; finalidade_emissao (finNFSe) também
        # nunca era enviado, campo obrigatório — rejeitava com "valores not expected,
        # expected finNFSe".
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['razao_social_prestador'], 'Dourados Calhas Ltda')
        self.assertEqual(payload['codigo_municipio_prestador'], '5208707')
        self.assertEqual(payload['logradouro_prestador'], 'Avenida Aragoiana')
        self.assertEqual(payload['finalidade_emissao'], 0)

    def test_build_nfse_payload_includes_tipo_retencao_iss(self):
        # Bug corrigido: o grupo tribMun exige pelo menos um entre retenção/imunidade/
        # suspensão/benefício — sem nenhum, a SEFAZ rejeita com "tribMun: Missing
        # child element(s)". Mandamos tipo_retencao_iss=1 (não retido) como padrão.
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['tipo_retencao_iss'], 1)

    def test_build_nfse_payload_includes_inscricao_municipal_prestador_when_set(self):
        # "Inscrição Municipal do prestador do serviço não encontrada" acontecia com
        # NFeConfig.environment=SANDBOX (homologação não replica o cadastro real). Uma
        # NFSe real emitida manualmente em produção (mesmo CNPJ) veio autorizada
        # (cStat=100) com <prest><IM>5468736</IM></prest> presente — confirma que a IM
        # deve ser enviada quando configurada, não omitida.
        config = NFeConfig.load()
        self.assertFalse(config.inscricao_municipal)
        payload = build_nfse_nacional_payload(self.task)
        self.assertNotIn('inscricao_municipal_prestador', payload)

        config.inscricao_municipal = '5468736'
        config.save()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['inscricao_municipal_prestador'], '5468736')

    def test_build_nfse_payload_codigo_opcao_simples_nacional(self):
        # opSimpNac: 1 = Não optante, 2 = Optante MEI, 3 = Optante ME/EPP. Uma NFSe
        # real emitida em produção (prestador optante do Simples Nacional, não MEI)
        # veio autorizada com opSimpNac=3 — o mapeamento antigo mandava '1' pra esse
        # caso (invertido).
        config = NFeConfig.load()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_opcao_simples_nacional'], '3')  # SIMPLES_NACIONAL (default)

        config.regime_tributario = NFeConfig.RegimeTributario.NORMAL
        config.save()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_opcao_simples_nacional'], '1')

        config.regime_tributario = NFeConfig.RegimeTributario.MEI
        config.save()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_opcao_simples_nacional'], '2')

    def test_build_nfse_payload_includes_grupo_obra_for_construction_subitens(self):
        # Bug corrigido: SEFAZ rejeitava com "O grupo de informações de obra é
        # obrigatório quando o código de tributação nacional pertencer a um dos
        # subitens 07.02.01, 07.02.02, [...]" — '070201' (instalação de calhas) é um
        # desses subitens. Ainda não temos Inscrição Imobiliária/CNO/CEI cadastrados,
        # então preenchemos o grupo só com o endereço do imóvel (já disponível).
        self.service.codigo_tributacao_nacional_iss = '070201'
        self.service.save()
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['logradouro_obra'], 'Rua B')
        self.assertEqual(payload['bairro_obra'], 'Setor Sul')
        self.assertEqual(payload['numero_obra'], 'S/N')

    def test_build_nfse_payload_omits_grupo_obra_for_non_construction_subitens(self):
        # codigo_tributacao_nacional_iss='140101' (padrão do setUp) não está na lista
        # de subitens de obra — o grupo não deve ser enviado à toa.
        payload = build_nfse_nacional_payload(self.task)
        self.assertNotIn('logradouro_obra', payload)
        self.assertNotIn('cep_obra', payload)

    def test_raises_validation_error_when_property_missing_ibge_code(self):
        self.property_obj.ibge_code = ''
        self.property_obj.save()
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfse_nacional_payload(self.task)
        self.assertTrue(any('Código IBGE' in p for p in ctx.exception.problems))

    def test_raises_validation_error_when_ibs_cbs_not_configured(self):
        config = NFeConfig.load()
        config.default_ibs_cbs_situacao_tributaria = ''
        config.default_ibs_cbs_classificacao_tributaria = ''
        config.save()

        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfse_nacional_payload(self.task)
        self.assertTrue(any('IBS/CBS' in p for p in ctx.exception.problems))

    def test_build_nfse_payload_falls_back_to_config_default_iss_code(self):
        self.service.codigo_tributacao_nacional_iss = ''
        self.service.save()

        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['codigo_tributacao_nacional_iss'], '140101')  # default do NFeConfig

    def test_data_competencia_present_and_defaults_to_today(self):
        # Bug corrigido: a DPS Nacional exige data_competencia (dCompet) no XML antes
        # de outros elementos (ex: tpEmit) — sem esse campo, a Focus gera um XML fora
        # de ordem e a validação de schema rejeita com "Element tpEmit not expected,
        # expected dCompet". Sem execução concluída, cai para a data de hoje.
        payload = build_nfse_nacional_payload(self.task)
        self.assertIn('data_competencia', payload)
        from datetime import date
        self.assertEqual(payload['data_competencia'], date.today().isoformat())

    def test_data_competencia_uses_own_finished_date(self):
        from datetime import date
        finished = timezone.now() - timezone.timedelta(days=3)
        self.task.status = 'CONCLUIDO'
        self.task.finished_at = finished
        self.task.save()

        payload = build_nfse_nacional_payload(self.task)
        # Compara de forma tolerante a fuso (não usa igualdade exata de data) para não
        # ficar frágil a conversões de timezone dependentes do SO da máquina de teste —
        # o importante é confirmar que usou a data de execução da PRÓPRIA etapa, não o
        # fallback "hoje" (não busca mais em outras etapas da OS).
        self.assertNotEqual(payload['data_competencia'], date.today().isoformat())

    def test_nfse_raises_when_task_has_no_service_items(self):
        self.service_item.delete()
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfse_nacional_payload(self.task)
        self.assertTrue(any('não tem itens de serviço' in p for p in ctx.exception.problems))

    def test_nfse_value_ignores_product_items_in_same_task(self):
        # A etapa tem serviço (800) E produto (150) juntos no mesmo faturamento — a
        # NFSe deve cobrir só a parte de serviço, nunca somar os dois (padrão de
        # mercado / LC 116 item 7.02 — ver conversa sobre Bling e nota conjugada).
        ServiceItem.objects.create(
            service_order=self.order, task=self.task, product=self.product,
            description='Calha de Alumínio', quantity=3, unit_price=Decimal('50.00'),
        )
        payload = build_nfse_nacional_payload(self.task)
        self.assertEqual(payload['valor_servico'], 800.0)

    def test_build_nfe_from_task_covers_only_product_items(self):
        ServiceItem.objects.create(
            service_order=self.order, task=self.task, product=self.product,
            description='Calha de Alumínio', quantity=3, unit_price=Decimal('50.00'),
        )
        payload = build_nfe_or_nfce_payload_from_task(self.task, 'NFE')
        self.assertEqual(len(payload['items']), 1)
        self.assertEqual(payload['items'][0]['codigo_produto'], 'CALHA-01')
        self.assertEqual(payload['valor_total'], 150.0)

    def test_build_nfe_from_task_raises_when_no_product_items(self):
        with self.assertRaises(FiscalValidationError) as ctx:
            build_nfe_or_nfce_payload_from_task(self.task, 'NFE')
        self.assertTrue(any('Nenhum item de produto' in p for p in ctx.exception.problems))

    def test_task_discount_is_allocated_proportionally_between_product_and_service(self):
        # ServiceOrderTask.discount é um valor único (R$) pro faturamento da etapa
        # inteira (produto+serviço). Como agora emitimos em dois documentos separados,
        # o desconto precisa ser rateado proporcionalmente pra soma continuar batendo
        # com o valor total da etapa/cobrança já gerada.
        ServiceItem.objects.create(
            service_order=self.order, task=self.task, product=self.product,
            description='Calha de Alumínio', quantity=3, unit_price=Decimal('50.00'),
        )
        # bruto: serviço 800 (84.2%) + produto 150 (15.8%) = 950 total
        self.task.discount = Decimal('95.00')  # 10% do total
        self.task.save()

        nfse_payload = build_nfse_nacional_payload(self.task)
        nfe_payload = build_nfe_or_nfce_payload_from_task(self.task, 'NFE')

        total_net = Decimal(str(nfse_payload['valor_servico'])) + Decimal(str(nfe_payload['valor_total']))
        self.assertEqual(total_net, self.task.billing_value_net)
