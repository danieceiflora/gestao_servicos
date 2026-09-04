from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField, Count
from django.db.models.functions import Coalesce
from django.forms import inlineformset_factory
import hashlib
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from .models import (
    Product, StockMovement, ImportHistory, ImportItem, ProductCategory,
    Supplier, PurchaseInvoice, PurchaseInvoiceItem,
)
from integracoes.models import SystemConfig
from .forms import (
    ProductForm, StockMovementForm, ProductImportForm, ProductCompositionFormSet, ProductVariantFormSet,
    PurchaseInvoiceForm, PurchaseInvoiceItemForm, PurchaseInvoiceItemFormSet, PurchaseInvoiceXMLUploadForm,
)
from .utils_nfe_import import (
    parse_nfe_xml, match_products, NFeXMLParseError,
    find_supplier_by_cnpj, get_or_create_supplier_from_xml, create_missing_products,
    _update_product_fiscal,
)
from .utils_product_import import parse_bling_rows

class ManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_manager

def is_manager(user):
    return user.is_authenticated and user.is_manager

@login_required
def get_product_prices(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse({
        'preco_custo': float(product.preco_custo),
        'default_unit_price': float(product.default_unit_price),
        'current_stock': float(product.current_stock),
        'min_stock': float(product.min_stock),
        'max_stock': float(product.max_stock),
        'unit_type': product.get_unit_type_display(),
    })

@login_required
def search_materia_prima(request):
    q = request.GET.get('q', '')
    products = Product.objects.filter(
        Q(name__icontains=q) | Q(code__icontains=q),
        type=Product.Type.MATERIA_PRIMA,
        is_active=True
    )[:10]
    
    results = [
        {'id': p.id, 'text': f"{p.name} ({p.code or 'S/C'})"} 
        for p in products
    ]
    return JsonResponse({'results': results})

class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'services/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'last_import').all()
        search = self.request.GET.get('search')
        category = self.request.GET.get('category')
        status = self.request.GET.get('status')
        source = self.request.GET.get('source')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search)
            )
        if category:
            queryset = queryset.filter(category_id=category)
        if source in Product.RegistrationSource.values:
            queryset = queryset.filter(registration_source=source)
        if status == 'low':
            queryset = queryset.filter(current_stock__gt=0, current_stock__lte=F('min_stock'))
        elif status == 'zero':
            queryset = queryset.filter(current_stock__lte=0)
        elif status == 'ok':
            queryset = queryset.filter(current_stock__gt=F('min_stock'))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = Product.objects.all()
        valor_total = qs.aggregate(
            total=Coalesce(Sum(ExpressionWrapper(
                F('current_stock') * F('preco_custo'),
                output_field=DecimalField()
            )), Decimal('0'))
        )['total']
        context['kpi_valor_total'] = valor_total
        context['kpi_total_skus'] = qs.count()
        context['kpi_abaixo_minimo'] = qs.filter(current_stock__gt=0, current_stock__lte=F('min_stock'), min_stock__gt=0).count()
        context['kpi_zerados'] = qs.filter(current_stock__lte=0).count()
        context['categories'] = ProductCategory.objects.all().order_by('name')
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_source'] = self.request.GET.get('source', '')
        context['registration_sources'] = Product.RegistrationSource.choices
        return context

class ProductCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tax_regime'] = SystemConfig.load().tax_regime
        if self.request.POST:
            context['composition_formset'] = ProductCompositionFormSet(self.request.POST)
            context['variant_formset'] = ProductVariantFormSet(self.request.POST)
        else:
            context['composition_formset'] = ProductCompositionFormSet()
            context['variant_formset'] = ProductVariantFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        composition_formset = context['composition_formset']
        variant_formset = context['variant_formset']

        with transaction.atomic():
            form.instance.registration_source = Product.RegistrationSource.MANUAL
            form.instance.created_by = self.request.user
            self.object = form.save()
            if form.instance.format == 'COM_COMPOSICAO':
                if composition_formset.is_valid():
                    composition_formset.instance = self.object
                    composition_formset.save()
                else:
                    return self.form_invalid(form)
            elif form.instance.format == 'COM_VARIACOES':
                if variant_formset.is_valid():
                    variant_formset.instance = self.object
                    variant_formset.save()
                else:
                    return self.form_invalid(form)

        messages.success(self.request, "Produto cadastrado com sucesso.")
        return redirect(self.success_url)

class ProductUpdateView(LoginRequiredMixin, ManagerRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tax_regime'] = SystemConfig.load().tax_regime
        if self.request.POST:
            context['composition_formset'] = ProductCompositionFormSet(self.request.POST, instance=self.object)
            context['variant_formset'] = ProductVariantFormSet(self.request.POST, instance=self.object)
        else:
            context['composition_formset'] = ProductCompositionFormSet(instance=self.object)
            context['variant_formset'] = ProductVariantFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        composition_formset = context['composition_formset']
        variant_formset = context['variant_formset']

        with transaction.atomic():
            self.object = form.save()
            if form.instance.format == 'COM_COMPOSICAO':
                if composition_formset.is_valid():
                    composition_formset.instance = self.object
                    composition_formset.save()
                else:
                    return self.form_invalid(form)
            elif form.instance.format == 'COM_VARIACOES':
                if variant_formset.is_valid():
                    variant_formset.instance = self.object
                    variant_formset.save()
                else:
                    return self.form_invalid(form)

        messages.success(self.request, "Produto atualizado com sucesso.")
        return redirect(self.success_url)

class StockMovementCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = 'services/stock_movement_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        movement = form.save(commit=False)
        product = movement.product
        
        if movement.movement_type == StockMovement.MovementType.ENTRADA:
            product.increase_stock(
                movement.quantity,
                user=self.request.user,
                reason=movement.reason,
                notes=movement.notes,
                service_order=movement.service_order
            )
        else:
            product.reduce_stock(
                movement.quantity,
                user=self.request.user,
                reason=movement.reason,
                notes=movement.notes,
                service_order=movement.service_order
            )
        
        messages.success(self.request, f"Movimentação de {movement.get_movement_type_display()} realizada com sucesso.")
        return redirect(self.success_url)

@login_required
def product_stock_history(request, pk):
    from datetime import datetime, date
    product = get_object_or_404(Product, pk=pk)
    movements = product.movements.all().select_related('user', 'service_order', 'import_history')
    import_items = product.importitem_set.filter(is_error=False).exclude(changes=[]).select_related(
        'import_history', 'import_history__user'
    ).order_by('-import_history__completed_at', '-created_at')

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    mov_type = request.GET.get('type')

    if date_from:
        try:
            movements = movements.filter(created_at__date__gte=date_from)
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            movements = movements.filter(created_at__date__lte=date_to)
        except (ValueError, TypeError):
            pass
    if mov_type in ('ENTRADA', 'SAIDA'):
        movements = movements.filter(movement_type=mov_type)

    # Dados para gráfico (últimos 30 lançamentos cronológicos)
    chart_qs = list(product.movements.order_by('created_at').values(
        'created_at', 'movement_type', 'quantity', 'saldo_apos'
    )[:60])
    chart_labels = [m['created_at'].strftime('%d/%m %H:%M') for m in chart_qs]
    chart_data = [float(m['saldo_apos']) if m['saldo_apos'] is not None else None for m in chart_qs]

    context = {
        'product': product,
        'movements': movements,
        'date_from': date_from or '',
        'date_to': date_to or '',
        'selected_type': mov_type or '',
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'import_items': import_items,
    }
    return render(request, 'services/product_stock_history.html', context)

def _normalized_product_name(value):
    return ' '.join(str(value or '').casefold().split())


def _build_bling_preview(rows, decisions=None):
    decisions = decisions or {}
    products = list(Product.objects.select_related('supplier').all())
    products_by_id = {product.pk: product for product in products}
    by_bling_id = {product.bling_id: product for product in products if product.bling_id is not None}
    by_bling_code = {product.bling_code: product for product in products if product.bling_code}
    by_code = {product.code: product for product in products if product.code}
    by_barcode = {}
    for product in products:
        if product.barcode:
            by_barcode.setdefault(product.barcode, []).append(product)

    seen_bling_ids = set()
    seen_bling_codes = set()
    matched_product_ids = set()
    reserved_local_codes = {}
    existing_suppliers = {_normalized_product_name(name) for name in Supplier.objects.values_list('name', flat=True)}
    existing_categories = {_normalized_product_name(name) for name in ProductCategory.objects.values_list('name', flat=True)}
    new_suppliers = {
        _normalized_product_name(row.get('supplier_name'))
        for row in rows if row.get('supplier_name') and _normalized_product_name(row['supplier_name']) not in existing_suppliers
    }
    new_categories = {
        _normalized_product_name(row.get('category_name'))
        for row in rows if row.get('category_name') and _normalized_product_name(row['category_name']) not in existing_categories
    }
    preview_rows = []
    summary = {
        'total': len(rows), 'create': 0, 'update': 0, 'conflicts': 0,
        'errors': 0, 'movements': 0, 'suppliers': len(new_suppliers),
        'categories': len(new_categories), 'ignored': 0, 'pending': 0,
        'resolved': 0,
    }

    for row in rows:
        result = dict(row)
        structural_errors = list(row.get('errors') or [])
        problems = list(structural_errors)
        product = None
        match_reason = ''
        decision = decisions.get(str(row['row_number']), {'decision': 'IMPORT'})
        decision_type = decision.get('decision', 'IMPORT')

        if row.get('bling_id') in seen_bling_ids:
            problems.append('ID do Bling repetido na planilha.')
        if row.get('bling_code') in seen_bling_codes:
            problems.append('Código do Bling repetido na planilha.')
        if row.get('bling_id') is not None:
            seen_bling_ids.add(row['bling_id'])
        if row.get('bling_code'):
            seen_bling_codes.add(row['bling_code'])

        if not problems:
            product = by_bling_id.get(row.get('bling_id'))
            if product:
                match_reason = 'ID do Bling'

        if not product and not problems and row.get('bling_code'):
            product = by_bling_code.get(row['bling_code'])
            if product:
                match_reason = 'Código do Bling'

        if not product and not problems and row.get('barcode'):
            barcode_matches = by_barcode.get(row['barcode'], [])
            if len(barcode_matches) == 1:
                product = barcode_matches[0]
                match_reason = 'GTIN/EAN'
            elif len(barcode_matches) > 1:
                problems.append('GTIN/EAN corresponde a mais de um produto local.')

        supplier_code = row.get('supplier_code')
        if not product and not problems and supplier_code and supplier_code in by_code:
            candidate = by_code[supplier_code]
            if _normalized_product_name(candidate.name) == _normalized_product_name(row.get('name')):
                product = candidate
                match_reason = 'código do fornecedor e descrição'
            else:
                problems.append(f'O código local {supplier_code} pertence a outro produto ({candidate.name}).')

        local_code = None
        if not product and not problems:
            local_code = supplier_code or row.get('bling_code')
            occupied = by_code.get(local_code)
            if occupied:
                problems.append(f'O código local {local_code} já pertence a {occupied.name}.')
            elif local_code in reserved_local_codes:
                problems.append(
                    f'O código local {local_code} também será usado pela linha '
                    f'{reserved_local_codes[local_code]} desta planilha.'
                )

        automatic_problems = list(problems)
        automatic_product = product
        automatic_local_code = local_code

        if decision_type == 'IGNORE':
            result.update({
                'action': 'IGNORAR',
                'base_action': 'ERRO' if structural_errors else ('CONFLITO' if automatic_problems else ('ATUALIZAR' if product else 'CRIAR')),
                'details': decision.get('reason') or ('Ignorado pelo usuário.'),
                'product_id': None,
                'local_code': automatic_local_code,
                'stock_delta': '0',
                'resolution': 'IGNORE',
                'requires_resolution': bool(automatic_problems),
            })
            summary['ignored'] += 1
            preview_rows.append(result)
            continue

        if decision_type == 'CREATE' and not structural_errors:
            product = None
            problems = []
            local_code = str(decision.get('local_code') or '').strip()
            if not local_code:
                problems.append('Informe um código local para criar o produto.')
            elif local_code in by_code:
                problems.append(f'O código local {local_code} já pertence a {by_code[local_code].name}.')
            existing_external = by_bling_id.get(row.get('bling_id')) or by_bling_code.get(row.get('bling_code'))
            if existing_external:
                problems.append(f'O identificador do Bling já pertence a {existing_external.name}.')
            match_reason = 'decisão manual: importar como novo'
        elif decision_type == 'LINK' and not structural_errors:
            problems = []
            try:
                product = products_by_id.get(int(decision.get('product_id')))
            except (TypeError, ValueError):
                product = None
            if not product:
                problems.append('Selecione um produto local válido para vincular.')
            else:
                if product.bling_id not in (None, row.get('bling_id')):
                    problems.append(f'{product.name} já está vinculado a outro ID do Bling.')
                if product.bling_code not in (None, '', row.get('bling_code')):
                    problems.append(f'{product.name} já está vinculado a outro código do Bling.')
                local_code = product.code
                match_reason = 'decisão manual: produto vinculado'

        if not product and not problems and local_code in reserved_local_codes:
            problems.append(
                f'O código local {local_code} também será usado pela linha '
                f'{reserved_local_codes[local_code]} desta planilha.'
            )

        if product and product.pk in matched_product_ids:
            problems.append(f'Mais de uma linha foi associada ao produto local {product.name}.')
        if product and not problems:
            matched_product_ids.add(product.pk)

        if problems:
            result.update({
                'action': 'PENDENTE',
                'base_action': 'ERRO' if structural_errors else 'CONFLITO',
                'details': ' '.join(problems),
                'product_id': None,
                'local_code': local_code,
                'stock_delta': '0',
                'resolution': decision_type if decision_type in {'CREATE', 'LINK'} else '',
                'resolution_product_id': product.pk if product else decision.get('product_id'),
                'resolution_local_code': decision.get('local_code') or f"BLING-{row.get('bling_code')}",
                'requires_resolution': True,
            })
            summary['errors' if structural_errors else 'conflicts'] += 1
            summary['pending'] += 1
        elif product:
            delta = Decimal(row['stock']) - product.current_stock
            result.update({
                'action': 'ATUALIZAR',
                'base_action': 'CONFLITO' if automatic_problems else 'ATUALIZAR',
                'details': f'Correspondência por {match_reason}: {product.name}.',
                'product_id': product.pk,
                'local_code': product.code,
                'stock_delta': str(delta),
                'resolution': decision_type if decision_type == 'LINK' else '',
                'resolution_product_id': product.pk if decision_type == 'LINK' else None,
                'resolution_local_code': '',
                'requires_resolution': bool(automatic_problems),
            })
            summary['update'] += 1
            if automatic_problems:
                summary['resolved'] += 1
            if delta:
                summary['movements'] += 1
        else:
            desired_stock = Decimal(row['stock'])
            result.update({
                'action': 'CRIAR',
                'base_action': 'CONFLITO' if automatic_problems else 'CRIAR',
                'details': f'Novo produto com código local {local_code}.',
                'product_id': None,
                'local_code': local_code,
                'stock_delta': str(desired_stock),
                'resolution': decision_type if decision_type == 'CREATE' else '',
                'resolution_product_id': None,
                'resolution_local_code': local_code,
                'requires_resolution': bool(automatic_problems),
            })
            summary['create'] += 1
            if automatic_problems:
                summary['resolved'] += 1
            if local_code:
                reserved_local_codes[local_code] = row['row_number']
            if desired_stock:
                summary['movements'] += 1

        preview_rows.append(result)

    summary['blocked'] = bool(summary['pending'])
    summary['selected'] = summary['create'] + summary['update']
    return {'rows': preview_rows, 'summary': summary}


def _get_or_create_supplier(name):
    if not name:
        return None, False
    supplier = Supplier.objects.filter(name__iexact=name).first()
    if supplier:
        return supplier, False
    return Supplier.objects.create(name=name, client_type='PJ'), True


def _get_or_create_category(name):
    if not name:
        return None, False
    category = ProductCategory.objects.filter(name__iexact=name).first()
    if category:
        return category, False
    return ProductCategory.objects.create(name=name), True


def _audit_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'pk'):
        return str(value)
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _change(field, description, old, new):
    if isinstance(old, Decimal) or isinstance(new, Decimal):
        try:
            if Decimal(str(old)) == Decimal(str(new)):
                return None
        except Exception:
            pass
    old_value, new_value = _audit_value(old), _audit_value(new)
    if old_value == new_value:
        return None
    return {
        'campo': field,
        'descricao': description,
        'valor_anterior': old_value,
        'valor_novo': new_value,
    }


def _apply_bling_import(import_history, user):
    source_rows = import_history.preview_data.get('source_rows') or []
    decisions = import_history.preview_data.get('decisions') or {}
    preview = _build_bling_preview(source_rows, decisions)
    if preview['summary']['blocked']:
        import_history.status = ImportHistory.Status.BLOQUEADA
        import_history.preview_data = {'source_rows': source_rows, 'decisions': decisions, **preview}
        import_history.save(update_fields=['status', 'preview_data'])
        return None, preview

    created_count = updated_count = movements_count = 0
    suppliers_created = categories_created = 0

    for row in preview['rows']:
        if row['action'] == 'IGNORAR':
            ImportItem.objects.create(
                import_history=import_history,
                row_number=row['row_number'],
                identifier=row['bling_code'] or row['name'],
                action='Ignorado',
                details=row['details'] or 'Linha ignorada pelo usuário durante a revisão.',
            )
            continue

        supplier, supplier_created = _get_or_create_supplier(row.get('supplier_name'))
        category, category_created = _get_or_create_category(row.get('category_name'))
        suppliers_created += int(supplier_created)
        categories_created += int(category_created)

        product = Product.objects.filter(pk=row.get('product_id')).first() if row.get('product_id') else None
        created = product is None
        if created:
            product = Product(code=row['local_code'], current_stock=Decimal('0'))

        old_stock = product.current_stock
        previous_last_import_id = product.last_import_id
        field_values = {
            'name': ('Nome', row['name']),
            'bling_id': ('ID no Bling', row['bling_id']),
            'bling_code': ('Código no Bling', row['bling_code']),
            'supplier_code': ('Código no fornecedor', row.get('supplier_code') or None),
            'supplier': ('Fornecedor', supplier),
            'category': ('Categoria', category),
            'barcode': ('GTIN/EAN', row.get('barcode') or None),
            'unit_type': ('Unidade', row['unit_type']),
            'type': ('Tipo', row['type']),
            'default_unit_price': ('Preço de venda', Decimal(row['default_unit_price'])),
            'preco_custo': ('Preço de custo', Decimal(row['preco_custo'])),
            'min_stock': ('Estoque mínimo', Decimal(row['min_stock'])),
            'max_stock': ('Estoque máximo', Decimal(row['max_stock'])),
            'weight': ('Peso bruto', Decimal(row['weight'])),
            'net_weight': ('Peso líquido', Decimal(row['net_weight'])),
            'width': ('Largura', Decimal(row['width'])),
            'height': ('Altura', Decimal(row['height'])),
            'depth': ('Profundidade', Decimal(row['depth'])),
            'ncm': ('NCM', row.get('ncm')),
            'cest': ('CEST', row.get('cest')),
            'origem_mercadoria': ('Origem da mercadoria', row['origem_mercadoria']),
            'is_active': ('Ativo', row['is_active']),
        }
        changes = []
        for field, (description, new_value) in field_values.items():
            item = _change(field, description, None if created else getattr(product, field), new_value)
            if item:
                changes.append(item)
        existing_external = product.external_data if isinstance(product.external_data, dict) else {}
        product.name = row['name']
        product.bling_id = row['bling_id']
        product.bling_code = row['bling_code']
        product.supplier_code = row.get('supplier_code') or None
        product.supplier = supplier
        product.category = category
        product.barcode = row.get('barcode') or None
        product.unit_type = row['unit_type']
        product.type = row['type']
        product.format = Product.Format.SIMPLES
        product.default_unit_price = Decimal(row['default_unit_price'])
        product.preco_custo = Decimal(row['preco_custo'])
        product.min_stock = Decimal(row['min_stock'])
        product.max_stock = Decimal(row['max_stock'])
        product.weight = Decimal(row['weight'])
        product.net_weight = Decimal(row['net_weight'])
        product.width = Decimal(row['width'])
        product.height = Decimal(row['height'])
        product.depth = Decimal(row['depth'])
        product.ncm = row.get('ncm')
        product.cest = row.get('cest')
        product.origem_mercadoria = row['origem_mercadoria']
        product.is_active = row['is_active']
        product.external_data = {**existing_external, **row['external_data']}
        if created:
            product.registration_source = Product.RegistrationSource.BLING
            product.created_by = user
            product.source_import = import_history
        product.last_import = import_history
        product.save()

        desired_stock = Decimal(row['stock'])
        delta = desired_stock - old_stock
        if delta:
            product.current_stock = desired_stock
            product.save(update_fields=['current_stock'])
            StockMovement.objects.create(
                product=product,
                quantity=abs(delta),
                movement_type=(StockMovement.MovementType.ENTRADA if delta > 0 else StockMovement.MovementType.SAIDA),
                reason=StockMovement.Reason.AJUSTE,
                user=user,
                import_history=import_history,
                notes=f'Ajuste de saldo pela importação Bling ({import_history.filename})',
                saldo_apos=desired_stock,
            )
            movements_count += 1
            changes.append(_change('current_stock', 'Estoque', old_stock, desired_stock))

        if not created and not changes:
            product.last_import_id = previous_last_import_id
            product.save(update_fields=['last_import', 'updated_at'])
            ImportItem.objects.create(
                import_history=import_history, row_number=row['row_number'],
                identifier=row['bling_code'] or row['name'], product=product,
                action='Ignorado', details='Nenhuma alteração detectada.', changes=[],
            )
            continue

        ImportItem.objects.create(
            import_history=import_history,
            row_number=row['row_number'],
            identifier=row['bling_code'] or row['name'],
            product=product,
            action='Criado' if created else 'Atualizado',
            details=f"Dados Bling sincronizados. Estoque: {old_stock} -> {desired_stock}.",
            changes=[item for item in changes if item],
        )
        created_count += int(created)
        updated_count += int(not created)

    import_history.created_count = created_count
    import_history.updated_count = updated_count
    import_history.movements_count = movements_count
    import_history.status = ImportHistory.Status.CONCLUIDA
    import_history.completed_at = timezone.now()
    import_history.errors = ''
    import_history.preview_data = {}
    import_history.save(update_fields=[
        'created_count', 'updated_count', 'movements_count', 'status', 'completed_at', 'errors', 'preview_data'
    ])
    return {
        'created': created_count,
        'updated': updated_count,
        'movements': movements_count,
        'suppliers': suppliers_created,
        'categories': categories_created,
        'ignored': preview['summary']['ignored'],
    }, preview


def _bling_decisions_from_post(request, source_rows):
    ignored_rows = set(request.POST.getlist('ignored_rows'))
    decisions = {}
    for row in source_rows:
        row_key = str(row['row_number'])
        if row_key in ignored_rows:
            decisions[row_key] = {
                'decision': 'IGNORE',
                'reason': 'Linha ignorada pelo usuário durante a revisão.',
            }
            continue

        resolution = request.POST.get(f'resolution_{row_key}', '').upper()
        if resolution == 'CREATE':
            decisions[row_key] = {
                'decision': 'CREATE',
                'local_code': request.POST.get(f'local_code_{row_key}', '').strip(),
            }
        elif resolution == 'LINK':
            decisions[row_key] = {
                'decision': 'LINK',
                'product_id': request.POST.get(f'product_id_{row_key}', '').strip(),
            }
    return decisions


@login_required
@user_passes_test(is_manager)
def product_import_review(request, pk):
    import_history = get_object_or_404(
        ImportHistory,
        pk=pk,
        user=request.user,
        operation_type=ImportHistory.OperationType.BLING,
    )
    if import_history.status == ImportHistory.Status.CONCLUIDA:
        messages.info(request, 'Esta importação já foi concluída.')
        return redirect('product_import_history_detail', pk=import_history.pk)

    source_rows = import_history.preview_data.get('source_rows') or []
    decisions = import_history.preview_data.get('decisions') or {}

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'discard':
            filename = import_history.filename
            import_history.delete()
            messages.success(request, f'Prévia de {filename} descartada. Nenhum produto foi alterado.')
            return redirect('product_import')

        if action in {'save_decisions', 'confirm'}:
            decisions = _bling_decisions_from_post(request, source_rows)

        preview = _build_bling_preview(source_rows, decisions)
        import_history.status = ImportHistory.Status.BLOQUEADA if preview['summary']['blocked'] else ImportHistory.Status.PRONTA
        import_history.preview_data = {'source_rows': source_rows, 'decisions': decisions, **preview}
        import_history.save(update_fields=['status', 'preview_data'])

        if action in {'save_decisions', 'revalidate'}:
            if preview['summary']['blocked']:
                messages.warning(request, f"Ainda existem {preview['summary']['pending']} linha(s) aguardando decisão.")
            else:
                messages.success(request, 'Decisões salvas. A importação está pronta para confirmar.')
            return redirect('product_import_review', pk=import_history.pk)

        if action == 'confirm':
            if preview['summary']['blocked']:
                messages.error(
                    request,
                    f"Ainda existem {preview['summary']['pending']} linha(s) sem uma decisão válida. "
                    'As escolhas preenchidas foram preservadas.'
                )
                return redirect('product_import_review', pk=import_history.pk)
            try:
                with transaction.atomic():
                    locked_history = ImportHistory.objects.select_for_update().get(pk=import_history.pk)
                    result, refreshed_preview = _apply_bling_import(locked_history, request.user)
                    if result is None:
                        messages.error(request, 'A conciliação mudou. Revise as pendências antes de confirmar.')
                        return redirect('product_import_review', pk=import_history.pk)
            except Exception as exc:
                messages.error(request, f'Erro ao confirmar a importação do Bling: {exc}')
                return redirect('product_import_review', pk=import_history.pk)

            messages.success(
                request,
                f"Importação concluída: {result['created']} criados, {result['updated']} atualizados, "
                f"{result['ignored']} ignorados e {result['movements']} ajustes de estoque."
            )
            return redirect('product_list')

    preview = _build_bling_preview(source_rows, decisions)
    if import_history.preview_data.get('summary') != preview['summary']:
        import_history.status = ImportHistory.Status.BLOQUEADA if preview['summary']['blocked'] else ImportHistory.Status.PRONTA
        import_history.preview_data = {'source_rows': source_rows, 'decisions': decisions, **preview}
        import_history.save(update_fields=['status', 'preview_data'])

    return render(request, 'services/product_import_review.html', {
        'import_obj': import_history,
        'preview': preview,
        'products': Product.objects.order_by('name', 'code'),
    })

@login_required
@user_passes_test(is_manager)
def product_import(request):
    if request.method == 'POST':
        form = ProductImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            filename = file.name
            
            # --- PREVENÇÃO DE DUPLICIDADE (CHECKSUM) ---
            file_content = file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()

            existing_import = ImportHistory.objects.filter(file_hash=file_hash).first()
            if existing_import and existing_import.status == ImportHistory.Status.CONCLUIDA:
                messages.error(request, 'Este arquivo já foi importado anteriormente.')
                return redirect('product_import')
            try:
                source_rows = parse_bling_rows(file_content, filename)
                preview = _build_bling_preview(source_rows)
            except Exception as exc:
                messages.error(request, f'Erro ao ler a planilha do Bling: {exc}')
                return redirect('product_import')

            import_history = existing_import or ImportHistory(user=request.user, file_hash=file_hash)
            import_history.user = request.user
            import_history.filename = filename
            import_history.operation_type = ImportHistory.OperationType.BLING
            import_history.status = ImportHistory.Status.BLOQUEADA if preview['summary']['blocked'] else ImportHistory.Status.PRONTA
            import_history.preview_data = {'source_rows': source_rows, 'decisions': {}, **preview}
            import_history.errors = ''
            import_history.save()
            return redirect('product_import_review', pk=import_history.pk)
    else:
        form = ProductImportForm()
    
    preview_id = request.GET.get('preview')
    if preview_id:
        preview_history = ImportHistory.objects.filter(
            pk=preview_id,
            user=request.user,
            operation_type=ImportHistory.OperationType.BLING,
        ).first()
        if preview_history:
            return redirect('product_import_review', pk=preview_history.pk)
    return render(request, 'services/product_import.html', {'form': form})

class ImportHistoryListView(LoginRequiredMixin, ManagerRequiredMixin, ListView):
    model = ImportHistory
    template_name = 'services/product_import_history.html'
    context_object_name = 'imports'
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().select_related('user').annotate(
            ignored_count=Count('items_logged', filter=Q(items_logged__action='Ignorado')),
            error_count=Count('items_logged', filter=Q(items_logged__is_error=True)),
        )

class ImportHistoryDetailView(LoginRequiredMixin, ManagerRequiredMixin, DetailView):
    model = ImportHistory
    template_name = 'services/product_import_history_detail.html'
    context_object_name = 'import_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items_logged.all().select_related('product')
        action = self.request.GET.get('action', '')
        search = self.request.GET.get('search', '').strip()
        if action:
            items = items.filter(action=action)
        if search:
            items = items.filter(Q(identifier__icontains=search) | Q(product__name__icontains=search) | Q(product__code__icontains=search))
        context['items'] = items
        all_items = self.object.items_logged.all()
        context['ignored_count'] = all_items.filter(action='Ignorado').count()
        context['error_count'] = all_items.filter(is_error=True).count()
        context['impacted_products'] = Product.objects.filter(
            importitem__import_history=self.object,
            importitem__is_error=False,
        ).exclude(importitem__action='Ignorado').distinct().order_by('name')
        context['actions'] = all_items.order_by().values_list('action', flat=True).distinct()
        context['selected_action'] = action
        context['search'] = search
        return context


# --- NOTA DE ENTRADA (PURCHASE INVOICE) ---

def _item_from_hidden_post(post_data, index):
    return {
        'code': post_data.get(f'item_{index}_code', ''),
        'barcode': post_data.get(f'item_{index}_barcode', ''),
        'name': post_data.get(f'item_{index}_name', ''),
        'unit': post_data.get(f'item_{index}_unit', ''),
        'ncm': post_data.get(f'item_{index}_ncm', ''),
        'cfop': post_data.get(f'item_{index}_cfop', ''),
        'cest': post_data.get(f'item_{index}_cest', ''),
        'quantity': _decimal_or_zero(post_data.get(f'item_{index}_quantity')),
        'unit_cost': _decimal_or_zero(post_data.get(f'item_{index}_unit_cost')),
        'origem': _decimal_or_zero(post_data.get(f'item_{index}_origem')),
        'icms_raw': post_data.get(f'item_{index}_icms_raw', ''),
        'pis_cst': post_data.get(f'item_{index}_pis_cst', ''),
        'cofins_cst': post_data.get(f'item_{index}_cofins_cst', ''),
    }


def _decimal_or_zero(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        # Aceita tanto "25.00" quanto "25,00" — proteção extra caso algum
        # número chegue localizado (ex: template renderizando em pt-BR).
        return Decimal(str(value).replace(',', '.'))
    except Exception:
        return Decimal('0')


@login_required
@user_passes_test(is_manager)
def purchase_invoice_import_preview(request):
    """Tela única de importação: passo 1 lê o XML e mostra os dados extraídos
    (nota, fornecedor, itens) pra conferência; passo 2 ("Confirmar e
    Importar") efetivamente cria a Nota de Entrada (RASCUNHO) com esses
    dados, cadastrando fornecedor/produtos que não existirem. O usuário
    revisa e lança (dá entrada no estoque) na tela de detalhe da nota."""
    parsed = None
    matched_items = None
    supplier = None
    total = None
    xml_import_error = ''
    raw_preview = ''
    filename = ''
    duplicate_invoice = None

    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        try:
            item_count = int(request.POST.get('item_count', 0))
        except (TypeError, ValueError):
            item_count = 0

        parsed = {
            'number': request.POST.get('h_number', ''),
            'series': request.POST.get('h_series', ''),
            'access_key': request.POST.get('h_access_key', ''),
            'issue_date': request.POST.get('h_issue_date', ''),
            'supplier_cnpj': request.POST.get('h_supplier_cnpj', ''),
            'supplier_name': request.POST.get('h_supplier_name', ''),
            'supplier_trade_name': request.POST.get('h_supplier_trade_name', ''),
            'supplier_ie': request.POST.get('h_supplier_ie', ''),
            'supplier_phone': request.POST.get('h_supplier_phone', ''),
            'supplier_address': request.POST.get('h_supplier_address', ''),
            'items': [_item_from_hidden_post(request.POST, i) for i in range(item_count)],
        }

        supplier, supplier_created = get_or_create_supplier_from_xml(parsed)
        if not supplier:
            messages.error(
                request,
                "O XML não traz um CNPJ de fornecedor válido — não é possível importar automaticamente. "
                "Cadastre o fornecedor manualmente e lance a nota pela opção \"Lançar Manualmente\"."
            )
            return redirect('purchase_invoice_import_preview')

        duplicate_invoice = PurchaseInvoice.find_duplicate(
            supplier=supplier,
            number=parsed['number'],
            series=parsed['series'],
            access_key=parsed['access_key'],
        )
        if duplicate_invoice:
            messages.error(
                request,
                f"Esta nota já foi importada (registro #{duplicate_invoice.pk}, "
                f"status: {duplicate_invoice.get_status_display()})."
            )
            return redirect('purchase_invoice_detail', pk=duplicate_invoice.pk)

        matched_items, _unmatched = match_products(parsed['items'])
        created_products = create_missing_products(matched_items, supplier=supplier, user=request.user)

        # Modo Bling: opt-in checkbox pra atualizar campos fiscais de produtos
        # já cadastrados (só preenche campos vazios — nunca sobrescreve
        # configuração manual).
        regime_mismatch_labels = []
        updated_products = []
        if request.POST.get('update_existing_products'):
            for item in matched_items:
                product = item.get('product')
                if product is None or product in created_products:
                    continue
                changed = _update_product_fiscal(product, item)
                if changed:
                    updated_products.append(product.name)
            if updated_products:
                messages.info(
                    request,
                    f"Dados fiscais de {len(updated_products)} produto(s) existente(s) "
                    f"atualizados: {', '.join(updated_products[:5])}."
                )

        # Mark itens com CST/CSOSN divergente do regime da empresa — para o
        # preview renderizado abaixo (torna visível que ficou em branco).
        from fiscal.models import NFeConfig
        try:
            cfg = NFeConfig.load()
            is_simples = cfg.regime_tributario in (1, 2)
        except Exception:
            is_simples = None
        for item in matched_items:
            icms_raw = item.get('icms_raw') or ''
            if icms_raw and ((len(icms_raw) == 2 and is_simples) or (len(icms_raw) == 3 and not is_simples)):
                item['regime_mismatch'] = True
                regime_mismatch_labels.append(item['name'])
        if regime_mismatch_labels:
            messages.warning(
                request,
                f"{len(regime_mismatch_labels)} item(ns) tinham CST/CSOSN divergente do regime da empresa "
                f"e ficaram sem CST ICMS/CSOSN no cadastro. Revise manualmente: "
                f"{', '.join(regime_mismatch_labels[:5])}."
            )

        with transaction.atomic():
            locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
            duplicate_invoice = PurchaseInvoice.find_duplicate(
                supplier=locked_supplier,
                number=parsed['number'],
                series=parsed['series'],
                access_key=parsed['access_key'],
            )
            if not duplicate_invoice:
                invoice_kwargs = dict(
                    supplier=locked_supplier,
                    number=parsed['number'],
                    series=parsed['series'],
                    access_key=''.join(filter(str.isdigit, parsed['access_key'] or '')),
                    generate_expense=bool(request.POST.get('generate_expense')),
                    expense_due_date=request.POST.get('expense_due_date') or None,
                    status=PurchaseInvoice.Status.RASCUNHO,
                )
                if parsed['issue_date']:
                    invoice_kwargs['issue_date'] = parsed['issue_date']
                invoice = PurchaseInvoice.objects.create(**invoice_kwargs)

                for item in matched_items:
                    PurchaseInvoiceItem.objects.create(
                        invoice=invoice,
                        product=item['product'],
                        quantity=item['quantity'],
                        unit_cost=item['unit_cost'],
                    )

        if duplicate_invoice:
            messages.error(
                request,
                f"Esta nota já foi importada (registro #{duplicate_invoice.pk}, "
                f"status: {duplicate_invoice.get_status_display()})."
            )
            return redirect('purchase_invoice_detail', pk=duplicate_invoice.pk)

        if supplier_created:
            messages.info(request, f"Fornecedor \"{supplier.display_name}\" cadastrado automaticamente a partir do XML.")
        if created_products:
            names = ", ".join(p.name for p in created_products[:5])
            more = f" e mais {len(created_products) - 5}" if len(created_products) > 5 else ""
            messages.info(request, f"{len(created_products)} produto(s) cadastrados automaticamente: {names}{more}. Revise categoria e preço de venda depois.")
        messages.success(request, "Nota de entrada importada como rascunho. Confira os itens e clique em \"Lançar Nota\" pra dar entrada no estoque.")
        return redirect('purchase_invoice_detail', pk=invoice.pk)

    if request.method == 'POST':
        upload_form = PurchaseInvoiceXMLUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            xml_file = upload_form.cleaned_data['xml_file']
            filename = xml_file.name
            try:
                raw_bytes = xml_file.read()
                xml_file.seek(0)
                raw_preview = raw_bytes[:800].decode('utf-8', errors='replace')
            except Exception:
                raw_preview = ''

            try:
                parsed = parse_nfe_xml(xml_file)
            except NFeXMLParseError as e:
                xml_import_error = str(e)
        else:
            xml_import_error = "Escolha um arquivo XML antes de enviar."

        if parsed:
            matched_items, _unmatched = match_products(parsed['items'])
            supplier = find_supplier_by_cnpj(parsed['supplier_cnpj'])
            duplicate_invoice = PurchaseInvoice.find_duplicate(
                supplier=supplier,
                number=parsed['number'],
                series=parsed['series'],
                access_key=parsed['access_key'],
            )
            for item in matched_items:
                item['subtotal'] = item['quantity'] * item['unit_cost']
            total = sum((item['subtotal'] for item in matched_items), Decimal('0'))
    else:
        upload_form = PurchaseInvoiceXMLUploadForm()

    return render(request, 'services/purchase_invoices/purchase_invoice_import_preview.html', {
        'upload_form': upload_form,
        'parsed': parsed,
        'matched_items': matched_items,
        'supplier': supplier,
        'total': total,
        'xml_import_error': xml_import_error,
        'raw_preview': raw_preview,
        'filename': filename,
        'duplicate_invoice': duplicate_invoice,
    })


def _items_initial_from_post(post_data):
    """Reconstrói a lista de itens a partir do POST sem passar pelo formset
    ligado (bound) — evita que o simples fato de renderizar o template
    (que acessa `formset.errors`) dispare validação e mostre erros de campo
    obrigatório quando só queremos reexibir o que o usuário já tinha
    preenchido (ex.: reenvio do Importar sem escolher o arquivo de novo, ou
    XML que falhou ao ser lido)."""
    try:
        total = int(post_data.get('items-TOTAL_FORMS', 0))
    except (TypeError, ValueError):
        total = 0

    rows = []
    for i in range(total):
        if post_data.get(f'items-{i}-DELETE'):
            continue
        rows.append({
            'product': post_data.get(f'items-{i}-product') or None,
            'quantity': post_data.get(f'items-{i}-quantity') or None,
            'unit_cost': post_data.get(f'items-{i}-unit_cost') or None,
        })
    return rows


def _header_initial_from_post(post_data):
    return {
        'supplier': post_data.get('supplier') or None,
        'number': post_data.get('number', ''),
        'series': post_data.get('series', ''),
        'access_key': post_data.get('access_key', ''),
        'issue_date': post_data.get('issue_date') or None,
        'notes': post_data.get('notes', ''),
        'generate_expense': bool(post_data.get('generate_expense')),
        'expense_due_date': post_data.get('expense_due_date') or None,
    }


def _xml_item_formset_class(extra):
    """FormSet com `extra` dinâmico — usado só para pré-popular as linhas de
    itens extraídas do XML antes de salvar (o formset padrão da tela manual
    usa extra=0 e adiciona linhas via JS)."""
    return inlineformset_factory(
        PurchaseInvoice, PurchaseInvoiceItem,
        form=PurchaseInvoiceItemForm,
        extra=extra, can_delete=True, min_num=1, validate_min=True,
    )


class PurchaseInvoiceListView(LoginRequiredMixin, ManagerRequiredMixin, ListView):
    model = PurchaseInvoice
    template_name = 'services/purchase_invoices/purchase_invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        queryset = PurchaseInvoice.objects.select_related('supplier').order_by('-issue_date', '-created_at')
        status = self.request.GET.get('status')
        supplier_id = self.request.GET.get('supplier')
        if status:
            queryset = queryset.filter(status=status)
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = PurchaseInvoice.Status.choices
        context['suppliers'] = Supplier.objects.order_by('name')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_supplier'] = self.request.GET.get('supplier', '')
        return context


@login_required
@user_passes_test(is_manager)
def purchase_invoice_create(request):
    header_initial = None
    items_initial = None
    xml_import_error = ''

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'import_xml':
            upload_form = PurchaseInvoiceXMLUploadForm(request.POST, request.FILES)
            parsed = None

            if upload_form.is_valid():
                try:
                    parsed = parse_nfe_xml(upload_form.cleaned_data['xml_file'])
                except NFeXMLParseError as e:
                    xml_import_error = str(e)
                    messages.error(request, f"Não foi possível ler o XML: {e}")
            else:
                # O navegador limpa o campo de arquivo a cada envio do formulário —
                # se o usuário reenviar sem escolher o XML de novo, não há nada pra
                # importar. Mantém tudo que já estava preenchido em vez de zerar.
                xml_import_error = "Nenhum arquivo XML foi enviado. Escolha o arquivo antes de clicar em Importar."
                messages.error(request, xml_import_error)

            if parsed:
                matched_items, _unmatched = match_products(parsed['items'])

                supplier, supplier_created = get_or_create_supplier_from_xml(parsed)
                created_products = create_missing_products(matched_items, supplier=supplier, user=request.user)

                header_initial = {
                    'supplier': supplier.id if supplier else None,
                    'number': parsed['number'],
                    'series': parsed['series'],
                    'access_key': parsed['access_key'],
                    'issue_date': parsed['issue_date'] or None,
                }
                items_initial = [
                    {
                        'product': item['product'].id if item['product'] else None,
                        'quantity': item['quantity'],
                        'unit_cost': item['unit_cost'],
                    }
                    for item in matched_items
                ]

                if supplier_created:
                    messages.info(
                        request,
                        f"Fornecedor \"{supplier.display_name}\" (CNPJ {parsed['supplier_cnpj']}) não existia e foi "
                        "cadastrado automaticamente com os dados do XML. Revise o cadastro se precisar completar algo."
                    )
                elif not supplier:
                    messages.warning(
                        request,
                        f"O XML não traz um CNPJ de fornecedor válido ({parsed['supplier_cnpj'] or 's/ CNPJ'}). "
                        "Selecione o fornecedor manualmente."
                    )

                if created_products:
                    names = ", ".join(p.name for p in created_products[:5])
                    more = f" e mais {len(created_products) - 5}" if len(created_products) > 5 else ""
                    messages.info(
                        request,
                        f"{len(created_products)} produto(s) não existiam no catálogo e foram cadastrados "
                        f"automaticamente a partir do XML: {names}{more}. Revise categoria, preço de venda e "
                        "estoque mínimo depois — o XML só traz nome, código/EAN, unidade, NCM/CFOP e custo."
                    )

                messages.success(request, f"XML importado: {len(items_initial)} item(ns) prontos. Confira e salve.")

                form = PurchaseInvoiceForm(initial=header_initial)
                formset = _xml_item_formset_class(extra=max(len(items_initial or []), 1))(initial=items_initial)
            else:
                # Sem XML novo pra processar (arquivo não enviado ou XML não
                # reconhecido): reconstrói o formulário a partir do que veio no
                # POST sem "ligar" (bind) o form/formset a ele — só usando
                # `initial`. Isso preserva o que o usuário já tinha preenchido
                # sem disparar validação (o simples fato de renderizar
                # `{{ formset.errors }}" no template já validaria um formset
                # bound, mostrando "campo obrigatório" pra linhas que o
                # usuário nem tentou salvar ainda).
                header_initial = _header_initial_from_post(request.POST)
                rows = _items_initial_from_post(request.POST)
                form = PurchaseInvoiceForm(initial=header_initial)
                formset = _xml_item_formset_class(extra=max(len(rows), 1))(initial=rows)

        elif action in ('save_draft', 'save_and_launch'):
            form = PurchaseInvoiceForm(request.POST)
            formset = PurchaseInvoiceItemFormSet(request.POST)

            if form.is_valid() and formset.is_valid():
                with transaction.atomic():
                    supplier = Supplier.objects.select_for_update().get(pk=form.cleaned_data['supplier'].pk)
                    duplicate = PurchaseInvoice.find_duplicate(
                        supplier=supplier,
                        number=form.cleaned_data.get('number'),
                        series=form.cleaned_data.get('series'),
                        access_key=form.cleaned_data.get('access_key'),
                    )
                    if duplicate:
                        form.add_error(
                            None,
                            f'Esta nota já foi cadastrada (registro #{duplicate.pk}, '
                            f'status: {duplicate.get_status_display()}).'
                        )
                    else:
                        invoice = form.save(commit=False)
                        invoice.status = PurchaseInvoice.Status.RASCUNHO
                        invoice.save()
                        formset.instance = invoice
                        formset.save()

                if duplicate:
                    return render(request, 'services/purchase_invoices/purchase_invoice_form.html', {
                        'form': form, 'formset': formset,
                        'upload_form': PurchaseInvoiceXMLUploadForm(),
                        'title': 'Nova Nota de Entrada',
                    })

                if action == 'save_and_launch':
                    try:
                        invoice.launch(user=request.user)
                        messages.success(request, "Nota de entrada lançada com sucesso — estoque e custo dos produtos atualizados.")
                    except ValueError as e:
                        messages.error(request, f"Nota salva como rascunho, mas não pôde ser lançada: {e}")
                else:
                    messages.success(request, "Nota de entrada salva como rascunho.")
                return redirect('purchase_invoice_detail', pk=invoice.pk)
        else:
            form = PurchaseInvoiceForm()
            formset = PurchaseInvoiceItemFormSet()
    else:
        form = PurchaseInvoiceForm()
        formset = PurchaseInvoiceItemFormSet()

    return render(request, 'services/purchase_invoices/purchase_invoice_form.html', {
        'form': form,
        'formset': formset,
        'upload_form': PurchaseInvoiceXMLUploadForm(),
        'title': 'Nova Nota de Entrada',
        'xml_import_error': xml_import_error,
    })


class PurchaseInvoiceDetailView(LoginRequiredMixin, ManagerRequiredMixin, DetailView):
    model = PurchaseInvoice
    template_name = 'services/purchase_invoices/purchase_invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related('product').all()
        return context


@login_required
@user_passes_test(is_manager)
def purchase_invoice_launch(request, pk):
    invoice = get_object_or_404(PurchaseInvoice, pk=pk)
    if request.method == 'POST':
        try:
            invoice.launch(user=request.user)
            messages.success(request, "Nota de entrada lançada com sucesso — estoque e custo dos produtos atualizados.")
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_invoice_detail', pk=invoice.pk)


@login_required
@user_passes_test(is_manager)
def purchase_invoice_cancel(request, pk):
    invoice = get_object_or_404(PurchaseInvoice, pk=pk)
    if request.method == 'POST':
        try:
            invoice.cancel()
            messages.success(request, "Nota de entrada cancelada.")
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_invoice_detail', pk=invoice.pk)
