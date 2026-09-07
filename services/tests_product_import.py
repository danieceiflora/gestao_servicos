from io import BytesIO
from decimal import Decimal
from unittest.mock import ANY, MagicMock, call, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook
from xlrd.compdoc import CompDocError

from .models import ImportHistory, ImportItem, Product, ProductCategory, StockMovement, Supplier, User
from .forms import ProductImportForm
from .utils_product_import import decimal_from_brazilian, parse_bling_rows, read_spreadsheet


BLING_HEADERS = [
    'ID', 'Código', 'Descrição', 'Unidade', 'NCM', 'Origem', 'Preço',
    'Situação', 'Estoque', 'Preço de custo', 'Cód. no fornecedor',
    'Fornecedor', 'Estoque máximo', 'Estoque mínimo', 'Peso líquido (Kg)',
    'Peso bruto (Kg)', 'GTIN/EAN', 'Largura do produto', 'Altura do Produto',
    'Profundidade do produto', 'Produto Variação', 'Tipo do item', 'CEST',
    'Unidade de Medida', 'Categoria do produto', 'Marca',
]


def make_bling_xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(BLING_HEADERS)
    for row in rows:
        sheet.append([row.get(header, '') for header in BLING_HEADERS])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def sample_row(**overrides):
    row = {
        'ID': 16691171492,
        'Código': '536\t',
        'Descrição': 'Produto Bling',
        'Unidade': 'KG',
        'NCM': '7210.61.00',
        'Origem': 2,
        'Preço': '8,00',
        'Situação': 'Ativo',
        'Estoque': '2.172,5350',
        'Preço de custo': '7,50',
        'Cód. no fornecedor': 'FORN-536\t',
        'Fornecedor': 'Fornecedor Bling Ltda',
        'Estoque máximo': '3.000,0000',
        'Estoque mínimo': '20,0000',
        'Peso líquido (Kg)': '1,23456',
        'Peso bruto (Kg)': '1,50000',
        'GTIN/EAN': '7891234567890',
        'Largura do produto': '100,00',
        'Altura do Produto': '1,00',
        'Profundidade do produto': '10,00',
        'Produto Variação': 'Variação',
        'Tipo do item': 'Matéria-Prima',
        'CEST': '08.021.00',
        'Unidade de Medida': 'Milímetro',
        'Categoria do produto': 'Chapas',
        'Marca': 'Marca preservada',
    }
    row.update(overrides)
    return row


class BlingParserTests(TestCase):
    @staticmethod
    def xls_workbook():
        sheet = MagicMock()
        sheet.nrows = 2
        sheet.row_values.side_effect = [
            ['ID', 'Código', 'Descrição', 'Preço', 'Estoque'],
            [1, 'P-1', 'Produto', '10,00', '2,0000'],
        ]
        workbook = MagicMock()
        workbook.sheet_by_index.return_value = sheet
        return workbook

    @patch('xlrd.open_workbook')
    def test_xls_workbook_corruption_retries_in_tolerant_mode(self, open_workbook):
        workbook = self.xls_workbook()
        open_workbook.side_effect = [
            CompDocError('Workbook corruption: seen[2] == 4'),
            workbook,
        ]

        with self.assertLogs('services.utils_product_import', level='WARNING'):
            rows = read_spreadsheet(b'xls-content', 'produtos.xls')

        self.assertEqual(rows[0]['Código'], 'P-1')
        self.assertEqual(open_workbook.call_args_list, [
            call(file_contents=b'xls-content', logfile=ANY),
            call(file_contents=b'xls-content', logfile=ANY, ignore_workbook_corruption=True),
        ])

    @patch('xlrd.open_workbook')
    def test_xls_unrelated_compound_document_error_is_not_ignored(self, open_workbook):
        open_workbook.side_effect = CompDocError('Not an OLE2 compound document')

        with self.assertRaisesMessage(CompDocError, 'Not an OLE2 compound document'):
            read_spreadsheet(b'invalid', 'produtos.xls')

        open_workbook.assert_called_once_with(file_contents=b'invalid', logfile=ANY)

    @patch('xlrd.open_workbook')
    def test_valid_xls_uses_only_strict_read(self, open_workbook):
        open_workbook.return_value = self.xls_workbook()

        rows = read_spreadsheet(b'valid-xls', 'produtos.xls')

        self.assertEqual(rows[0]['ID'], 1)
        open_workbook.assert_called_once_with(file_contents=b'valid-xls', logfile=ANY)

    def test_form_rejects_removed_operation(self):
        form = ProductImportForm(
            data={'operation_type': 'CATALOG'},
            files={'file': SimpleUploadedFile('produtos.xls', b'xls')},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('operation_type', form.errors)

    def test_form_accepts_supported_bling_extensions(self):
        for extension in ('csv', 'xlsx', 'xls'):
            with self.subTest(extension=extension):
                form = ProductImportForm(
                    data={'operation_type': 'BLING'},
                    files={'file': SimpleUploadedFile(f'produtos.{extension}', b'conteudo')},
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_brazilian_decimal_and_complete_mapping(self):
        self.assertEqual(str(decimal_from_brazilian('2.172,5350')), '2172.5350')
        content = make_bling_xlsx([sample_row()])

        parsed = parse_bling_rows(content, 'produtos.xlsx')[0]

        self.assertEqual(parsed['bling_id'], 16691171492)
        self.assertEqual(parsed['bling_code'], '536')
        self.assertEqual(parsed['supplier_code'], 'FORN-536')
        self.assertEqual(parsed['stock'], '2172.5350')
        self.assertEqual(parsed['unit_type'], Product.UnitType.QUILO)
        self.assertEqual(parsed['type'], Product.Type.MATERIA_PRIMA)
        self.assertEqual(parsed['ncm'], '72106100')
        self.assertEqual(parsed['cest'], '0802100')
        self.assertEqual(parsed['width'], '10.00')
        self.assertEqual(parsed['external_data']['bling']['Marca'], 'Marca preservada')
        self.assertEqual(parsed['errors'], [])

    def test_duplicate_names_are_allowed_for_distinct_external_ids(self):
        Product.objects.create(name='Mesmo nome', bling_id=1, bling_code='A')
        Product.objects.create(name='Mesmo nome', bling_id=2, bling_code='B')
        self.assertEqual(Product.objects.filter(name='Mesmo nome').count(), 2)


class BlingImportFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='manager-import',
            password='password123',
            role=User.Roles.MANAGER,
        )
        self.client.force_login(self.user)
        self.url = reverse('product_import')

    def upload_preview(self, rows, filename='bling.xlsx', nonce=b''):
        upload = SimpleUploadedFile(
            filename,
            make_bling_xlsx(rows) + nonce,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self.client.post(self.url, {
            'action': 'preview',
            'operation_type': 'BLING',
            'file': upload,
        })
        history = ImportHistory.objects.latest('created_at')
        self.assertRedirects(response, reverse('product_import_review', args=[history.pk]))
        return history

    def confirm(self, history, **data):
        return self.client.post(reverse('product_import_review', args=[history.pk]), {
            'action': 'confirm',
            **data,
        })

    def test_import_page_exposes_only_bling_flow(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'Importação completa do Bling')
        self.assertNotContains(response, 'Gestão de catálogo')
        self.assertNotContains(response, 'Movimentação de estoque')
        self.assertNotContains(response, 'Modelo CSV')

    def test_forged_legacy_operation_is_rejected_without_writes(self):
        upload = SimpleUploadedFile(
            'bling.xlsx',
            make_bling_xlsx([sample_row()]),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(self.url, {
            'action': 'preview',
            'operation_type': 'CATALOG',
            'file': upload,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Somente a importação completa do Bling está disponível.')
        self.assertFalse(ImportHistory.objects.exists())
        self.assertFalse(Product.objects.exists())

    def test_preview_does_not_write_and_confirmation_imports_all_data(self):
        history = self.upload_preview([sample_row()])

        self.assertEqual(history.status, ImportHistory.Status.PRONTA)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(history.preview_data['summary']['create'], 1)

        response = self.confirm(history)

        self.assertRedirects(response, reverse('product_list'))
        product = Product.objects.get(bling_id=16691171492)
        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.CONCLUIDA)
        self.assertEqual(product.code, 'FORN-536')
        self.assertEqual(product.current_stock, decimal_from_brazilian('2.172,5350'))
        self.assertEqual(product.supplier.name, 'Fornecedor Bling Ltda')
        self.assertEqual(product.category.name, 'Chapas')
        self.assertEqual(Supplier.objects.count(), 1)
        self.assertEqual(ProductCategory.objects.count(), 1)
        movement = StockMovement.objects.get(product=product)
        self.assertEqual(movement.quantity, decimal_from_brazilian('2.172,5350'))
        self.assertEqual(movement.saldo_apos, decimal_from_brazilian('2.172,5350'))
        self.assertEqual(movement.import_history, history)
        self.assertEqual(product.registration_source, Product.RegistrationSource.BLING)
        self.assertEqual(product.created_by, self.user)
        self.assertEqual(product.source_import, history)
        self.assertEqual(product.last_import, history)
        item = ImportItem.objects.get(import_history=history)
        stock_change = next(change for change in item.changes if change['campo'] == 'current_stock')
        self.assertEqual(stock_change['valor_anterior'], '0')
        self.assertEqual(stock_change['valor_novo'], '2172.5350')
        self.assertIsNotNone(history.completed_at)

    def test_conflict_blocks_confirmation(self):
        Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])

        self.assertEqual(history.status, ImportHistory.Status.BLOQUEADA)
        self.assertEqual(history.preview_data['summary']['conflicts'], 1)
        preview_response = self.client.get(reverse('product_import_review', args=[history.pk]))
        self.assertContains(preview_response, 'Resolva 1 pendência(s) para continuar')
        self.assertContains(preview_response, 'Confirmar importação')
        self.assertContains(preview_response, 'id="confirm-import"')

        response = self.confirm(history)

        self.assertEqual(response.status_code, 302)
        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.BLOQUEADA)
        self.assertFalse(Product.objects.filter(bling_id=16691171492).exists())

    def test_ignored_conflict_allows_confirmation_and_is_audited(self):
        existing = Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])

        response = self.confirm(history, ignored_rows='2')

        self.assertRedirects(response, reverse('product_list'))
        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.CONCLUIDA)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Product.objects.get(), existing)
        ignored = ImportItem.objects.get(import_history=history)
        self.assertEqual(ignored.action, 'Ignorado')
        self.assertIsNone(ignored.product)

    def test_conflict_can_be_created_with_alternative_code(self):
        Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])

        response = self.confirm(history, resolution_2='CREATE', local_code_2='BLING-536')

        self.assertRedirects(response, reverse('product_list'))
        imported = Product.objects.get(bling_id=16691171492)
        self.assertEqual(imported.code, 'BLING-536')

    def test_duplicate_local_codes_inside_spreadsheet_require_resolution(self):
        first = sample_row(**{
            'ID': 1,
            'Código': '432',
            'Cód. no fornecedor': '297',
            'Descrição': 'Primeiro produto',
        })
        second = sample_row(**{
            'ID': 2,
            'Código': '297',
            'Cód. no fornecedor': '',
            'Descrição': 'Segundo produto',
        })

        history = self.upload_preview([first, second])

        self.assertEqual(history.status, ImportHistory.Status.BLOQUEADA)
        self.assertEqual(history.preview_data['summary']['create'], 1)
        self.assertEqual(history.preview_data['summary']['pending'], 1)
        pending = next(row for row in history.preview_data['rows'] if row['action'] == 'PENDENTE')
        self.assertEqual(pending['row_number'], 3)
        self.assertIn('também será usado pela linha 2', pending['details'])

        response = self.confirm(history, ignored_rows='3')

        self.assertRedirects(response, reverse('product_list'))
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Product.objects.get().code, '297')

    def test_conflict_can_be_linked_to_selected_product(self):
        Product.objects.create(name='Código ocupado', code='536')
        target = Product.objects.create(name='Produto correto', code='TARGET')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])

        response = self.confirm(history, resolution_2='LINK', product_id_2=str(target.pk))

        self.assertRedirects(response, reverse('product_list'))
        target.refresh_from_db()
        self.assertEqual(target.bling_id, 16691171492)
        self.assertEqual(target.name, 'Produto Bling')

    def test_saving_decision_persists_it_and_releases_confirmation(self):
        Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])
        review_url = reverse('product_import_review', args=[history.pk])

        response = self.client.post(review_url, {
            'action': 'save_decisions',
            'resolution_2': 'CREATE',
            'local_code_2': 'BLING-536',
        }, follow=True)

        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.PRONTA)
        self.assertEqual(history.preview_data['decisions']['2']['decision'], 'CREATE')
        self.assertEqual(history.preview_data['decisions']['2']['local_code'], 'BLING-536')
        self.assertEqual(history.preview_data['summary']['pending'], 0)
        self.assertEqual(history.preview_data['summary']['resolved'], 1)
        self.assertContains(response, 'Revisão validada')
        self.assertContains(response, 'data-submit-action="confirm"')

    def test_review_form_uses_hidden_action_for_direct_confirmation(self):
        Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])

        response = self.client.get(reverse('product_import_review', args=[history.pk]))

        self.assertContains(response, 'id="review-form" data-preserve-submit-button="true"')
        self.assertContains(response, 'type="hidden" name="action" id="review-action"')
        self.assertContains(response, 'id="confirm-import"')
        self.assertNotContains(response, 'data-submit-action="save_decisions"')

    def test_incomplete_direct_confirmation_preserves_completed_decisions(self):
        Product.objects.create(name='Código ocupado 1', code='536')
        Product.objects.create(name='Código ocupado 2', code='537')
        history = self.upload_preview([
            sample_row(**{'Cód. no fornecedor': '', 'Código': '536', 'ID': 1}),
            sample_row(**{'Cód. no fornecedor': '', 'Código': '537', 'ID': 2}),
        ])

        response = self.confirm(history, ignored_rows='2')

        self.assertRedirects(response, reverse('product_import_review', args=[history.pk]))
        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.BLOQUEADA)
        self.assertEqual(history.preview_data['decisions']['2']['decision'], 'IGNORE')
        self.assertEqual(history.preview_data['summary']['pending'], 1)
        self.assertEqual(Product.objects.count(), 2)

    def test_pending_preview_can_be_discarded(self):
        history = self.upload_preview([sample_row()])

        response = self.client.post(reverse('product_import_review', args=[history.pk]), {'action': 'discard'})

        self.assertRedirects(response, self.url)
        self.assertFalse(ImportHistory.objects.filter(pk=history.pk).exists())

    def test_revalidation_preserves_ignored_decision(self):
        Product.objects.create(name='Outro produto', code='536')
        history = self.upload_preview([sample_row(**{'Cód. no fornecedor': ''})])
        review_url = reverse('product_import_review', args=[history.pk])
        self.client.post(review_url, {'action': 'save_decisions', 'ignored_rows': '2'})

        response = self.client.post(review_url, {'action': 'revalidate'})

        self.assertRedirects(response, review_url)
        history.refresh_from_db()
        self.assertEqual(history.status, ImportHistory.Status.PRONTA)
        self.assertEqual(history.preview_data['decisions']['2']['decision'], 'IGNORE')
        self.assertEqual(history.preview_data['summary']['ignored'], 1)

    def test_old_preview_query_redirects_to_review_page(self):
        history = self.upload_preview([sample_row()])

        response = self.client.get(f'{self.url}?preview={history.pk}')

        self.assertRedirects(response, reverse('product_import_review', args=[history.pk]))

    def test_second_file_updates_by_bling_id_and_adjusts_only_delta(self):
        history = self.upload_preview([sample_row(**{'Estoque': '10,0000'})], 'bling-1.xlsx')
        self.confirm(history)

        second = sample_row(**{'Estoque': '12,5000', 'Preço': '9,00'})
        second_history = self.upload_preview([second], 'bling-2.xlsx')
        self.assertEqual(second_history.preview_data['summary']['update'], 1)
        self.confirm(second_history)

        product = Product.objects.get(bling_id=16691171492)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(product.current_stock, decimal_from_brazilian('12,5000'))
        self.assertEqual(product.default_unit_price, decimal_from_brazilian('9,00'))
        self.assertEqual(StockMovement.objects.filter(product=product).count(), 2)
        self.assertEqual(
            StockMovement.objects.filter(product=product).latest('created_at').quantity,
            decimal_from_brazilian('2,5000'),
        )
        self.assertEqual(product.registration_source, Product.RegistrationSource.BLING)
        self.assertEqual(product.source_import, history)
        self.assertEqual(product.last_import, second_history)
        price_change = next(
            change for change in ImportItem.objects.get(import_history=second_history).changes
            if change['campo'] == 'default_unit_price'
        )
        self.assertEqual(price_change['valor_anterior'], '8.00')
        self.assertEqual(price_change['valor_novo'], '9.00')

    def test_identical_update_is_ignored_and_does_not_replace_last_import(self):
        first = self.upload_preview([sample_row()], 'bling-original.xlsx')
        self.confirm(first)
        product = Product.objects.get(bling_id=16691171492)

        second = self.upload_preview([sample_row()], 'bling-identical.xlsx', nonce=b'nonce')
        self.confirm(second)

        product.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(product.last_import, first)
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(ImportItem.objects.get(import_history=second).action, 'Ignorado')

    def test_product_and_import_pages_expose_audit_links(self):
        history = self.upload_preview([sample_row()])
        self.confirm(history)
        product = Product.objects.get(bling_id=16691171492)

        listing = self.client.get(reverse('product_list'), {'source': 'BLING'})
        self.assertContains(listing, 'Bling')
        self.assertContains(listing, f'Última: #{history.pk}')
        product_history = self.client.get(reverse('product_stock_history', args=[product.pk]))
        self.assertContains(product_history, 'Proveniência do cadastro')
        self.assertContains(product_history, 'Alterações por importação')
        import_detail = self.client.get(reverse('product_import_history_detail', args=[history.pk]))
        self.assertContains(import_detail, 'Produtos impactados')
        self.assertContains(import_detail, 'Ver ')


class ProductAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='catalog-manager', password='password123', role=User.Roles.MANAGER,
        )
        self.client.force_login(self.user)

    def test_manual_creation_records_origin_user_and_dates(self):
        response = self.client.post(reverse('product_create'), {
            'name': 'Produto manual', 'unit_type': Product.UnitType.UNIDADE,
            'format': Product.Format.SIMPLES, 'type': Product.Type.PRODUTO,
            'preco_custo': '0', 'preco_custo_total': '0',
            'preco_venda_total': '0', 'default_unit_price': '0',
            'current_stock': '0', 'min_stock': '0', 'max_stock': '0',
            'origem_mercadoria': '0', 'aliquota_ibpt_fed': '0',
            'aliquota_ibpt_est': '0', 'aliquota_ibpt_mun': '0',
        })
        self.assertRedirects(response, reverse('product_list'))
        product = Product.objects.get(name='Produto manual')
        self.assertEqual(product.registration_source, Product.RegistrationSource.MANUAL)
        self.assertEqual(product.created_by, self.user)
        self.assertIsNotNone(product.created_at)
        self.assertIsNotNone(product.updated_at)

    def test_legacy_catalog_history_remains_readable(self):
        history = ImportHistory.objects.create(
            user=self.user,
            filename='catalogo-antigo.csv',
            operation_type=ImportHistory.OperationType.CATALOG,
            status=ImportHistory.Status.CONCLUIDA,
        )

        listing = self.client.get(reverse('product_import_history'))
        detail = self.client.get(reverse('product_import_history_detail', args=[history.pk]))

        self.assertContains(listing, 'Gestão de Catálogo')
        self.assertContains(detail, 'Gestão de Catálogo')
