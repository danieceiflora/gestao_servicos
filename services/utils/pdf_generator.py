import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.units import cm
from django.conf import settings
from integracoes.models import SystemConfig

class BudgetPDFGenerator:
    def __init__(self, service_order):
        self.service_order = service_order
        self.config = SystemConfig.load()
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='CompanyTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#111827'), # Gray 900
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#374151'), # Gray 700
            spaceBefore=12,
            spaceAfter=6,
            borderPadding=2,
            borderWidth=0,
            leftIndent=0
        ))
        self.styles.add(ParagraphStyle(
            name='Label',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#4B5563') # Gray 600
        ))
        self.styles.add(ParagraphStyle(
            name='Value',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1F2937') # Gray 800
        ))
        self.styles.add(ParagraphStyle(
            name='TotalValue',
            parent=self.styles['Normal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#059669'), # Emerald 600
            alignment=2 # Right
        ))

    def _get_header(self):
        elements = []
        
        # Logo and Company Info table
        logo_path = None
        if self.config.company_logo:
            try:
                logo_path = self.config.company_logo.path
            except ValueError:
                pass

        company_info = [
            [Paragraph(self.config.company_name or "---", self.styles['CompanyTitle'])],
            [Paragraph(f"CNPJ: {self.config.company_cnpj or '---'}", self.styles['Normal'])],
            [Paragraph(f"Endereço: {self.config.company_address or '---'}", self.styles['Normal'])],
            [Paragraph(f"Telefone: {self.config.company_phone or '---'} | Site: {self.config.company_website or '---'}", self.styles['Normal'])]
        ]

        if logo_path and os.path.exists(logo_path):
            img = Image(logo_path, width=3*cm, height=3*cm, kind='proportional')
            header_table = Table([[img, company_info]], colWidths=[4*cm, 14*cm])
        else:
            header_table = Table([[company_info]], colWidths=[18*cm])

        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,0), 'CENTER'),
        ]))
        
        elements.append(header_table)
        elements.append(Spacer(1, 1*cm))
        return elements

    def _get_client_info(self):
        elements = []
        elements.append(Paragraph("DADOS DO CLIENTE", self.styles['SectionHeader']))
        
        client = self.service_order.client_property.client
        prop = self.service_order.client_property
        
        data = [
            [Paragraph("Cliente:", self.styles['Label']), Paragraph(str(client.name or "---"), self.styles['Value'])],
            [Paragraph("Telefone:", self.styles['Label']), Paragraph(str(client.phones.first().phone if client.phones.exists() else "---"), self.styles['Value'])],
            [Paragraph("Endereço:", self.styles['Label']), Paragraph(str(prop.full_address or "---"), self.styles['Value'])],
        ]
        
        table = Table(data, colWidths=[3*cm, 15*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_order_info(self):
        elements = []
        elements.append(Paragraph(f"ORÇAMENTO DE SERVIÇO #{self.service_order.number}", self.styles['SectionHeader']))
        
        # Busca o técnico responsável (primeiro membro da equipe da primeira tarefa de vistoria/orçamento)
        tech_name = "Não identificado"
        inspection_date = "Não realizada"
        budget_task = self.service_order.tasks.filter(task_type='BUDGET').first()
        if budget_task:
            first_member = budget_task.team_members.first()
            if first_member:
                tech_name = first_member.professional.name
            
            if budget_task.scheduled_at:
                inspection_date = budget_task.scheduled_at.strftime('%d/%m/%Y')

        data = [
            [Paragraph("Descrição do Problema:", self.styles['Label']), Paragraph(self.service_order.description or "Não informada", self.styles['Value'])],
            [Paragraph("Técnico Responsável:", self.styles['Label']), Paragraph(tech_name, self.styles['Value'])],
            [Paragraph("Data da Vistoria:", self.styles['Label']), Paragraph(inspection_date, self.styles['Value'])],
        ]
        
        table = Table(data, colWidths=[5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(Paragraph("ITENS E SERVIÇOS", self.styles['SectionHeader']))
        
        data = [['Descrição', 'Quantidade']]
        
        # Adiciona APENAS Itens de Serviço (Produtos/Serviços detalhados)
        for item in self.service_order.items.all():
            description = item.description
            if not description:
                if item.product:
                    description = item.product.name
                elif item.service:
                    description = item.service.name
                else:
                    description = "---"

            data.append([
                Paragraph(description, self.styles['Value']),
                Paragraph(str(item.quantity).replace('.', ','), self.styles['Value'])
            ])
            
        if len(data) == 1:
            data.append(["Nenhum item detalhado", "-"])

        table = Table(data, colWidths=[15*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F3F4F6')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#374151')),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 1*cm))
        return elements

    def _get_photos(self):
        elements = []
        photos = []
        
        # Coleta todas as fotos de todas as etapas
        for task in self.service_order.tasks.all():
            for media in task.medias.all():
                if not media.is_video() and media.file:
                    try:
                        if os.path.exists(media.file.path):
                            photos.append(media.file.path)
                    except ValueError:
                        continue
        
        if photos:
            elements.append(PageBreak())
            elements.append(Paragraph("REGISTROS FOTOGRÁFICOS", self.styles['SectionHeader']))
            elements.append(Spacer(1, 0.5*cm))
            
            img_data = []
            row = []
            for i, photo_path in enumerate(photos):
                img = Image(photo_path, width=8*cm, height=6*cm, kind='proportional')
                row.append(img)
                if (i + 1) % 2 == 0:
                    img_data.append(row)
                    row = []
            
            if row:
                if len(row) == 1:
                    row.append("")
                img_data.append(row)
            
            table = Table(img_data, colWidths=[9*cm, 9*cm])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ]))
            elements.append(table)
            
        return elements

    def _get_footer(self):
        from django.utils import timezone
        elements = []
        
        if self.service_order.client_observation:
            elements.append(Paragraph("OBSERVAÇÕES ADICIONAIS", self.styles['SectionHeader']))
            elements.append(Paragraph(str(self.service_order.client_observation), self.styles['Value']))
            elements.append(Spacer(1, 0.5*cm))

        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph("Validade deste orçamento: 7 dias a partir da data de geração.", self.styles['Normal']))
        
        now = timezone.now().astimezone(timezone.get_current_timezone())
        elements.append(Paragraph(f"Gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')}", self.styles['Normal']))
            
        elements.append(Spacer(1, 1*cm))
        
        total_value = self.service_order.total_value or 0
        elements.append(Paragraph(f"VALOR TOTAL: R$ {total_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), self.styles['TotalValue']))
        
        return elements

    def generate(self):
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )

        elements = []
        elements.extend(self._get_header())
        elements.extend(self._get_client_info())
        elements.extend(self._get_order_info())
        elements.extend(self._get_items_table())
        elements.extend(self._get_footer())
        elements.extend(self._get_photos())

        doc.build(elements)
        
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
