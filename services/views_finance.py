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
