import os
from io import BytesIO
from PIL import Image as PILImage, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.units import cm
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

    def _get_header(self, doc_title="Orçamento"):
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
            [Spacer(1, 0.1*cm)],
            [Paragraph("Válido até:", self.styles['DocInfoLabel'])],
            [Paragraph((now + timezone.timedelta(days=7)).strftime('%d/%m/%Y'), self.styles['DocInfoValue'])],
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

    def _get_client_info(self):
        elements = []
        client = self.service_order.client_property.client
        prop = self.service_order.client_property
        
        phone_val = "---"
        if client.phones.exists():
            phone_val = client.phones.first().phone

        elements.append(self._section_title("DADOS DO CLIENTE"))
        elements.append(Spacer(1, 0.1*cm))

        # Grid de informações do cliente estilo modelopdf.jpg
        data = [
            # Linha 1
            [
                [Paragraph("Cliente", self.styles['GridLabel']), Paragraph(str(client.name or "---"), self.styles['GridValue'])],
                [Paragraph("CPF/CNPJ", self.styles['GridLabel']), Paragraph("---", self.styles['GridValue'])],
                [Paragraph("Vendedor/Técnico", self.styles['GridLabel']), Paragraph("Dourados Calhas", self.styles['GridValue'])]
            ],
            # Linha 2
            [
                [Paragraph("Contato", self.styles['GridLabel']), Paragraph(str(phone_val), self.styles['GridValue'])],
                [Paragraph("Celular", self.styles['GridLabel']), Paragraph(str(phone_val), self.styles['GridValue'])],
            ],
            # Linha 3
            [
                [Paragraph("Endereço", self.styles['GridLabel']), Paragraph(str(prop.full_address or "---"), self.styles['GridValue'])],
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

class BudgetPDFGenerator(BasePDFGenerator):
    def __init__(self, service_order):
        super().__init__(service_order)
        self.doc_title = "Orçamento"

    def _get_order_info(self):
        elements = []
        tech_name = "Não identificado"
        inspection_date = "Não realizada"
        budget_task = self.service_order.tasks.filter(task_type='BUDGET').first()
        if budget_task:
            first_member = budget_task.team_members.first()
            if first_member: tech_name = first_member.professional.name
            if budget_task.scheduled_at: inspection_date = budget_task.scheduled_at.strftime('%d/%m/%Y')

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

        # Header da tabela em preto com texto branco
        data = [[
            Paragraph("CÓDIGO", self.styles['TableHeader']),
            Paragraph("DESCRIÇÃO", self.styles['TableHeader']),
            Paragraph("QTD", self.styles['TableHeader']),
            Paragraph("PREÇO UNIT.", self.styles['TableHeader']),
            Paragraph("TOTAL", self.styles['TableHeader'])
        ]]
        
        for item in self.service_order.items.all():
            code = item.product.code if (item.product and item.product.code) else "---"
            description = item.description or (item.product.name if item.product else (item.service.name if item.service else "---"))
            quantity = str(item.quantity).replace('.', ',')
            unit_price = self._format_currency(item.unit_price)
            total = self._format_currency(item.total_price)
            
            data.append([
                Paragraph(code, self.styles['TableItem']),
                Paragraph(description, self.styles['TableItem']),
                Paragraph(quantity, self.styles['TableItem']),
                Paragraph(unit_price, self.styles['TableItem']),
                Paragraph(total, self.styles['TableItem'])
            ])
            
        if len(data) == 1:
            data.append([Paragraph("---", self.styles['TableItem']), Paragraph("Nenhum item detalhado", self.styles['TableItem']), "", "", ""])
            
        table = Table(data, colWidths=[2.5*cm, 8.5*cm, 2*cm, 2.5*cm, 2.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), self.header_bg),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,1), (4,-1), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        return elements

    def _get_summary(self):
        elements = []
        gross_total = self.service_order.total_value or 0
        discount = self.service_order.discount or 0
        net_total = gross_total - discount

        summary_data = [
            [Paragraph("Frete", self.styles['SummaryLabel']), Paragraph(self._format_currency(0), self.styles['SummaryValue'])],
            [Paragraph("Subtotal", self.styles['SummaryLabel']), Paragraph(self._format_currency(gross_total), self.styles['SummaryValue'])],
            [Paragraph("Desconto", self.styles['SummaryLabel']), Paragraph(self._format_currency(discount), self.styles['SummaryValue'])],
            [Paragraph("Total Final", self.styles['TotalFinalLabel']), Paragraph(self._format_currency(net_total), self.styles['TotalFinalValue'])],
        ]
        
        summary_table = Table(summary_data, colWidths=[10*cm, 3.5*cm])
        summary_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,3), (1,3), self.bg_light), # Destaque no Total
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
        finished_at_str = "Não finalizado"
        last_execution = self.service_order.tasks.filter(task_type='EXECUTION', status='COMPLETED').order_by('-finished_at').first()
        if last_execution and last_execution.finished_at:
            finished_at_dt = last_execution.finished_at
            finished_at_str = finished_at_dt.strftime('%d/%m/%Y %H:%M')

        elements.append(self._section_title("DADOS DA FINALIZAÇÃO"))
        elements.append(Spacer(1, 0.1*cm))

        data = [
            [Paragraph("Data de Conclusão:", self.styles['Label']), Paragraph(finished_at_str, self.styles['Value'])],
        ]
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

        # Header da tabela em preto com texto branco
        data = [[
            Paragraph("CÓDIGO", self.styles['TableHeader']),
            Paragraph("DESCRIÇÃO", self.styles['TableHeader']),
            Paragraph("QTD", self.styles['TableHeader']),
            Paragraph("TOTAL", self.styles['TableHeader'])
        ]]
        
        for item in self.service_order.items.all():
            code = item.product.code if (item.product and item.product.code) else "---"
            description = item.description or (item.product.name if item.product else (item.service.name if item.service else "---"))
            quantity = str(item.quantity).replace('.', ',')
            total = self._format_currency(item.total_price)
            
            data.append([
                Paragraph(code, self.styles['TableItem']),
                Paragraph(description, self.styles['TableItem']),
                Paragraph(quantity, self.styles['TableItem']),
                Paragraph(total, self.styles['TableItem'])
            ])
            
        if len(data) == 1:
            data.append([Paragraph("---", self.styles['TableItem']), Paragraph("Nenhum item detalhado", self.styles['TableItem']), "", ""])
            
        table = Table(data, colWidths=[2.5*cm, 10.5*cm, 2.5*cm, 2.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), self.header_bg),
            ('GRID', (0,0), (-1,-1), 0.5, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,1), (3,-1), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        return elements

    def _get_summary(self):
        elements = []
        gross_total = self.service_order.total_value or 0
        discount = self.service_order.discount or 0
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
        data = [['Etapa', 'Data/Hora', 'Responsáveis', 'Status']]
        tasks = self.service_order.tasks.all().order_by('scheduled_at').prefetch_related('team_members__professional', 'team_members__role')
        for task in tasks:
            technicians = [f"{tm.professional.name}{' (' + tm.role.name + ')' if tm.role else ''}" for tm in task.team_members.all()]
            date_str = (task.finished_at or task.scheduled_at).strftime('%d/%m/%Y %H:%M') if (task.finished_at or task.scheduled_at) else "---"
            data.append([Paragraph(task.get_task_type_display(), self.styles['SmallValue']), Paragraph(date_str, self.styles['SmallValue']), Paragraph(", ".join(technicians) or "---", self.styles['SmallValue']), Paragraph(task.get_status_display(), self.styles['SmallValue'])])
        if len(data) == 1: data.append(["-", "-", "-", "-"])
        table = Table(data, colWidths=[4*cm, 3.5*cm, 7.5*cm, 3*cm])
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
            elements.append(PageBreak())
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

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        elements = []
        elements.extend(self._get_header(doc_title=self.doc_title))
        elements.extend(self._get_client_info())
        elements.extend(self._get_completion_info())
        elements.extend(self._get_items_table())
        elements.extend(self._get_summary())
        elements.extend(self._get_tasks_timeline())
        elements.extend(self._get_checklists())
        elements.extend(self._get_general_media())
        elements.extend(self._get_signatures())
        elements.extend(self._get_footer())
        doc.build(elements, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
