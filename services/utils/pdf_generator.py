import os
from io import BytesIO
from PIL import Image as PILImage, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from django.conf import settings
from django.utils import timezone
from integracoes.models import SystemConfig

class BasePDFGenerator:
    def __init__(self, service_order):
        self.service_order = service_order
        self.config = SystemConfig.load()
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        
        # Cores e Configurações de UI (Definir antes de setup_styles)
        self.grid_color = colors.HexColor('#9CA3AF') # Gray 400
        self.bg_light = colors.HexColor('#F9FAFB') # Gray 50
        self.bg_header = colors.HexColor('#F3F4F6') # Gray 100
        self.header_bg = colors.HexColor('#E5E7EB') # Gray 200 - Mais suave para impressão
        self.header_text_color = colors.HexColor('#111827') # Texto escuro para contraste
        self.doc_title = "Documento"
        
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='CompanyTitle',
            parent=self.styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#111827'),
            spaceAfter=2,
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='CompanyDetail',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#374151'),
            leading=10,
            alignment=1 # Center
        ))
        self.styles.add(ParagraphStyle(
            name='DocInfoLabel',
            parent=self.styles['Normal'],
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1F2937'),
            alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name='DocInfoValue',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#111827'),
            alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeaderText',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=self.header_text_color,
            alignment=0, # Left
            leading=12
        ))
        self.styles.add(ParagraphStyle(
            name='GridLabel',

            parent=self.styles['Normal'],
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#374151'),
            leading=8
        ))
        self.styles.add(ParagraphStyle(
            name='GridValue',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#111827'),
            leading=12
        ))
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=self.header_text_color,
            alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name='TableItem',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#111827'),
        ))
        self.styles.add(ParagraphStyle(
            name='SummaryLabel',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#374151'),
            alignment=2
        ))
        self.styles.add(ParagraphStyle(
            name='SummaryValue',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#111827'),
            alignment=2
        ))
        self.styles.add(ParagraphStyle(
            name='TotalFinalLabel',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            alignment=2
        ))
        self.styles.add(ParagraphStyle(
            name='TotalFinalValue',
            parent=self.styles['Normal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            alignment=2
        ))
        self.styles.add(ParagraphStyle(
            name='ChecklistItem',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#111827'),
            leftIndent=10,
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='ChecklistResponse',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#4B5563'),
            fontName='Helvetica-Oblique',
            leftIndent=20
        ))
        self.styles.add(ParagraphStyle(
            name='SmallLabel',
            parent=self.styles['Normal'],
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#4B5563')
        ))
        self.styles.add(ParagraphStyle(
            name='SmallValue',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#1F2937')
        ))
        self.styles.add(ParagraphStyle(
            name='Label',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#374151')
        ))
        self.styles.add(ParagraphStyle(
            name='Value',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#111827')
        ))
        self.styles.add(ParagraphStyle(
            name='WarrantyCompany',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            alignment=TA_CENTER,
            leading=12
        ))
        self.styles.add(ParagraphStyle(
            name='WarrantyTitle',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            alignment=TA_CENTER,
            leading=15
        ))
        self.styles.add(ParagraphStyle(
            name='WarrantyHeading',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            spaceBefore=10,
            spaceAfter=4
        ))
        self.styles.add(ParagraphStyle(
            name='WarrantyBody',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#1F2937'),
            alignment=TA_JUSTIFY,
            leading=12,
            spaceAfter=4
        ))
        self.styles.add(ParagraphStyle(
            name='WarrantyBullet',
            parent=self.styles['WarrantyBody'],
            leftIndent=12,
        ))

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setStrokeColor(self.grid_color)
        canvas.setLineWidth(0.5)
        canvas.line(1.5*cm, 1.2*cm, A4[0]-1.5*cm, 1.2*cm)
        
        company_info = f"{self.config.company_name or '---'}"
        if self.config.company_cnpj:
            company_info += f" - CNPJ: {self.config.company_cnpj}"
            
        footer_text = f"{company_info} | {self.doc_title} nº {self.service_order.number} | Pág. {canvas.getPageNumber()}"
        canvas.drawRightString(A4[0]-1.5*cm, 0.8*cm, footer_text)
        canvas.restoreState()

    def _format_currency(self, value):
        if value is None: value = 0
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _section_title(self, text):
        data = [[Paragraph(text.upper(), self.styles['SectionHeaderText'])]]
        table = Table(data, colWidths=[18*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), self.header_bg),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        return table

    def _get_header(self, doc_title="Orçamento", show_validity=True):
        elements = []

        # Coluna 1: Logo
        logo_file = getattr(self.config, 'company_logo', None)
        img = None
        if logo_file:
            try:
                img = self._get_processed_image(logo_file, width=3.5*cm, height=2.5*cm)
            except Exception as e:
                print(f"Erro ao processar logo: {e}")

        logo_cell = img if img else Paragraph("LOGO", self.styles['CompanyTitle'])

        # Coluna 2: Detalhes da Empresa
        company_info = [
            Paragraph(f"<b>{self.config.company_name}</b>", self.styles['CompanyDetail']),
            Paragraph(f"CNPJ: {self.config.company_cnpj or '---'}", self.styles['CompanyDetail']),
            Paragraph(self.config.company_address or "---", self.styles['CompanyDetail']),
            Paragraph(f"Tel: {self.config.company_phone or '---'}", self.styles['CompanyDetail']),
            Paragraph(self.config.company_website or "", self.styles['CompanyDetail']),
        ]
        info_cell = company_info

        # Coluna 3: Info do Documento
        now = timezone.now().astimezone(timezone.get_current_timezone())
        doc_info_data = [
            [Paragraph("Criado em:", self.styles['DocInfoLabel'])],
            [Paragraph(now.strftime('%d/%m/%Y'), self.styles['DocInfoValue'])],
        ]
        if show_validity:
            doc_info_data += [
                [Spacer(1, 0.1*cm)],
                [Paragraph("Válido até:", self.styles['DocInfoLabel'])],
                [Paragraph((now + timezone.timedelta(days=7)).strftime('%d/%m/%Y'), self.styles['DocInfoValue'])],
            ]
        doc_info_data += [
            [Spacer(1, 0.1*cm)],
            [Paragraph(f"{doc_title} nº:", self.styles['DocInfoLabel'])],
            [Paragraph(str(self.service_order.number), self.styles['DocInfoValue'])],
        ]
        doc_info_table = Table(doc_info_data, colWidths=[4*cm])
        doc_info_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
            ('TOPPADDING', (0,0), (-1,-1), 1),
        ]))

        # Tabela Principal do Header
        header_data = [[logo_cell, info_cell, doc_info_table]]
        header_table = Table(header_data, colWidths=[4.5*cm, 9.5*cm, 4*cm])
        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,0), 'CENTER'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'CENTER'),
        ]))
        
        elements.append(header_table)
        elements.append(Spacer(1, 0.2*cm))
        
        # Título do Documento
        elements.append(self._section_title(doc_title))
        elements.append(Spacer(1, 0.3*cm))
        
        return elements

    def _get_responsible_tech(self):
        """Tenta encontrar o profissional responsável pela OS (Originador ou executor do orçamento)"""
        if self.service_order.originator:
            return self.service_order.originator.name
        
        budget_task = self.service_order.tasks.filter(task_type='ORCAMENTO').first()
        if budget_task:
            first_member = budget_task.team_members.first()
            if first_member:
                return first_member.professional.name
        
        # Fallback para o primeiro executor se não houver orçamento
        execution_task = self.service_order.tasks.filter(task_type='EXECUCAO').first()
        if execution_task:
            first_member = execution_task.team_members.first()
            if first_member:
                return first_member.professional.name
                
        return "Não identificado"

    def _get_client_info(self):
        elements = []
        client = self.service_order.client_property.client
        prop = self.service_order.client_property
        
        phone_val = "---"
        if client.phones.exists():
            phone_val = client.phones.first().phone

        elements.append(self._section_title("DADOS DO CLIENTE"))
        elements.append(Spacer(1, 0.1*cm))

        # Endereço simplificado (Rua, Número, Complemento)
        address_main = f"{prop.address or ''}"
        if prop.number:
            address_main += f", {prop.number}"
        if prop.complement:
            address_main += f" - {prop.complement}"
        if not address_main:
            address_main = "---"

        tech_name = self._get_responsible_tech()

        # Grid de informações do cliente estilo modelopdf.jpg
        data = [
            # Linha 1
            [
                [Paragraph("Cliente", self.styles['GridLabel']), Paragraph(str(client.name or "---"), self.styles['GridValue'])],
                [Paragraph("CPF/CNPJ", self.styles['GridLabel']), Paragraph(str(client.document or "---"), self.styles['GridValue'])],
                [Paragraph("Vendedor/Técnico", self.styles['GridLabel']), Paragraph(tech_name, self.styles['GridValue'])]
            ],
            # Linha 2 - Removido "Contato", mantido "Celular"
            [
                [Paragraph("Celular", self.styles['GridLabel']), Paragraph(str(phone_val), self.styles['GridValue'])],
                '',
                ''
            ],
            # Linha 3
            [
                [Paragraph("Endereço", self.styles['GridLabel']), Paragraph(address_main, self.styles['GridValue'])],
                '', # Span col
                [Paragraph("Bairro", self.styles['GridLabel']), Paragraph(str(prop.neighborhood or "---"), self.styles['GridValue'])]
            ],
            # Linha 4
            [
                [Paragraph("Cidade", self.styles['GridLabel']), Paragraph(str(prop.city or "---"), self.styles['GridValue'])],
                [Paragraph("Estado", self.styles['GridLabel']), Paragraph(str(prop.state or "MS"), self.styles['GridValue'])],
                [Paragraph("CEP", self.styles['GridLabel']), Paragraph(str(prop.cep or "---"), self.styles['GridValue'])]
            ]
        ]
        
        table = Table(data, colWidths=[9*cm, 4.5*cm, 4.5*cm])
        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('SPAN', (0,2), (1,2)), # Span endereço
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_processed_image(self, file_source, width=None, height=None, max_width=18*cm, max_height=12*cm):
        """Prepara imagem a partir de um FileField ou caminho string para garantir orientação e proporções corretas"""
        from django.core.files.storage import default_storage
        try:
            if not file_source:
                return None
            
            # Se for uma string (caminho), abre via default_storage
            if isinstance(file_source, str):
                if not default_storage.exists(file_source):
                    return None
                f = default_storage.open(file_source, 'rb')
            else:
                # Se for um FileField
                f = file_source.open('rb')

            with f:
                with PILImage.open(f) as img:
                    # Corrigir orientação EXIF
                    img = ImageOps.exif_transpose(img)
                    
                    # Calcular proporções
                    img_w, img_h = img.size
                    aspect = img_w / float(img_h)
                    
                    if width and not height:
                        target_w = width
                        target_h = target_w / aspect
                    elif height and not width:
                        target_h = height
                        target_w = target_h * aspect
                    elif width and height:
                        target_w = width
                        target_h = height
                    else:
                        target_w = max_width
                        target_h = target_w / aspect
                        if target_h > max_height:
                            target_h = max_height
                            target_w = target_h * aspect
                    
                    # Salvar em buffer temporário para o ReportLab
                    temp_buffer = BytesIO()
                    # Converter para RGB se necessário (ex: RGBA -> RGB) para JPEG
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(temp_buffer, format="JPEG", quality=85)
                    temp_buffer.seek(0)
                    
                    return RLImage(temp_buffer, width=target_w, height=target_h)
        except Exception as e:
            print(f"Erro ao processar imagem: {e}")
            return None

    def _item_rows(self, items):
        """Retorna linhas de dados para uma lista de itens."""
        rows = []
        for item in items:
            code = item.product.code if (item.product and item.product.code) else "---"
            description = item.description or (item.product.name if item.product else (item.service.name if item.service else "---"))
            unit = "un"
            if item.product:
                unit = "mt" if item.product.unit_type == 'METRO' else "un"
            elif item.service:
                unit = item.service.unit_of_measure
            rows.append([
                Paragraph(code, self.styles['TableItem']),
                Paragraph(description, self.styles['TableItem']),
                Paragraph(str(item.quantity).replace('.', ','), self.styles['TableItem']),
                Paragraph(unit, self.styles['TableItem']),
                Paragraph(self._format_currency(item.total_price), self.styles['TableItem'])
            ])
        return rows

    def _build_grouped_items_table(self, include_types=None):
        """Constrói tabela de itens agrupados por etapa. Usada por BudgetPDFGenerator e CompletionPDFGenerator.
        include_types: lista de task_type strings para filtrar (ex: ['ORCAMENTO']). None = todas as etapas.
        """
        from decimal import Decimal

        col_widths = [2.5*cm, 8.5*cm, 2*cm, 2.5*cm, 2.5*cm]
        header_row = [[
            Paragraph("CÓDIGO", self.styles['TableHeader']),
            Paragraph("DESCRIÇÃO", self.styles['TableHeader']),
            Paragraph("QTD", self.styles['TableHeader']),
            Paragraph("UNID.", self.styles['TableHeader']),
            Paragraph("TOTAL", self.styles['TableHeader'])
        ]]

        task_qs = self.service_order.tasks.prefetch_related('items').order_by('scheduled_at')
        if include_types:
            task_qs = task_qs.filter(task_type__in=include_types)
        tasks = task_qs
        # Itens gerais (sem task) só aparecem quando não há filtro por tipo
        general_items = self.service_order.items.filter(task__isnull=True) if not include_types else self.service_order.items.none()

        data = list(header_row)
        span_commands = [
            ('BACKGROUND', (0,0), (-1,0), self.header_bg),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,1), (4,-1), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]

        for task in tasks:
            task_items = list(task.items.all())
            if not task_items:
                continue
            date_str = task.scheduled_at.strftime('%d/%m/%Y') if task.scheduled_at else ''
            task_label = task.get_task_type_display() + (f"  —  {date_str}" if date_str else "")
            group_idx = len(data)
            data.append([Paragraph(task_label, self.styles.get('TableSubHeader', self.styles['TableHeader'])), "", "", "", ""])
            span_commands.append(('SPAN', (0, group_idx), (-1, group_idx)))
            span_commands.append(('BACKGROUND', (0, group_idx), (-1, group_idx), self.bg_header))

            data.extend(self._item_rows(task_items))

            subtotal = sum((i.total_price for i in task_items), Decimal('0'))
            sub_idx = len(data)
            data.append([
                Paragraph("Subtotal da etapa", self.styles['SummaryLabel']),
                "", "", "",
                Paragraph(self._format_currency(subtotal), self.styles['SummaryValue'])
            ])
            span_commands.append(('SPAN', (0, sub_idx), (3, sub_idx)))
            span_commands.append(('ALIGN', (4, sub_idx), (4, sub_idx), 'RIGHT'))
            span_commands.append(('BACKGROUND', (0, sub_idx), (-1, sub_idx), self.bg_light))

        general_rows = self._item_rows(general_items)
        if general_rows:
            if len(data) > 1:
                gen_idx = len(data)
                data.append([Paragraph("Itens do Orçamento", self.styles.get('TableSubHeader', self.styles['TableHeader'])), "", "", "", ""])
                span_commands.append(('SPAN', (0, gen_idx), (-1, gen_idx)))
                span_commands.append(('BACKGROUND', (0, gen_idx), (-1, gen_idx), self.bg_header))
            data.extend(general_rows)

        if len(data) == 1:
            data.append([Paragraph("---", self.styles['TableItem']), Paragraph("Nenhum item detalhado", self.styles['TableItem']), "", "", ""])

        return Table(data, colWidths=col_widths), span_commands


class BudgetPDFGenerator(BasePDFGenerator):
    def __init__(self, service_order):
        super().__init__(service_order)
        self.doc_title = "Orçamento"

    def _get_order_info(self):
        elements = []
        tech_name = self._get_responsible_tech()
        inspection_date = "Não realizada"
        budget_task = self.service_order.tasks.filter(task_type='ORCAMENTO').first()
        if budget_task and budget_task.scheduled_at:
            inspection_date = budget_task.scheduled_at.strftime('%d/%m/%Y')

        elements.append(self._section_title("DADOS DO ATENDIMENTO"))
        elements.append(Spacer(1, 0.1*cm))

        data = [
            [Paragraph("Descrição do Problema:", self.styles['Label']), Paragraph(self.service_order.description or "Não informada", self.styles['Value'])],
            [Paragraph("Técnico Responsável:", self.styles['Label']), Paragraph(tech_name, self.styles['Value'])],
            [Paragraph("Data da Vistoria:", self.styles['Label']), Paragraph(inspection_date, self.styles['Value'])],
        ]
        table = Table(data, colWidths=[5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('BACKGROUND', (0,0), (0,-1), self.bg_light),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(self._section_title("DETALHAMENTO DOS ITENS"))
        elements.append(Spacer(1, 0.1*cm))
        exec_types = ['EXECUCAO', 'GARANTIA', 'RETORNO']
        has_exec = self.service_order.tasks.filter(task_type__in=exec_types).exists()
        include = exec_types if has_exec else None
        table, span_commands = self._build_grouped_items_table(include_types=include)
        table.setStyle(TableStyle(span_commands))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        return elements

    def _get_summary(self):
        from decimal import Decimal
        elements = []
        gross_total = self.service_order.total_value or Decimal('0')

        billable_types = ['EXECUCAO', 'GARANTIA', 'RETORNO']
        billable_tasks = list(self.service_order.tasks.filter(task_type__in=billable_types))
        task_discount = sum((t.discount or Decimal('0')) for t in billable_tasks)
        discount = task_discount if task_discount > 0 else (self.service_order.discount or Decimal('0'))

        net_total = gross_total - discount

        total_paid = sum(
            (b.get_total_paid() for b in self.service_order.billings.all()),
            Decimal('0')
        )
        remaining = net_total - total_paid

        summary_data = [
            [Paragraph("Frete", self.styles['SummaryLabel']), Paragraph(self._format_currency(0), self.styles['SummaryValue'])],
            [Paragraph("Subtotal", self.styles['SummaryLabel']), Paragraph(self._format_currency(gross_total), self.styles['SummaryValue'])],
            [Paragraph("Desconto", self.styles['SummaryLabel']), Paragraph(self._format_currency(discount), self.styles['SummaryValue'])],
        ]

        if total_paid > 0:
            summary_data.append([
                Paragraph("Pagamentos realizados", self.styles['SummaryLabel']),
                Paragraph(f"- {self._format_currency(total_paid)}", self.styles['SummaryValue'])
            ])
            summary_data.append([
                Paragraph("Saldo restante", self.styles['TotalFinalLabel']),
                Paragraph(self._format_currency(remaining), self.styles['TotalFinalValue'])
            ])
        else:
            summary_data.append([
                Paragraph("Total Final", self.styles['TotalFinalLabel']),
                Paragraph(self._format_currency(net_total), self.styles['TotalFinalValue'])
            ])

        total_row_idx = len(summary_data) - 1
        summary_table = Table(summary_data, colWidths=[10*cm, 3.5*cm])
        summary_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0, total_row_idx), (1, total_row_idx), self.bg_light),
        ]))

        wrapper = Table([[Spacer(1,1), summary_table]], colWidths=[4.5*cm, 13.5*cm])
        wrapper.setStyle(TableStyle([('ALIGN', (1,0), (1,0), 'RIGHT')]))

        elements.append(wrapper)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_footer(self):
        elements = []
        if self.service_order.client_observation:
            elements.append(self._section_title("OBSERVAÇÕES"))
            obs_table = Table([[Paragraph(str(self.service_order.client_observation), self.styles['TableItem'])]], colWidths=[18*cm])
            obs_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            elements.append(obs_table)
            elements.append(Spacer(1, 0.5*cm))
            
        return elements

    def _get_photos(self):
        elements = []
        photos = []
        for task in self.service_order.tasks.all():
            for media in task.medias.all():
                if not media.is_video() and media.file:
                    photos.append(media.file)
        if photos:
            elements.append(PageBreak())
            elements.append(self._section_title("REGISTROS FOTOGRÁFICOS"))
            elements.append(Spacer(1, 0.5*cm))
            img_data = []
            row = []
            for i, photo_file in enumerate(photos):
                img = self._get_processed_image(photo_file, max_width=8.5*cm, max_height=7*cm)
                if img:
                    row.append(img)
                    if (i + 1) % 2 == 0:
                        img_data.append(row)
                        row = []
            if row:
                if len(row) == 1: row.append("")
                img_data.append(row)
            table = Table(img_data, colWidths=[9*cm, 9*cm])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 15),
                ('TOPPADDING', (0,0), (-1,-1), 15),
                ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ]))
            elements.append(table)
        return elements

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        elements = []
        elements.extend(self._get_header(doc_title=self.doc_title))
        elements.extend(self._get_client_info())
        elements.extend(self._get_order_info())
        elements.extend(self._get_items_table())
        elements.extend(self._get_summary())
        elements.extend(self._get_footer())
        elements.extend(self._get_photos())
        doc.build(elements, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf

class CompletionPDFGenerator(BasePDFGenerator):
    def __init__(self, service_order):
        super().__init__(service_order)
        self.doc_title = "Relatório de Serviço"

    def _get_completion_info(self):
        elements = []
        status_display = self.service_order.get_status_display()
        finished_at_dt = None
        last_execution = self.service_order.tasks.filter(task_type='EXECUCAO', status='CONCLUIDO').order_by('-finished_at').first()
        if last_execution and last_execution.finished_at:
            finished_at_dt = last_execution.finished_at

        elements.append(self._section_title("DADOS DA FINALIZAÇÃO"))
        elements.append(Spacer(1, 0.1*cm))

        data = []
        if finished_at_dt:
            warranty_date = finished_at_dt + timezone.timedelta(days=365)
            data.append([Paragraph("Garantia do Serviço:", self.styles['Label']), Paragraph(f"Válida até {warranty_date.strftime('%d/%m/%Y')} (365 dias)", self.styles['Value'])])
        data.append([Paragraph("Descrição do Problema:", self.styles['Label']), Paragraph(self.service_order.description or "---", self.styles['Value'])])

        table = Table(data, colWidths=[5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('BACKGROUND', (0,0), (0,-1), self.bg_light),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(self._section_title("MATERIAIS E SERVIÇOS"))
        elements.append(Spacer(1, 0.1*cm))
        exec_types = ['EXECUCAO', 'GARANTIA', 'RETORNO']
        has_exec = self.service_order.tasks.filter(task_type__in=exec_types).exists()
        include = exec_types if has_exec else None
        table, span_commands = self._build_grouped_items_table(include_types=include)
        table.setStyle(TableStyle(span_commands))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        return elements

    def _get_summary(self):
        from decimal import Decimal
        elements = []
        gross_total = self.service_order.total_value or Decimal('0')

        billable_types = ['EXECUCAO', 'GARANTIA', 'RETORNO']
        billable_tasks = list(self.service_order.tasks.filter(task_type__in=billable_types))
        task_discount = sum((t.discount or Decimal('0')) for t in billable_tasks)
        discount = task_discount if task_discount > 0 else (self.service_order.discount or Decimal('0'))

        net_total = gross_total - discount

        summary_data = [
            [Paragraph("Subtotal", self.styles['SummaryLabel']), Paragraph(self._format_currency(gross_total), self.styles['SummaryValue'])],
            [Paragraph("Desconto", self.styles['SummaryLabel']), Paragraph(self._format_currency(discount), self.styles['SummaryValue'])],
            [Paragraph("Total do Serviço", self.styles['TotalFinalLabel']), Paragraph(self._format_currency(net_total), self.styles['TotalFinalValue'])],
        ]
        
        summary_table = Table(summary_data, colWidths=[10*cm, 3.5*cm])
        summary_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,2), (1,2), self.bg_light),
        ]))
        
        wrapper = Table([[Spacer(1,1), summary_table]], colWidths=[4.5*cm, 13.5*cm])
        wrapper.setStyle(TableStyle([('ALIGN', (1,0), (1,0), 'RIGHT')]))
        
        elements.append(wrapper)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_tasks_timeline(self):
        elements = []
        elements.append(self._section_title("CRONOGRAMA DE ETAPAS"))
        elements.append(Spacer(1, 0.1*cm))
        data = [['Etapa', 'Programado', 'Iniciado', 'Finalizado', 'Responsáveis', 'Status']]
        tasks = self.service_order.tasks.all().order_by('scheduled_at').prefetch_related('team_members__professional', 'team_members__role')
        for task in tasks:
            technicians = [
                f"{(tm.professional.name if getattr(tm, 'professional', None) and getattr(tm.professional, 'name', None) else 'Responsável')}"
                f"{(' (' + tm.role.name + ')' if getattr(tm, 'role', None) and getattr(tm.role, 'name', None) else '')}"
                for tm in task.team_members.all()
            ]
            scheduled_str = task.scheduled_at.strftime('%d/%m/%Y %H:%M') if getattr(task, 'scheduled_at', None) and task.scheduled_at else '---'
            started_str = task.started_at.strftime('%d/%m/%Y %H:%M') if getattr(task, 'started_at', None) and task.started_at else '---'
            finished_str = task.finished_at.strftime('%d/%m/%Y %H:%M') if getattr(task, 'finished_at', None) and task.finished_at else '---'
            data.append([
                Paragraph(task.get_task_type_display(), self.styles['SmallValue']),
                Paragraph(scheduled_str, self.styles['SmallValue']),
                Paragraph(started_str, self.styles['SmallValue']),
                Paragraph(finished_str, self.styles['SmallValue']),
                Paragraph(", ".join(technicians) or "---", self.styles['SmallValue']),
                Paragraph(task.get_status_display(), self.styles['SmallValue'])
            ])
        if len(data) == 1:
            data.append(["-", "-", "-", "-", "-", "-"])
        table = Table(data, colWidths=[3.5*cm, 3*cm, 3*cm, 3*cm, 4*cm, 1.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), self.bg_header),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_checklists(self):
        elements = []
        tasks = self.service_order.tasks.all().prefetch_related('checklist_responses__item', 'checklist_responses__medias')
        if not any(t.checklist_responses.exists() for t in tasks): return elements
        elements.append(self._section_title("CHECKLISTS DE VERIFICAÇÃO"))
        elements.append(Spacer(1, 0.2*cm))
        for task in tasks:
            responses = task.checklist_responses.all()
            if not responses.exists(): continue
            elements.append(Paragraph(f"Etapa: {task.get_task_type_display()} ({task.scheduled_at.strftime('%d/%m/%Y') if task.scheduled_at else '---'})", self.styles['Label']))
            elements.append(Spacer(1, 0.2*cm))
            checklist_data = []
            for resp in responses:
                status = " [X] " if resp.completed else " [ ] "
                item_elements = [Paragraph(f"<b>{status} {resp.item.name}</b>", self.styles['ChecklistItem'])]
                if resp.text_response: item_elements.append(Paragraph(f"Resposta: {resp.text_response}", self.styles['ChecklistResponse']))
                for media in resp.medias.all():
                    if media.is_video():
                        url = f"{settings.SITE_URL}{media.file.url}" if hasattr(settings, 'SITE_URL') else media.file.url
                        item_elements.append(Paragraph(f'<link href="{url}"><font color="blue">🎬 Ver Vídeo</font></link>', self.styles['ChecklistResponse']))
                    elif media.file:
                        img = self._get_processed_image(media.file, max_width=6*cm, max_height=5*cm)
                        if img: item_elements.append(img)

                checklist_data.append([item_elements])
            table = Table(checklist_data, colWidths=[18*cm])
            table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, self.grid_color), ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_general_media(self):
        elements = []
        photos, videos = [], []
        for task in self.service_order.tasks.all():
            for media in task.medias.all():
                if media.is_video(): videos.append(media)
                elif media.file:
                    photos.append(media.file)
        if photos or videos:
            elements.append(self._section_title("EVIDÊNCIAS GERAIS"))
            elements.append(Spacer(1, 0.3*cm))
            if videos:
                elements.append(Paragraph("VÍDEOS:", self.styles['Label']))
                for vid in videos:
                    url = f"{settings.SITE_URL}{vid.file.url}" if hasattr(settings, 'SITE_URL') else vid.file.url
                    elements.append(Paragraph(f'<link href="{url}"><font color="blue">🎬 Assistir Vídeo: {os.path.basename(vid.file.name)}</font></link>', self.styles['Normal']))
                elements.append(Spacer(1, 0.5*cm))
            if photos:
                elements.append(Paragraph("REGISTROS FOTOGRÁFICOS:", self.styles['Label']))
                img_data, row = [], []
                for i, photo_file in enumerate(photos):
                    img = self._get_processed_image(photo_file, max_width=8.5*cm, max_height=7*cm)
                    if img:
                        row.append(img)
                        if (i + 1) % 2 == 0: img_data.append(row); row = []
                if row: 
                    if len(row) == 1: row.append("")
                    img_data.append(row)
                table = Table(img_data, colWidths=[9*cm, 9*cm])
                table.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 15),
                    ('TOPPADDING', (0,0), (-1,-1), 15),
                    ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
                ]))
                elements.append(table)
        return elements

    def _get_signatures(self):
        elements = []
        tasks_with_signatures = self.service_order.tasks.filter(customer_signature__isnull=False).exclude(customer_signature='')
        
        if tasks_with_signatures.exists():
            elements.append(self._section_title("ASSINATURAS DE CONFORMIDADE"))
            elements.append(Spacer(1, 0.3*cm))
            
            sig_data = []
            row = []
            for i, task in enumerate(tasks_with_signatures):
                sig_img = self._get_processed_image(task.customer_signature, width=6*cm, height=3*cm)
                
                cell_elements = []
                if sig_img:
                    cell_elements.append(sig_img)
                
                cell_elements.append(Spacer(1, 0.1*cm))
                cell_elements.append(Paragraph(f"<b>{task.customer_name or 'Responsável'}</b>", self.styles['SmallLabel']))
                cell_elements.append(Paragraph(f"Etapa: {task.get_task_type_display()}", self.styles['SmallValue']))
                cell_elements.append(Paragraph(f"Data: {task.finished_at.strftime('%d/%m/%Y %H:%M') if task.finished_at else '---'}", self.styles['SmallValue']))
                
                row.append(cell_elements)
                
                if (i + 1) % 2 == 0:
                    sig_data.append(row)
                    row = []
            
            if row:
                if len(row) == 1:
                    row.append("")
                sig_data.append(row)
            
            table = Table(sig_data, colWidths=[9*cm, 9*cm])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                ('TOPPADDING', (0,0), (-1,-1), 10),
                ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))
            
        return elements

    def _get_footer(self):
        elements = []
        elements.append(Spacer(1, 0.5*cm))
        now = timezone.now().astimezone(timezone.get_current_timezone())
        elements.append(Paragraph(f"Relatório gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')}", self.styles['Normal']))
        elements.append(Paragraph("Este documento comprova a execução dos serviços e a verificação dos itens de controle.", self.styles['Normal']))
        return elements

    def _get_warranty_terms(self):
        """Página final com o Termo de Garantia de Serviços de Calhas e Rufos."""
        elements = []
        elements.append(PageBreak())

        elements.append(Paragraph("DOURADOS CALHAS", self.styles['WarrantyCompany']))
        elements.append(Paragraph(
            "AVENIDA ARAGOIÂNIA (GO-040), Nº 97, QD 80 LT 23 SALA 2<br/>GARAVELO B. GOIÂNIA-GO",
            self.styles['WarrantyCompany']
        ))
        elements.append(Spacer(1, 0.6*cm))
        elements.append(Paragraph("TERMO DE GARANTIA DE SERVIÇOS DE CALHAS E RUFOS", self.styles['WarrantyTitle']))
        elements.append(Spacer(1, 0.6*cm))

        elements.append(Paragraph("1. PRAZO DE GARANTIA", self.styles['WarrantyHeading']))
        elements.append(Paragraph(
            "A Dourados Calhas estabelece as seguintes garantias para os serviços realizados:",
            self.styles['WarrantyBody']
        ))
        elements.append(Paragraph(
            "• Garantia sobre as chapas: De acordo com o Código de Defesa do Consumidor (Lei nº 8.078/1990), os "
            "produtos e serviços duráveis possuem garantia legal de 90 (noventa) dias, porém a Dourados Calhas "
            "oferece uma garantia contratual de 1 ano (trezentos e sessenta e cinco dias). Essa extensão da "
            "garantia foi adotada para contemplar o período de estiagem, permitindo que o cliente tenha a "
            "oportunidade de verificar o desempenho do sistema durante um ciclo completo de chuvas.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "• Garantia sobre a vedação: A vedação assim como as chapas tem a garantia legal de 90 dias de "
            "acordo com o CDC, entretanto, a Dourados Calhas possui garantia 1 ano (trezentos e sessenta e "
            "cinco dias), permitindo que o cliente tenha a oportunidade de verificar o desempenho do sistema "
            "durante um ciclo completo de chuvas.",
            self.styles['WarrantyBullet']
        ))

        elements.append(Paragraph("2. COBERTURA DA GARANTIA", self.styles['WarrantyHeading']))
        elements.append(Paragraph("Esta garantia cobre exclusivamente:", self.styles['WarrantyBody']))
        elements.append(Paragraph("• Defeitos relacionados à execução do serviço.", self.styles['WarrantyBullet']))
        elements.append(Paragraph("• Vazamentos ou falhas decorrentes de instalação inadequada.", self.styles['WarrantyBullet']))
        elements.append(Paragraph("• A fixação e vedação de calhas e rufos realizadas pela Prestadora.", self.styles['WarrantyBullet']))

        elements.append(Paragraph("3. EXCLUSÕES DA GARANTIA", self.styles['WarrantyHeading']))
        elements.append(Paragraph("A garantia não cobre:", self.styles['WarrantyBody']))
        elements.append(Paragraph(
            "• Danos causados por falta de manutenção periódica, acúmulo de sujeira, folhas ou resíduos.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "• Problemas decorrentes de alterações ou intervenções realizadas por terceiros como reformas, "
            "perfurações ou modificações posteriores.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "• Danos causados por fenômenos naturais severos, como ventos extremos, granizo, quedas de "
            "árvores e/ou estruturas e desastres naturais.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "• Oxidação causada por agentes químicos, cloro de aquecedores de piscinas, resíduos industriais "
            "ou ambientes altamente corrosivos.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "Obs.: Todos os termos de exclusão de garantia estão de acordo com a Lei nº 8.078/1990 (Art. 26, "
            "inciso II; Art. 14, § 3º, inciso II; Art. 12, § 3º, inciso III) e a Lei nº 10.406/2002 (Art. 393).",
            self.styles['WarrantyBody']
        ))

        elements.append(Paragraph("4. PROCEDIMENTO PARA ACIONAMENTO DA GARANTIA", self.styles['WarrantyHeading']))
        elements.append(Paragraph("Para acionar a garantia, o cliente deve:", self.styles['WarrantyBody']))
        elements.append(Paragraph(
            "1. Entrar em contato com a Prestadora pelo telefone ou WhatsApp (62) 3224-0985.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "2. Informar detalhes do problema e apresentar este Termo de Garantia.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "3. Permitir acesso ao local para análise técnica do problema.",
            self.styles['WarrantyBullet']
        ))
        elements.append(Paragraph(
            "4. A Prestadora tem um prazo de 48 horas para verificar o problema após ser acionada, salvo em "
            "situações excepcionais que impossibilitem o cumprimento deste prazo.",
            self.styles['WarrantyBullet']
        ))

        elements.append(Paragraph("5. SOLUÇÕES OFERECIDAS", self.styles['WarrantyHeading']))
        elements.append(Paragraph(
            "Confirmado o defeito coberto pela garantia, a Prestadora se compromete a realizar os reparos "
            "necessários sem custo adicional, dentro de um prazo de 6 dias.",
            self.styles['WarrantyBody']
        ))

        elements.append(Paragraph("6. OBSERVAÇÕES FINAIS", self.styles['WarrantyHeading']))
        elements.append(Paragraph(
            "Este Termo de Garantia é complementar aos direitos previstos no Código de Defesa do Consumidor, "
            "não os excluindo ou limitando.",
            self.styles['WarrantyBody']
        ))

        return elements

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        elements = []
        elements.extend(self._get_header(doc_title=self.doc_title, show_validity=False))
        elements.extend(self._get_client_info())
        elements.extend(self._get_completion_info())
        elements.extend(self._get_items_table())
        elements.extend(self._get_summary())
        elements.extend(self._get_tasks_timeline())
        elements.extend(self._get_checklists())
        elements.extend(self._get_general_media())
        elements.extend(self._get_signatures())
        elements.extend(self._get_footer())
        elements.extend(self._get_warranty_terms())
        doc.build(elements, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf


class SalePDFGenerator(BasePDFGenerator):
    def __init__(self, sale):
        super().__init__(sale)  # sale.number used in footer/header
        self.sale = sale
        self.doc_title = "Pedido de Venda"

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setStrokeColor(self.grid_color)
        canvas.setLineWidth(0.5)
        canvas.line(1.5*cm, 1.2*cm, A4[0]-1.5*cm, 1.2*cm)
        company_info = f"{self.config.company_name or '---'}"
        if self.config.company_cnpj:
            company_info += f" - CNPJ: {self.config.company_cnpj}"
        footer_text = f"{company_info} | Venda nº {self.sale.number} | Pág. {canvas.getPageNumber()}"
        canvas.drawRightString(A4[0]-1.5*cm, 0.8*cm, footer_text)

        if self.sale.status == 'CANCELADO':
            canvas.saveState()
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColor(colors.red, alpha=0.15)
            canvas.translate(A4[0]/2, A4[1]/2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "CANCELADO")
            canvas.restoreState()

        canvas.restoreState()

    def _get_sale_header(self):
        """Cabeçalho específico da venda: sem 'Válido até' (não se aplica a um pedido já fechado),
        exibindo status atual no lugar."""
        elements = []

        logo_file = getattr(self.config, 'company_logo', None)
        img = None
        if logo_file:
            try:
                img = self._get_processed_image(logo_file, width=3.5*cm, height=2.5*cm)
            except Exception as e:
                print(f"Erro ao processar logo: {e}")
        logo_cell = img if img else Paragraph("LOGO", self.styles['CompanyTitle'])

        company_info = [
            Paragraph(f"<b>{self.config.company_name}</b>", self.styles['CompanyDetail']),
            Paragraph(f"CNPJ: {self.config.company_cnpj or '---'}", self.styles['CompanyDetail']),
            Paragraph(self.config.company_address or "---", self.styles['CompanyDetail']),
            Paragraph(f"Tel: {self.config.company_phone or '---'}", self.styles['CompanyDetail']),
            Paragraph(self.config.company_website or "", self.styles['CompanyDetail']),
        ]

        now = timezone.now().astimezone(timezone.get_current_timezone())
        doc_info_data = [
            [Paragraph("Emitido em:", self.styles['DocInfoLabel'])],
            [Paragraph(now.strftime('%d/%m/%Y'), self.styles['DocInfoValue'])],
            [Spacer(1, 0.1*cm)],
            [Paragraph("Pedido nº:", self.styles['DocInfoLabel'])],
            [Paragraph(str(self.sale.number), self.styles['DocInfoValue'])],
            [Spacer(1, 0.1*cm)],
            [Paragraph("Status:", self.styles['DocInfoLabel'])],
            [Paragraph(self.sale.get_status_display(), self.styles['DocInfoValue'])],
        ]
        doc_info_table = Table(doc_info_data, colWidths=[4*cm])
        doc_info_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
            ('TOPPADDING', (0,0), (-1,-1), 1),
        ]))

        header_data = [[logo_cell, company_info, doc_info_table]]
        header_table = Table(header_data, colWidths=[4.5*cm, 9.5*cm, 4*cm])
        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,0), 'CENTER'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'CENTER'),
        ]))

        elements.append(header_table)
        elements.append(Spacer(1, 0.2*cm))
        elements.append(self._section_title(self.doc_title))
        elements.append(Spacer(1, 0.3*cm))
        return elements

    def _get_sale_client_info(self):
        elements = []
        client = self.sale.client
        if not client:
            return elements

        phone_val = "---"
        if client.phones.exists():
            phone_val = client.phones.first().phone

        elements.append(self._section_title("DADOS DO CLIENTE"))
        elements.append(Spacer(1, 0.1*cm))

        data = [
            [
                [Paragraph("Cliente", self.styles['GridLabel']), Paragraph(str(client.display_name or "---"), self.styles['GridValue'])],
                [Paragraph("CPF/CNPJ", self.styles['GridLabel']), Paragraph(str(client.document or "---"), self.styles['GridValue'])],
                [Paragraph("Telefone", self.styles['GridLabel']), Paragraph(phone_val, self.styles['GridValue'])],
            ],
        ]
        table = Table(data, colWidths=[9*cm, 4.5*cm, 4.5*cm])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(table)

        if self.sale.delivery_address:
            elements.append(Spacer(1, 0.2*cm))
            address_line = self.sale.delivery_address
            if self.sale.delivery_number:
                address_line += f", {self.sale.delivery_number}"
            if self.sale.delivery_complement:
                address_line += f" - {self.sale.delivery_complement}"

            delivery_data = [
                [
                    [Paragraph("Destinatário", self.styles['GridLabel']), Paragraph(self.sale.delivery_name or str(client.display_name), self.styles['GridValue'])],
                    [Paragraph("Logradouro", self.styles['GridLabel']), Paragraph(address_line, self.styles['GridValue'])],
                    '',
                ],
                [
                    [Paragraph("Bairro", self.styles['GridLabel']), Paragraph(self.sale.delivery_neighborhood or "---", self.styles['GridValue'])],
                    [Paragraph("Cidade", self.styles['GridLabel']), Paragraph(self.sale.delivery_city or "---", self.styles['GridValue'])],
                    [Paragraph("UF / CEP", self.styles['GridLabel']), Paragraph(f"{self.sale.delivery_state or '---'} / {self.sale.delivery_cep or '---'}", self.styles['GridValue'])],
                ],
            ]
            delivery_table = Table(delivery_data, colWidths=[5*cm, 9*cm, 4*cm])
            delivery_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
                ('SPAN', (1, 0), (2, 0)),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('BACKGROUND', (0, 0), (-1, 0), self.bg_light),
            ]))
            elements.append(Paragraph("Endereço de Entrega", self.styles['SmallLabel']))
            elements.append(Spacer(1, 0.1*cm))
            elements.append(delivery_table)

        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_sale_info(self):
        elements = []
        elements.append(self._section_title("DADOS DA VENDA"))
        elements.append(Spacer(1, 0.1*cm))

        salesperson = self.sale.user.get_full_name() or self.sale.user.username
        payment_display = self.sale.get_payment_method_display() if self.sale.payment_method else "---"
        delivery_date = self.sale.delivery_date.strftime('%d/%m/%Y') if self.sale.delivery_date else "---"
        created_at = self.sale.created_at.strftime('%d/%m/%Y') if self.sale.created_at else "---"

        rows = [
            [Paragraph("Vendedor:", self.styles['Label']), Paragraph(salesperson, self.styles['Value'])],
            [Paragraph("Data da Venda:", self.styles['Label']), Paragraph(created_at, self.styles['Value'])],
            [Paragraph("Prazo de Entrega:", self.styles['Label']), Paragraph(delivery_date, self.styles['Value'])],
            [Paragraph("Forma de Pagamento:", self.styles['Label']), Paragraph(payment_display, self.styles['Value'])],
        ]
        if self.sale.external_po_number:
            rows.append([Paragraph("Nº Pedido do Cliente (PO):", self.styles['Label']), Paragraph(self.sale.external_po_number, self.styles['Value'])])

        table = Table(rows, colWidths=[5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
            ('BACKGROUND', (0, 0), (0, -1), self.bg_light),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(self._section_title("ITENS DO PEDIDO"))
        elements.append(Spacer(1, 0.1*cm))

        data = [[
            Paragraph("CÓDIGO", self.styles['TableHeader']),
            Paragraph("DESCRIÇÃO", self.styles['TableHeader']),
            Paragraph("QTD", self.styles['TableHeader']),
            Paragraph("UN.", self.styles['TableHeader']),
            Paragraph("UNIT.", self.styles['TableHeader']),
            Paragraph("DESC.", self.styles['TableHeader']),
            Paragraph("SUBTOTAL", self.styles['TableHeader']),
        ]]

        for item in self.sale.items.all():
            code = item.product.code if (item.product and item.product.code) else "---"
            description = item.product.name if item.product else "---"
            if item.variant and hasattr(item.variant, 'name'):
                description += f" ({item.variant.name})"
            unit = "mt" if item.product and item.product.unit_type == 'METRO' else "un"
            data.append([
                Paragraph(code, self.styles['TableItem']),
                Paragraph(description, self.styles['TableItem']),
                Paragraph(str(item.quantity).replace('.', ','), self.styles['TableItem']),
                Paragraph(unit, self.styles['TableItem']),
                Paragraph(self._format_currency(item.unit_price), self.styles['TableItem']),
                Paragraph(self._format_currency(item.discount) if item.discount else "—", self.styles['TableItem']),
                Paragraph(self._format_currency(item.subtotal), self.styles['TableItem']),
            ])

        if len(data) == 1:
            data.append([Paragraph("---", self.styles['TableItem']), Paragraph("Nenhum item", self.styles['TableItem']), "", "", "", "", ""])

        table = Table(data, colWidths=[2*cm, 6.5*cm, 1.5*cm, 1.5*cm, 2.5*cm, 2*cm, 2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.header_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        return elements

    def _get_summary(self):
        elements = []
        items_subtotal = sum(item.subtotal for item in self.sale.items.all())
        discount = self.sale.discount or 0
        surcharge = self.sale.surcharge or 0
        total = self.sale.total_amount or 0

        rows = [
            [Paragraph("Subtotal dos Itens", self.styles['SummaryLabel']), Paragraph(self._format_currency(items_subtotal), self.styles['SummaryValue'])],
        ]
        if discount:
            rows.append([Paragraph("Desconto", self.styles['SummaryLabel']), Paragraph(f"- {self._format_currency(discount)}", self.styles['SummaryValue'])])
        if surcharge:
            rows.append([Paragraph("Acréscimo", self.styles['SummaryLabel']), Paragraph(f"+ {self._format_currency(surcharge)}", self.styles['SummaryValue'])])

        billing = getattr(self.sale, 'billing', None)
        total_paid = billing.get_total_paid() if billing else 0

        if total_paid > 0:
            remaining = total - total_paid
            rows.append([Paragraph("Total do Pedido", self.styles['SummaryLabel']), Paragraph(self._format_currency(total), self.styles['SummaryValue'])])
            rows.append([Paragraph("Pagamentos Recebidos", self.styles['SummaryLabel']), Paragraph(f"- {self._format_currency(total_paid)}", self.styles['SummaryValue'])])
            rows.append([Paragraph("Saldo Restante", self.styles['TotalFinalLabel']), Paragraph(self._format_currency(remaining), self.styles['TotalFinalValue'])])
        else:
            rows.append([Paragraph("Total Final", self.styles['TotalFinalLabel']), Paragraph(self._format_currency(total), self.styles['TotalFinalValue'])])

        summary_table = Table(rows, colWidths=[10*cm, 3.5*cm])
        summary_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, -1), (1, -1), self.bg_light),
        ]))
        wrapper = Table([[Spacer(1, 1), summary_table]], colWidths=[4.5*cm, 13.5*cm])
        wrapper.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(wrapper)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_payment_conditions(self):
        elements = []
        billing = getattr(self.sale, 'billing', None)

        if billing and billing.installments.exists():
            elements.append(self._section_title("CONDIÇÕES DE PAGAMENTO"))
            elements.append(Spacer(1, 0.1*cm))

            data = [[
                Paragraph("PARCELA", self.styles['TableHeader']),
                Paragraph("VENCIMENTO", self.styles['TableHeader']),
                Paragraph("VALOR", self.styles['TableHeader']),
                Paragraph("FORMA", self.styles['TableHeader']),
                Paragraph("STATUS", self.styles['TableHeader']),
            ]]
            for inst in billing.installments.all().order_by('installment_number'):
                data.append([
                    Paragraph(f"{inst.installment_number}ª", self.styles['TableItem']),
                    Paragraph(inst.due_date.strftime('%d/%m/%Y'), self.styles['TableItem']),
                    Paragraph(self._format_currency(inst.amount), self.styles['TableItem']),
                    Paragraph(inst.payment_method.descricao if inst.payment_method else "---", self.styles['TableItem']),
                    Paragraph(inst.get_status_display(), self.styles['TableItem']),
                ])

            table = Table(data, colWidths=[2.5*cm, 4*cm, 4*cm, 4*cm, 3.5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.header_bg),
                ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

        return elements

    def _get_sale_notes(self):
        elements = []
        if self.sale.notes_customer:
            elements.append(self._section_title("OBSERVAÇÕES"))
            obs_table = Table([[Paragraph(str(self.sale.notes_customer), self.styles['TableItem'])]], colWidths=[18*cm])
            obs_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, self.grid_color),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(obs_table)
            elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_acceptance_section(self):
        elements = []
        elements.append(Spacer(1, 0.8*cm))
        elements.append(Paragraph(
            "Confirmo o recebimento dos produtos/serviços descritos neste pedido, em conformidade com as "
            "especificações e condições comerciais acordadas.",
            self.styles['TableItem']
        ))
        elements.append(Spacer(1, 1.2*cm))

        sig_data = [[
            Paragraph("Data: ____ / ____ / ______", self.styles['SmallValue']),
            Paragraph("Assinatura do Cliente: ________________________________", self.styles['SmallValue']),
        ]]
        sig_table = Table(sig_data, colWidths=[6*cm, 12*cm])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(sig_table)
        return elements

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        elements = []
        elements.extend(self._get_sale_header())
        elements.extend(self._get_sale_client_info())
        elements.extend(self._get_sale_info())
        elements.extend(self._get_items_table())
        elements.extend(self._get_summary())
        elements.extend(self._get_payment_conditions())
        elements.extend(self._get_sale_notes())
        elements.extend(self._get_acceptance_section())
        doc.build(elements, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
