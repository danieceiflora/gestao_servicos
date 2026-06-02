from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q, F
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from datetime import datetime
from .models import ServiceOrderTask, ServiceOrderTeam, Professional, User, ServicePayment, Sale, SaleItem, Product, StockMovement, PaymentMethod, SalePayment, Expense, ExpenseInstallment, Client
from .forms import SaleForm, SaleItemFormSet, PaymentMethodForm, ExpenseForm, ExpenseInstallmentFormSet
from .expense_engine import generate_expense_installments
from django.http import HttpResponse
import csv
import logging
from io import BytesIO

logger = logging.getLogger(__name__)
from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from .models import Billing, Installment

def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]

@login_required
@user_passes_test(is_manager)
def payment_method_list(request):
    methods = PaymentMethod.objects.all().order_by('descricao')
    context = {
        'methods': methods,
        'title': 'Métodos de Pagamento',
    }
    return render(request, 'services/finance/payment_method_list.html', context)

@login_required
@user_passes_test(is_manager)
def payment_method_create(request):
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Método de pagamento criado com sucesso!")
            return redirect('payment_method_list')
    else:
        form = PaymentMethodForm()
    
    context = {
        'form': form,
        'title': 'Novo Método de Pagamento',
        'is_edit': False
    }
    return render(request, 'services/finance/payment_method_form.html', context)

@login_required
@user_passes_test(is_manager)
def payment_method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=method)
        if form.is_valid():
            form.save()
            messages.success(request, "Método de pagamento atualizado com sucesso!")
            return redirect('payment_method_list')
    else:
        form = PaymentMethodForm(instance=method)
    
    context = {
        'form': form,
        'title': f'Editar: {method.descricao}',
        'is_edit': True
    }
    return render(request, 'services/finance/payment_method_form.html', context)

@login_required
@user_passes_test(is_manager)
def payment_method_toggle(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)
    method.ativo = not method.ativo
    method.save()
    status = "ativado" if method.ativo else "desativado"
    messages.success(request, f"Método de pagamento {method.descricao} {status} com sucesso!")
    return redirect('payment_method_list')

@login_required
@user_passes_test(is_manager)
def finance_dashboard(request):
    now = timezone.now()
    month = int(request.GET.get('month', now.month))
    year = int(request.GET.get('year', now.year))
    professional_id = request.GET.get('professional')

    tz = timezone.get_current_timezone()
    start_of_month = timezone.make_aware(datetime(year, month, 1), tz)
    if month == 12:
        end_of_month = timezone.make_aware(datetime(year + 1, 1, 1), tz)
    else:
        end_of_month = timezone.make_aware(datetime(year, month + 1, 1), tz)

    # Query allocations for completed executions in the selected period
    allocations = ServiceOrderTeam.objects.filter(
        task__task_type=ServiceOrderTask.TaskType.EXECUCAO,
        task__status=ServiceOrderTask.TaskStatus.CONCLUIDO,
        task__finished_at__gte=start_of_month,
        task__finished_at__lt=end_of_month
    ).select_related('task__service_order', 'professional', 'role').order_by('professional__name', 'task__finished_at')

    if professional_id:
        allocations = allocations.filter(professional_id=professional_id)

    # Process data grouped by professional
    grouped_data = {}
    total_commission_global = Decimal('0')
    total_services_value_global = Decimal('0')
    total_base_salary_global = Decimal('0')
    professionals_seen = set()

    for alloc in allocations:
        p_id = str(alloc.professional.id)
        if p_id not in grouped_data:
            grouped_data[p_id] = {
                'professional_name': alloc.professional.name,
                'base_salary': alloc.professional.base_salary or Decimal('0'),
                'items': [],
                'total_commission': Decimal('0'),
                'total_services_value': Decimal('0'),
            }
        
        task_value = alloc.task.service_order.estimated_value or Decimal('0')
        comm_rate = alloc.role.commission_rate if alloc.role else Decimal('0')
        commission_value = (task_value * (comm_rate / 100))
        
        item = {
            'date': alloc.task.finished_at,
            'order_id': alloc.task.service_order.id,
            'os_number': alloc.task.service_order.number,
            'client_name': alloc.task.service_order.client_property.client.name,
            'address': alloc.task.service_order.client_property.address,
            'role': alloc.role.name if alloc.role else '---',
            'task_value': task_value,
            'comm_rate': comm_rate,
            'commission_value': commission_value,
        }
        
        grouped_data[p_id]['items'].append(item)
        grouped_data[p_id]['total_commission'] += commission_value
        grouped_data[p_id]['total_services_value'] += task_value
        
        total_commission_global += commission_value
        total_services_value_global += task_value
        
        if alloc.professional.id not in professionals_seen:
            professionals_seen.add(alloc.professional.id)
            total_base_salary_global += alloc.professional.base_salary or Decimal('0')

    # Flatten report_items for the dashboard table (simple list)
    report_items = []
    for p_id, data in grouped_data.items():
        for item in data['items']:
            # Inject professional name for each item in flat list
            item_with_name = item.copy()
            item_with_name['professional'] = data['professional_name']
            report_items.append(item_with_name)

    context = {
        'report_items': report_items,
        'grouped_data': grouped_data,
        'total_services_count': len(report_items),
        'total_services_value': total_services_value_global,
        'total_commission': total_commission_global,
        'total_base_salary': total_base_salary_global,
        'total_with_salary': total_commission_global + total_base_salary_global,
        'months': range(1, 13),
        'years': range(now.year - 2, now.year + 1),
        'selected_month': month,
        'selected_year': year,
        'selected_professional': professional_id,
        'professionals': Professional.objects.filter(is_active=True),
    }

    if request.GET.get('export') == 'xlsx':
        return export_finance_xlsx(grouped_data, month, year)
    elif request.GET.get('export') == 'pdf':
        return export_finance_pdf(grouped_data, month, year)

    return render(request, 'services/finance/dashboard.html', context)

def export_finance_xlsx(grouped_data, month, year):
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório Financeiro"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    group_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    center_align = Alignment(horizontal="center")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # Column widths
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 8
    ws.column_dimensions['C'].width = 30
    ws.column_dimensions['D'].width = 40
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 12
    ws.column_dimensions['H'].width = 15

    for p_id, data in grouped_data.items():
        # Professional Header
        ws.append([f"Colaborador: {data['professional_name']}"])
        ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=8)
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
        ws.cell(row=ws.max_row, column=1).fill = group_fill

        # Table Headers
        headers = ['Data', 'OS', 'Cliente', 'Endereço', 'Função', 'Vlr. OS (Est.)', 'Comissão (%)', 'Vlr. Comissão']
        ws.append(headers)
        header_row = ws.max_row
        for cell in ws[header_row]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = border

        # Data Rows
        for item in data['items']:
            ws.append([
                item['date'].strftime('%d/%m/%Y'),
                item['os_number'],
                item['client_name'],
                item['address'],
                item['role'],
                float(item['task_value']),
                float(item['comm_rate']),
                float(item['commission_value'])
            ])
            curr_row = ws.max_row
            ws.cell(row=curr_row, column=6).number_format = '"R$ "#,##0.00'
            ws.cell(row=curr_row, column=8).number_format = '"R$ "#,##0.00'
            ws.cell(row=curr_row, column=7).number_format = '0.0"%"'

        # Subtotals
        ws.append(['', '', '', '', '', 'Total Comissão:', '', float(data['total_commission'])])
        ws.cell(row=ws.max_row, column=6).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=8).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=8).number_format = '"R$ "#,##0.00'
        
        ws.append(['', '', '', '', '', 'Salário Base:', '', float(data['base_salary'])])
        ws.cell(row=ws.max_row, column=6).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=8).number_format = '"R$ "#,##0.00'
        
        ws.append(['', '', '', '', '', 'TOTAL GERAL:', '', float(data['total_commission'] + data['base_salary'])])
        last_row = ws.max_row
        ws.cell(row=last_row, column=6).font = Font(bold=True)
        ws.cell(row=last_row, column=8).font = Font(bold=True, color="FF0000")
        ws.cell(row=last_row, column=8).number_format = '"R$ "#,##0.00'
        
        ws.append([]) # Spacer
        ws.append([]) # Spacer

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="servicos_por_colaborador_{month}_{year}.xlsx"'
    wb.save(response)
    return response

def export_finance_pdf(grouped_data, month, year):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    for p_id, data in grouped_data.items():
        # Header for each professional
        elements.append(Paragraph("Serviços por colaborador", styles['Title']))
        now = timezone.now().astimezone(timezone.get_current_timezone())
        timestamp = now.strftime('%d/%m/%Y %H:%M:%S')
        elements.append(Paragraph(f"Colaborador: <b>{data['professional_name']}</b> | Período: {month:02d}/{year} | Gerado em: {timestamp}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Table
        table_data = [['Data', 'OS', 'Cliente', 'Endereço', 'Função', 'Vlr. Est. OS', 'Comis %', 'Vlr. Comis.']]
        for item in data['items']:
            table_data.append([
                item['date'].strftime('%d/%m/%Y'),
                str(item['os_number']),
                Paragraph(item['client_name'], styles['Normal']),
                Paragraph(item['address'], styles['Normal']),
                item['role'],
                f"R$ {item['task_value']:,.2f}",
                f"{item['comm_rate']}%",
                f"R$ {item['commission_value']:,.2f}"
            ])
        
        table = Table(table_data, repeatRows=1, colWidths=[60, 40, 140, 180, 100, 80, 60, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 15))
        
        # Professional Totals
        summary_data = [
            ['Total Comissão', f"R$ {data['total_commission']:,.2f}"],
            ['Salário Base', f"R$ {data['base_salary']:,.2f}"],
            ['TOTAL GERAL', f"R$ {(data['total_commission'] + data['base_salary']):,.2f}"]
        ]
        summary_table = Table(summary_data, colWidths=[150, 100])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (1, 2), (1, 2), colors.red),
        ]))
        elements.append(summary_table)
        
        # Signature
        elements.append(Spacer(1, 40))
        sig_data = [
            ['__________________________________________', '__________________________________________'],
            [f'Assinatura: {data["professional_name"]}', 'Data']
        ]
        sig_table = Table(sig_data, colWidths=[300, 300])
        sig_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 1), (-1, 1), 8)]))
        elements.append(sig_table)
        
        # Page break for next professional
        from reportlab.platypus import PageBreak
        elements.append(PageBreak())
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="servicos_por_colaborador_{month}_{year}.pdf"'
    response.write(pdf)
    return response

@login_required
def finance_professional_payments(request):
    """
    Lista pagamentos recebidos por técnicos.
    Se for gerente, vê todos (com filtro).
    Se for técnico, vê apenas os seus.
    """
    professional_id = request.GET.get('professional')
    status_filter = request.GET.get('status', 'PENDENTE')
    
    payments = ServicePayment.objects.select_related(
        'order', 'order__client_property__client', 'received_by'
    ).order_by('-paid_at')
    
    # Filtro de status
    if status_filter in ['PENDENTE', 'CONFIRMED']:
        payments = payments.filter(status=status_filter)
    
    # Filtro de permissão/profissional
    if not is_manager(request.user):
        try:
            professional = request.user.professional_profile
            payments = payments.filter(received_by=professional)
            professionals = [professional]
            selected_professional = str(professional.id)
        except Professional.DoesNotExist:
            payments = ServicePayment.objects.none()
            professionals = []
            selected_professional = None
    else:
        professionals = Professional.objects.filter(is_active=True)
        if professional_id:
            payments = payments.filter(received_by_id=professional_id)
            selected_professional = professional_id
        else:
            selected_professional = None
        
    paginator = Paginator(payments, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'payments': page_obj,  # Antigamente era 'payments': payments
        'page_obj': page_obj,
        'professionals': professionals,
        'selected_professional': selected_professional,
        'status_filter': status_filter,
        'title': 'Gestão de Recebimentos',
        'is_manager': is_manager(request.user),
        'layout_base': 'base.html' if is_manager(request.user) else 'base_equipe.html'
    }
    return render(request, 'services/finance/professional_payments.html', context)

@login_required
@user_passes_test(is_manager)
def finance_confirm_payment(request, payment_id):
    """Dá baixa em um pagamento individual."""
    payment = get_object_or_404(ServicePayment, id=payment_id)
    
    if request.method == 'POST':
        payment.status = 'CONFIRMED'
        payment.confirmed_at = timezone.now()
        payment.confirmed_by = request.user
        payment.save()
        messages.success(request, f'Pagamento de R$ {payment.amount} (OS #{payment.order.number}) baixado com sucesso.')
        
    return redirect('finance_professional_payments')

@login_required
@user_passes_test(is_manager)
def finance_bulk_confirm_payments(request):
    """Dá baixa em múltiplos pagamentos selecionados."""
    if request.method == 'POST':
        payment_ids = request.POST.getlist('payment_ids')
        if payment_ids:
            # We iterate to ensure order.update_status() is called via save() or explicitly
            payments = ServicePayment.objects.filter(id__in=payment_ids, status='PENDENTE')
            count = 0
            for p in payments:
                p.status = 'CONFIRMED'
                p.confirmed_at = timezone.now()
                p.confirmed_by = request.user
                p.save()
                count += 1
                
            messages.success(request, f'{count} pagamentos foram baixados com sucesso.')
        else:
            messages.warning(request, 'Nenhum pagamento selecionado.')
            
    return redirect('finance_professional_payments')


# --- MÓDULO DE VENDAS (PDV) ---

@login_required
@user_passes_test(is_manager)
def sale_list(request):
    sales = Sale.objects.all().select_related('client', 'user').order_by('-created_at')
    
    # Filtros
    q = request.GET.get('q')
    if q:
        sales = sales.filter(
            Q(number__icontains=q) | 
            Q(client__name__icontains=q) | 
            Q(user__username__icontains=q)
        )
        
    paginator = Paginator(sales, 20)
    page = request.GET.get('page')
    sales_page = paginator.get_page(page)
    
    context = {
        'sales': sales_page,
        'title': 'Histórico de Vendas',
    }
    return render(request, 'services/sale_list.html', context)

@login_required
@user_passes_test(is_manager)
def sale_create(request):
    if request.method == 'POST':
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    sale.user = request.user
                    sale.save()
                    
                    formset.instance = sale
                    items = formset.save()
                    
                    total = Decimal('0.00')
                    for item in items:
                        total += item.subtotal

                        # Baixa de Estoque com inteligência de composição
                        item.product.reduce_stock(
                            item.quantity,
                            user=request.user,
                            reason=StockMovement.Reason.VENDA_DIRETA,
                            notes=f"Venda Direta: #{sale.number}"
                        )

                    sale.total_amount = total - sale.discount + sale.surcharge
                    sale.status = Sale.Status.FINALIZADA
                    sale.save()
                    
                    # --- Lógica de Cobrança Centralizada (Opcional) ---
                    installment_dates = request.POST.getlist('installment_due_date[]')
                    installment_amounts = request.POST.getlist('installment_amount[]')
                    installment_methods = request.POST.getlist('installment_method_id[]')
                    
                    if installment_dates:
                        installments_data = []
                        for d, a, m in zip(installment_dates, installment_amounts, installment_methods):
                            installments_data.append({
                                'due_date': d,
                                'amount': Decimal(a),
                                'payment_method_id': m if m else None
                            })
                        
                        from .utils.finance import create_billing_for_sale
                        create_billing_for_sale(sale, installments_data)
                    
                    messages.success(request, f"Venda #{sale.number} realizada com sucesso!")
                    return redirect('sale_detail', number=sale.number)
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                messages.error(request, f"Erro ao processar venda: {str(e)}")
        else:
            messages.error(request, "Por favor, corrija os erros no formulário.")
    else:
        form = SaleForm()
        formset = SaleItemFormSet(queryset=SaleItem.objects.none())
    
    context = {
        'form': form,
        'formset': formset,
        'title': 'Nova Venda (PDV)',
        'products': Product.objects.filter(is_active=True),
        'clients': Client.objects.all().order_by('name'),
        'payment_methods': PaymentMethod.objects.filter(ativo=True)
    }
    return render(request, 'services/sale_form.html', context)

@login_required
@user_passes_test(is_manager)
def sale_detail(request, number):
    sale = get_object_or_404(Sale, number=number)
    can_edit = sale.can_be_edited()
    
    if request.method == 'POST':
        if not can_edit:
            messages.error(request, "Esta venda não pode ser editada pois já foi finalizada ou possui parcelas no Contas a Receber.")
            return redirect('sale_detail', number=sale.number)
            
        form = SaleForm(request.POST, instance=sale)
        formset = SaleItemFormSet(request.POST, instance=sale)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # 1. Estornar estoque atual antes de salvar as alterações
                    for item in sale.items.all():
                        item.product.increase_stock(
                            item.quantity,
                            user=request.user,
                            reason=StockMovement.Reason.DEVOLUCAO,
                            notes=f"Estorno para Reedição da Venda: #{sale.number}"
                        )
                    
                    # 2. Salvar venda e novos itens
                    sale = form.save(commit=False)
                    sale.save()
                    
                    formset.instance = sale
                    items = formset.save()
                    
                    # 3. Aplicar novo estoque e calcular total
                    total = Decimal('0.00')
                    # Recarregar itens para garantir que pegamos os salvos/atualizados
                    for item in sale.items.all():
                        total += item.subtotal
                        item.product.reduce_stock(
                            item.quantity,
                            user=request.user,
                            reason=StockMovement.Reason.VENDA_DIRETA,
                            notes=f"Venda Direta (Editada): #{sale.number}"
                        )

                    sale.total_amount = total - sale.discount + sale.surcharge
                    sale.save()
                    
                    # 4. Atualizar Cobrança (Billing) e Parcelas se existirem
                    installment_dates = request.POST.getlist('installment_due_date[]')
                    installment_amounts = request.POST.getlist('installment_amount[]')
                    installment_methods = request.POST.getlist('installment_method_id[]')
                    
                    if installment_dates:
                        installments_data = []
                        for d, a, m in zip(installment_dates, installment_amounts, installment_methods):
                            installments_data.append({
                                'due_date': d,
                                'amount': Decimal(a),
                                'payment_method_id': m if m else None
                            })
                        
                        from .utils.finance import create_billing_for_sale
                        # create_billing_for_sale já lida com a atualização se o Billing já existir
                        create_billing_for_sale(sale, installments_data)
                    
                    messages.success(request, f"Venda #{sale.number} atualizada com sucesso!")
                    return redirect('sale_detail', number=sale.number)
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                messages.error(request, f"Erro ao atualizar venda: {str(e)}")
        else:
            messages.error(request, "Por favor, corrija os erros no formulário.")
    else:
        form = SaleForm(instance=sale)
        formset = SaleItemFormSet(instance=sale)
    
    # Se já tiver billing, carregar as parcelas para o template
    initial_installments = []
    if hasattr(sale, 'billing'):
        for inst in sale.billing.installments.all():
            initial_installments.append({
                'due_date': inst.due_date.isoformat(),
                'amount': inst.amount,
                'method_id': inst.payment_method_id
            })

    context = {
        'sale': sale,
        'form': form,
        'formset': formset,
        'can_edit': can_edit,
        'is_detail': True,
        'title': f'Venda #{sale.number}',
        'products': Product.objects.filter(is_active=True),
        'clients': Client.objects.all().order_by('name'),
        'payment_methods': PaymentMethod.objects.filter(ativo=True),
        'initial_installments': initial_installments,
    }
    return render(request, 'services/sale_form.html', context)

@login_required
@user_passes_test(is_manager)
def sale_cancel(request, number):
    sale = get_object_or_404(Sale, number=number)
    
    if sale.status == Sale.Status.CANCELADO:
        messages.warning(request, "Esta venda já está cancelada.")
        return redirect('sale_detail', number=sale.number)
        
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Reverter Estoque com inteligência de composição
                for item in sale.items.all():
                    item.product.increase_stock(
                        item.quantity,
                        user=request.user,
                        reason=StockMovement.Reason.DEVOLUCAO,
                        notes=f"Estorno Venda Cancelada: #{sale.number}"
                    )
                
                sale.status = Sale.Status.CANCELADO
                sale.save()

                # Cancelar Billing se existir
                if hasattr(sale, 'billing'):
                    sale.billing.status = Billing.Status.CANCELADO
                    sale.billing.save()
                    sale.billing.installments.update(status=Installment.Status.CANCELADO)
                
                messages.success(request, "Venda cancelada e estoque estornado com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao cancelar venda: {str(e)}")
            
    return redirect('sale_detail', number=sale.number)

# --- CONTAS A RECEBER (FINANCEIRO CENTRALIZADO) ---

@login_required
@user_passes_test(is_manager)
def billing_list(request):
    """Lista de todas as cobranças (Contas a Receber)."""
    billings = Billing.objects.all().select_related('client', 'sale', 'service_order')
    
    # Filtros simples
    status = request.GET.get('status')
    if status:
        billings = billings.filter(status=status)
        
    context = {
        'billings': billings,
        'title': 'Contas a Receber',
        'active_menu': 'finance'
    }
    return render(request, 'services/finance/billing_list.html', context)

@login_required
@user_passes_test(is_manager)
def billing_detail(request, pk):
    """Detalhamento de uma cobrança e suas parcelas."""
    billing = get_object_or_404(Billing, pk=pk)
    installments = billing.installments.all().select_related('payment_method')
    payment_methods = PaymentMethod.objects.filter(ativo=True)
    
    context = {
        'billing': billing,
        'installments': installments,
        'payment_methods': payment_methods,
        'title': f'Cobrança #{billing.number}'
    }
    return render(request, 'services/finance/billing_detail.html', context)

@login_required
@user_passes_test(is_manager)
def installment_pay(request, pk):
    """Dá baixa manual em uma parcela, suportando múltiplos meios de pagamento."""
    installment = get_object_or_404(Installment, pk=pk)
    
    if request.method == 'POST':
        # Recebe listas de métodos e valores do formulário
        method_ids = request.POST.getlist('payment_method[]')
        amounts = request.POST.getlist('payment_amount[]')
        
        if not method_ids:
            # Fallback para o comportamento antigo (único select)
            method_ids = [request.POST.get('payment_method')]
            amounts = [installment.amount - installment.get_total_paid()]
        
        total_this_time = Decimal('0.00')
        
        for m_id, amt, dt in zip(method_ids, amounts, request.POST.getlist('payment_date[]')):
            if not m_id or not amt: continue
            
            amt_decimal = Decimal(amt.replace(',', '.'))
            if amt_decimal <= 0: continue
            
            method = get_object_or_404(PaymentMethod, pk=m_id)
            
            pay_date = timezone.now()
            if dt:
                try:
                    pay_date = timezone.make_aware(datetime.fromisoformat(dt))
                except ValueError:
                    pass
            
            # Cria o registro de pagamento real
            SalePayment.objects.create(
                venda=installment.billing.sale,
                os=installment.billing.service_order,
                installment=installment,
                metodo_pagamento=method,
                valor_bruto=amt_decimal,
                valor_tarifa=Decimal('0.00'), # TODO: Calcular tarifa se necessário
                valor_liquido=amt_decimal,     # TODO: Calcular líquido
                data_pagamento=pay_date,
                data_previsao=timezone.now().date() # TODO: Usar prazo do método
            )
            total_this_time += amt_decimal
        
        # Atualiza status da Parcela
        total_paid = installment.get_total_paid()
        if total_paid >= installment.amount:
            installment.status = Installment.Status.PAGO
            installment.paid_at = timezone.now()
        elif total_paid > 0:
            installment.status = Installment.Status.PARCIAL
        
        installment.save()
        
        # Atualiza status da Cobrança (Billing)
        billing = installment.billing
        all_installments = billing.installments.all()
        
        # Verifica se todas as parcelas estão pagas
        if not all_installments.exclude(status=Installment.Status.PAGO).exists():
            billing.status = Billing.Status.PAGO
        elif all_installments.filter(status__in=[Installment.Status.PAGO, Installment.Status.PARCIAL]).exists():
            billing.status = Billing.Status.PARCIAL
        else:
            billing.status = Billing.Status.PENDENTE
            
        billing.save()
        
        messages.success(request, f"Pagamento de R$ {total_this_time} registrado para a parcela {installment.installment_number}!")
        
    return redirect('billing_detail', pk=installment.billing.id)

# --- CONTAS A PAGAR (DESPESAS) ---

@login_required
@user_passes_test(is_manager)
def expense_list(request):
    expenses = Expense.objects.all().order_by('-issue_date')
    
    q = request.GET.get('q')
    if q:
        expenses = expenses.filter(
            Q(description__icontains=q) | 
            Q(supplier__name__icontains=q)
        )
        
    paginator = Paginator(expenses, 20)
    page = request.GET.get('page')
    expenses_page = paginator.get_page(page)
    
    context = {
        'expenses': expenses_page,
        'title': 'Contas a Pagar',
        'active_menu': 'finance'
    }
    return render(request, 'services/finance/expense_list.html', context)

@login_required
@user_passes_test(is_manager)
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        # Usamos um prefixo explícito para evitar problemas de colisão ou nomes automáticos complexos
        formset = ExpenseInstallmentFormSet(request.POST, prefix='installments')
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                expense = form.save()
                instances = formset.save(commit=False)
                for instance in instances:
                    instance.expense = expense
                    instance.save()
                
                messages.success(request, "Despesa criada com sucesso!")
                return redirect('expense_list')
        else:
            if not form.is_valid():
                logger.warning(f"ExpenseForm errors: {form.errors}")
            if not formset.is_valid():
                logger.warning(f"ExpenseInstallmentFormSet errors: {formset.errors}")
    else:
        form = ExpenseForm()
        formset = ExpenseInstallmentFormSet(queryset=ExpenseInstallment.objects.none(), prefix='installments')

    context = {
        'form': form,
        'formset': formset,
        'title': 'Nova Conta a Pagar',
        'is_edit': False,
        'active_menu': 'finance'
    }
    return render(request, 'services/finance/expense_form.html', context)

@login_required
@user_passes_test(is_manager)
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        formset = ExpenseInstallmentFormSet(request.POST, instance=expense, prefix='installments')
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                messages.success(request, "Despesa atualizada com sucesso!")
                return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
        formset = ExpenseInstallmentFormSet(instance=expense, prefix='installments')
        
    context = {
        'form': form,
        'formset': formset,
        'title': f'Editar Despesa: {expense.description}',
        'is_edit': True
    }
    return render(request, 'services/finance/expense_form.html', context)

@login_required
@user_passes_test(is_manager)
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Despesa excluída com sucesso!")
        return redirect('expense_list')
    return redirect('expense_list')

@login_required
@user_passes_test(is_manager)
def render_expense_installments_preview(request):
    try:
        data = request.POST if request.method == 'POST' else request.GET
        
        # Tenta pegar o valor de vários jeitos comuns
        total_amount_raw = data.get('total_amount', '0')
        # Limpa possíveis caracteres indesejados (espaços, R$)
        total_amount_raw = total_amount_raw.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            total_amount = Decimal(total_amount_raw)
        except:
            total_amount = Decimal('0')
        
        installments_count_raw = data.get('installments_count', '1')
        try:
            installments_count = int(installments_count_raw)
        except:
            installments_count = 1
        
        frequency = data.get('frequency', '')
        issue_date_str = data.get('issue_date')
        
        logger.info(f"Parsed values: total={total_amount}, count={installments_count}, freq={frequency}, date={issue_date_str}")
        
        issue_date = timezone.now().date()
        if issue_date_str:
            try:
                issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        preview_data = []
        if installments_count > 0:
            # Evita divisão por zero
            div_count = Decimal(installments_count) if installments_count > 0 else Decimal('1')
            base_amount = (total_amount / div_count).quantize(Decimal('0.01'))
            remainder = total_amount - (base_amount * Decimal(installments_count))
            
            current_date = issue_date
            for i in range(1, installments_count + 1):
                amount = base_amount
                if i == installments_count:
                    amount += remainder
                    
                preview_data.append({
                    'installment_number': f"{i}/{installments_count}",
                    'amount': amount,
                    'due_date': current_date
                })
                
                if i < installments_count:
                    if frequency == Expense.Frequency.DIARIA:
                        current_date += relativedelta(days=1)
                    elif frequency == Expense.Frequency.SEMANAL:
                        current_date += relativedelta(days=7)
                    elif frequency == Expense.Frequency.QUINZENAL:
                        current_date += relativedelta(days=15)
                    elif frequency == Expense.Frequency.MENSAL:
                        current_date += relativedelta(months=1)
                    elif frequency == Expense.Frequency.ANUAL:
                        current_date += relativedelta(years=1)
                    else:
                        current_date += relativedelta(months=1)

        logger.info(f"Generated preview_data with {len(preview_data)} items")

        # Usar inlineformset_factory para total consistência com o que o save espera
        from django.forms import inlineformset_factory
        from .forms import ExpenseInstallmentForm
        
        DynamicFormSet = inlineformset_factory(
            Expense, ExpenseInstallment,
            form=ExpenseInstallmentForm,
            extra=installments_count,
            can_delete=False
        )
        
        formset = DynamicFormSet(
            queryset=ExpenseInstallment.objects.none(),
            initial=preview_data,
            prefix='installments'
        )
        logger.info(f"Formset initialized with {formset.total_form_count()} forms")
        
    except Exception as e:
        logger.exception(f"Erro no preview de parcelas: {str(e)}")
        # Fallback para o formset padrão definido no forms.py
        from .forms import ExpenseInstallmentFormSet
        formset = ExpenseInstallmentFormSet(queryset=ExpenseInstallment.objects.none(), prefix='installments')
        
    return render(request, 'services/partials/expense_installments_preview.html', {
        'formset': formset
    })




