from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q, F
from django.utils import timezone
from decimal import Decimal
from .models import ServiceOrderTask, ServiceOrderTeam, Professional, User
from django.http import HttpResponse
import csv
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]

@login_required
@user_passes_test(is_manager)
def finance_dashboard(request):
    now = timezone.now()
    month = int(request.GET.get('month', now.month))
    year = int(request.GET.get('year', now.year))
    professional_id = request.GET.get('professional')

    # Query allocations for completed executions in the selected period
    allocations = ServiceOrderTeam.objects.filter(
        task__task_type=ServiceOrderTask.TaskType.EXECUTION,
        task__status=ServiceOrderTask.TaskStatus.COMPLETED,
        task__finished_at__month=month,
        task__finished_at__year=year
    ).select_related('task__service_order', 'professional', 'role')

    if professional_id:
        allocations = allocations.filter(professional_id=professional_id)

    # Process data for the table and totals
    report_items = []
    total_commission = Decimal('0')
    total_services_value = Decimal('0')
    professionals_seen = set()
    total_base_salary = Decimal('0')

    for alloc in allocations:
        # User requested to use ServiceOrder.estimated_value
        task_value = alloc.task.service_order.estimated_value or Decimal('0')
        comm_rate = alloc.role.commission_rate if alloc.role else Decimal('0')
        commission_value = (task_value * (comm_rate / 100))
        
        report_items.append({
            'date': alloc.task.finished_at,
            'order_id': alloc.task.service_order.id,
            'os_number': alloc.task.service_order.number,
            'client_name': alloc.task.service_order.client_property.client.name,
            'address': alloc.task.service_order.client_property.address,
            'professional': alloc.professional.name,
            'role': alloc.role.name if alloc.role else '---',
            'task_value': task_value,
            'comm_rate': comm_rate,
            'commission_value': commission_value,
        })
        
        total_commission += commission_value
        total_services_value += task_value
        
        if alloc.professional.id not in professionals_seen:
            professionals_seen.add(alloc.professional.id)
            total_base_salary += alloc.professional.base_salary or Decimal('0')

    context = {
        'report_items': report_items,
        'total_services_count': len(report_items),
        'total_services_value': total_services_value,
        'total_commission': total_commission,
        'total_base_salary': total_base_salary,
        'total_with_salary': total_commission + total_base_salary,
        'months': range(1, 13),
        'years': range(now.year - 2, now.year + 1),
        'selected_month': month,
        'selected_year': year,
        'selected_professional': professional_id,
        'professionals': Professional.objects.filter(is_active=True),
    }

    if request.GET.get('export') == 'xlsx':
        return export_finance_xlsx(report_items, total_commission, total_base_salary, month, year)
    elif request.GET.get('export') == 'pdf':
        return export_finance_pdf(report_items, total_commission, total_base_salary, month, year)

    return render(request, 'services/finance/dashboard.html', context)

def export_finance_xlsx(report_items, total_commission, total_base_salary, month, year):
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório Financeiro"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    center_align = Alignment(horizontal="center")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # Headers
    headers = ['Data', 'OS', 'Cliente', 'Endereço', 'Colaborador', 'Função', 'Valor OS (Est.)', 'Comissão (%)', 'Vlr. Comissão']
    ws.append(headers)

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border

    # Data
    for item in report_items:
        row = [
            item['date'].strftime('%d/%m/%Y'),
            item['os_number'],
            item['client_name'],
            item['address'],
            item['professional'],
            item['role'],
            float(item['task_value']),
            float(item['comm_rate']),
            float(item['commission_value'])
        ]
        ws.append(row)

    # Formatting columns
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 8
    ws.column_dimensions['C'].width = 30
    ws.column_dimensions['D'].width = 40
    ws.column_dimensions['E'].width = 25
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 15
    ws.column_dimensions['H'].width = 12
    ws.column_dimensions['I'].width = 15

    # Currency formatting
    for row in range(2, len(report_items) + 2):
        ws.cell(row=row, column=7).number_format = '"R$ "#,##0.00'
        ws.cell(row=row, column=9).number_format = '"R$ "#,##0.00'
        ws.cell(row=row, column=8).number_format = '0.0"%"'

    # Totals
    ws.append([])
    ws.append(['', '', '', '', '', '', 'Total Comissão', '', float(total_commission)])
    ws.append(['', '', '', '', '', '', 'Total Salários Base', '', float(total_base_salary)])
    ws.append(['', '', '', '', '', '', 'Total Geral', '', float(total_commission + total_base_salary)])

    last_row = ws.max_row
    for r in range(last_row - 2, last_row + 1):
        ws.cell(row=r, column=7).font = Font(bold=True)
        ws.cell(row=r, column=9).font = Font(bold=True)
        ws.cell(row=r, column=9).number_format = '"R$ "#,##0.00'

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="servicos_por_colaborador_{month}_{year}.xlsx"'
    wb.save(response)
    return response

def export_finance_pdf(report_items, total_commission, total_base_salary, month, year):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    # Header
    elements.append(Paragraph("Serviços por colaborador", styles['Title']))
    
    now = timezone.now().astimezone(timezone.get_current_timezone())
    timestamp = now.strftime('%d/%m/%Y %H:%M:%S')
    elements.append(Paragraph(f"Período: {month:02d}/{year} | Gerado em: {timestamp}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Table Header
    data = [['Data', 'OS', 'Cliente', 'Endereço', 'Colaborador', 'Função', 'Vlr. Est. OS', 'Comis %', 'Vlr. Comis.']]
    for item in report_items:
        data.append([
            item['date'].strftime('%d/%m/%Y'),
            str(item['os_number']),
            Paragraph(item['client_name'], styles['Normal']),
            Paragraph(item['address'], styles['Normal']),
            item['professional'],
            item['role'],
            f"R$ {item['task_value']:,.2f}",
            f"{item['comm_rate']}%",
            f"R$ {item['commission_value']:,.2f}"
        ])
    
    # Adjusting column widths for landscape A4 (approx 842 pts)
    # Total used: 60+40+130+150+120+80+80+60+80 = 800 pts
    table = Table(data, repeatRows=1, colWidths=[60, 40, 130, 150, 120, 80, 80, 60, 80])
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
    elements.append(Spacer(1, 20))
    
    # Totals Table
    summary_data = [
        ['Total Comissão', f"R$ {total_commission:,.2f}"],
        ['Total Salários Base', f"R$ {total_base_salary:,.2f}"],
        ['Total Geral', f"R$ {(total_commission + total_base_salary):,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[150, 100])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    
    # Signature Field
    elements.append(Spacer(1, 50))
    signature_data = [
        ['' , ''],
        ['__________________________________________', '__________________________________________'],
        ['Assinatura do Colaborador', 'Data da Assinatura']
    ]
    sig_table = Table(signature_data, colWidths=[300, 300])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica'),
        ('FONTSIZE', (0, 2), (-1, 2), 8),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="servicos_por_colaborador_{month}_{year}.pdf"'
    response.write(pdf)
    return response
