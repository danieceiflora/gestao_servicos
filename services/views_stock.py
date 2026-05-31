from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q
import csv
import io
from decimal import Decimal
from django.http import HttpResponse
from django.db import transaction
from openpyxl import load_workbook
import hashlib
from .models import Product, StockMovement, User, ImportHistory, ImportItem
from .forms import ProductForm, StockMovementForm, ProductImportForm

from integracoes.models import SystemConfig

def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]

class ManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_manager(self.request.user)

class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'services/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.all()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search)
            )
        return queryset

class ProductCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tax_regime'] = SystemConfig.load().tax_regime
        return context

    def form_valid(self, form):
        messages.success(self.request, "Produto cadastrado com sucesso.")
        return super().form_valid(form)

class ProductUpdateView(LoginRequiredMixin, ManagerRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tax_regime'] = SystemConfig.load().tax_regime
        return context

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado com sucesso.")
        return super().form_valid(form)

class StockMovementCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = 'services/stock_movement_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        movement = form.save(commit=False)
        movement.user = self.request.user
        
        product = movement.product
        if movement.movement_type == StockMovement.MovementType.IN:
            product.current_stock += movement.quantity
        else:
            product.current_stock -= movement.quantity
        
        product.save()
        movement.save()
        
        messages.success(self.request, f"Movimentação de {movement.get_movement_type_display()} realizada com sucesso.")
        return redirect(self.success_url)

@login_required
def product_stock_history(request, pk):
    product = get_object_or_404(Product, pk=pk)
    movements = product.movements.all().select_related('user', 'service_order')
    
    context = {
        'product': product,
        'movements': movements,
    }
    return render(request, 'services/product_stock_history.html', context)

@login_required
@user_passes_test(is_manager)
def product_import_template(request):
    """Gera um arquivo modelo (CSV ou XLSX) para importação, baseada no tipo de operação."""
    file_format = request.GET.get('format', 'csv')
    op_type = request.GET.get('type', 'CATALOG')
    
    if op_type == 'STOCK':
        headers = ['codigo', 'quantidade', 'tipo_entrada_saida', 'motivo', 'notas']
        data = [
            ['CABO-25-PT', '50', 'ENTRADA', 'COMPRA', 'NF 1234'],
            ['DISJ-20A', '2', 'SAIDA', 'PERDA', 'Quebrado no transporte']
        ]
        filename_prefix = "modelo_movimentacao_estoque"
    else:
        headers = ['nome', 'codigo', 'unidade', 'preco_venda', 'ativo_sim_nao']
        data = [
            ['Cabo Flexível 2.5mm', 'CABO-25-PT', 'M', '4.50', 'S'],
            ['Disjuntor 20A', 'DISJ-20A', 'UN', '18.90', 'S']
        ]
        filename_prefix = "modelo_gestao_catalogo"

    if file_format == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Modelo Importação"
        
        # Header styling
        header_font = Font(bold=True)
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
        
        # Add sample data
        for row_idx, row_data in enumerate(data, 2):
            for col_idx, value in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename_prefix}.xlsx"'
        wb.save(response)
        return response
    else:
        # Default to CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename_prefix}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(headers)
        for row in data:
            writer.writerow(row)
        
        return response

@login_required
@user_passes_test(is_manager)
def product_import(request):
    if request.method == 'POST':
        form = ProductImportForm(request.POST, request.FILES)
        if form.is_valid():
            op_type = form.cleaned_data['operation_type']
            file = request.FILES['file']
            filename = file.name
            
            # --- PREVENÇÃO DE DUPLICIDADE (CHECKSUM) ---
            file_content = file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            if ImportHistory.objects.filter(file_hash=file_hash).exists():
                messages.error(request, "Este arquivo (ou um conteúdo idêntico) já foi importado anteriormente. Operação cancelada para evitar duplicidade.")
                return redirect('product_import')
            
            # Reset file pointer for processing after reading for hash
            file.seek(0)
            
            data = []
            try:
                if filename.endswith('.csv'):
                    decoded_file = file.read().decode('utf-8').splitlines()
                    reader = csv.DictReader(decoded_file)
                    data = list(reader)
                elif filename.endswith('.xlsx'):
                    wb = load_workbook(file)
                    ws = wb.active
                    headers = [cell.value for cell in ws[1]]
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        data.append(dict(zip(headers, row)))
            except Exception as e:
                messages.error(request, f"Erro ao ler o arquivo: {str(e)}")
                return redirect('product_import')

            unit_map = {
                'UN': Product.UnitType.UNIT,
                'M': Product.UnitType.METER,
                'M2': Product.UnitType.SQUARE_METER,
                'L': Product.UnitType.LITER,
                'KG': Product.UnitType.KILO,
            }

            # Mapping for movement reasons
            reason_map = {
                'COMPRA': StockMovement.Reason.PURCHASE,
                'VENDA': StockMovement.Reason.SALE_OS,
                'AJUSTE': StockMovement.Reason.ADJUSTMENT,
                'PERDA': StockMovement.Reason.LOSS,
                'DEVOLUCAO': StockMovement.Reason.RETURN,
            }

            created_count = 0
            updated_count = 0
            movements_count = 0
            errors = []

            with transaction.atomic():
                audit = ImportHistory.objects.create(
                    user=request.user,
                    filename=f"[{op_type}] {filename}",
                    file_hash=file_hash
                )

                for index, row in enumerate(data, start=2):
                    try:
                        code = row.get('codigo')
                        name = row.get('nome')
                        identifier = code or name or f"Linha {index}"
                        
                        if not code and op_type == 'STOCK':
                            ImportItem.objects.create(
                                import_history=audit, row_number=index, identifier=identifier,
                                action="Falha", details="Código/SKU é obrigatório para estoque.", is_error=True
                            )
                            errors.append(f"Linha {index}: Código obrigatório.")
                            continue

                        if op_type == 'STOCK':
                            # --- OPERAÇÃO: MOVIMENTAÇÃO DE ESTOQUE ---
                            try:
                                product = Product.objects.get(code=code)
                            except Product.DoesNotExist:
                                ImportItem.objects.create(
                                    import_history=audit, row_number=index, identifier=identifier,
                                    action="Falha", details=f"Produto com código {code} não encontrado.", is_error=True
                                )
                                errors.append(f"Linha {index}: Produto não encontrado.")
                                continue

                            try:
                                qty = float(str(row.get('quantidade') or 0).replace(',', '.'))
                                if qty <= 0: raise ValueError()
                            except (ValueError, TypeError):
                                ImportItem.objects.create(
                                    import_history=audit, row_number=index, identifier=identifier,
                                    product=product, action="Falha", details="Quantidade inválida.", is_error=True
                                )
                                errors.append(f"Linha {index}: Qtd inválida.")
                                continue

                            tipo_str = str(row.get('tipo_entrada_saida') or 'ENTRADA').upper().strip()
                            mov_type = StockMovement.MovementType.IN if tipo_str in ['ENTRADA', 'E', 'IN'] else StockMovement.MovementType.OUT
                            
                            reason_str = str(row.get('motivo') or 'AJUSTE').upper().strip()
                            reason = reason_map.get(reason_str, StockMovement.Reason.ADJUSTMENT)
                            
                            notes = row.get('notas') or f"Importação em massa ({filename})"

                            old_stock = float(product.current_stock)
                            if mov_type == StockMovement.MovementType.IN:
                                product.current_stock += Decimal(str(qty))
                            else:
                                product.current_stock -= Decimal(str(qty))
                            product.save()

                            StockMovement.objects.create(
                                product=product, quantity=qty, movement_type=mov_type,
                                reason=reason, user=request.user, import_history=audit, notes=notes
                            )
                            
                            ImportItem.objects.create(
                                import_history=audit, row_number=index, identifier=identifier,
                                product=product, action="Estoque", 
                                details=f"{'Acrescentado' if mov_type == 'IN' else 'Removido'} {qty} ({reason_str}). Saldo: {old_stock} -> {product.current_stock}"
                            )
                            movements_count += 1
                            updated_count += 1

                        else:
                            # --- OPERAÇÃO: GESTÃO DE CATÁLOGO ---
                            if not name:
                                ImportItem.objects.create(
                                    import_history=audit, row_number=index, identifier=identifier,
                                    action="Falha", details="Nome obrigatório para catálogo.", is_error=True
                                )
                                continue
                            
                            unit_str = str(row.get('unidade') or 'UN').upper().strip()
                            unit_type = unit_map.get(unit_str, Product.UnitType.UNIT)
                            
                            try:
                                price = float(str(row.get('preco_venda') or 0).replace(',', '.'))
                            except (ValueError, TypeError): price = 0
                            
                            ativo_str = str(row.get('ativo_sim_nao') or 'S').upper().strip()
                            is_active = ativo_str in ['S', 'SIM', 'Y', 'YES', '1', 'TRUE']

                            product, created = Product.objects.get_or_create(
                                code=code,
                                defaults={'name': name, 'unit_type': unit_type, 'default_unit_price': price, 'is_active': is_active}
                            )

                            if created:
                                ImportItem.objects.create(
                                    import_history=audit, row_number=index, identifier=identifier,
                                    product=product, action="Criado", details=f"Produto novo. Preço: {price}. Ativo: {is_active}"
                                )
                                created_count += 1
                            else:
                                changes = []
                                if product.name != name: changes.append(f"Nome: {product.name} -> {name}")
                                if float(product.default_unit_price) != price: changes.append(f"Preço: {product.default_unit_price} -> {price}")
                                if product.is_active != is_active: changes.append(f"Ativo: {product.is_active} -> {is_active}")
                                
                                product.name = name
                                product.unit_type = unit_type
                                product.default_unit_price = price
                                product.is_active = is_active
                                product.save()
                                
                                ImportItem.objects.create(
                                    import_history=audit, row_number=index, identifier=identifier,
                                    product=product, action="Atualizado", details=", ".join(changes) if changes else "Nenhuma alteração detectada"
                                )
                                updated_count += 1

                    except Exception as e:
                        ImportItem.objects.create(
                            import_history=audit, row_number=index, identifier=f"Linha {index}",
                            action="Erro Crítico", details=str(e), is_error=True
                        )
                        errors.append(f"Linha {index}: {str(e)}")

                audit.created_count = created_count
                audit.updated_count = updated_count
                audit.movements_count = movements_count
                if errors:
                    audit.errors = "\n".join(errors)
                audit.save()

            if errors:
                messages.warning(request, f"Importação [{op_type}] finalizada com erros nas linhas: {', '.join(errors[:3])}...")
            
            messages.success(request, f"Importação [{op_type}] concluída. {created_count} criados, {updated_count} atualizados.")
            return redirect('product_list')
    else:
        form = ProductImportForm()
    
    return render(request, 'services/product_import.html', {'form': form})

class ImportHistoryListView(LoginRequiredMixin, ManagerRequiredMixin, ListView):
    model = ImportHistory
    template_name = 'services/product_import_history.html'
    context_object_name = 'imports'
    paginate_by = 20

class ImportHistoryDetailView(LoginRequiredMixin, ManagerRequiredMixin, DetailView):
    model = ImportHistory
    template_name = 'services/product_import_history_detail.html'
    context_object_name = 'import_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items_logged.all().select_related('product')
        return context
