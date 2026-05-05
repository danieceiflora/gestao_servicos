import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
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
            name='ChecklistItem',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#1F2937'),
            leftIndent=10
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

class BudgetPDFGenerator(BasePDFGenerator):
    def _get_order_info(self):
        elements = []
        elements.append(Paragraph(f"ORÇAMENTO DE SERVIÇO #{self.service_order.number}", self.styles['SectionHeader']))
        
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
        for item in self.service_order.items.all():
            description = item.description
            if not description:
                if item.product: description = item.product.name
                elif item.service: description = item.service.name
                else: description = "---"

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
                if len(row) == 1: row.append("")
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
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
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

class CompletionPDFGenerator(BasePDFGenerator):
    def _get_completion_info(self):
        elements = []
        elements.append(Paragraph(f"RELATÓRIO DE CONCLUSÃO DE SERVIÇO #{self.service_order.number}", self.styles['SectionHeader']))
        
        status_display = self.service_order.get_status_display()
        finished_at_dt = None
        finished_at_str = "Não finalizado"
        
        # Tenta pegar a data de finalização da última etapa de execução
        last_execution = self.service_order.tasks.filter(task_type='EXECUTION', status='COMPLETED').order_by('-finished_at').first()
        if last_execution and last_execution.finished_at:
            finished_at_dt = last_execution.finished_at
            finished_at_str = finished_at_dt.strftime('%d/%m/%Y %H:%M')

        data = [
            [Paragraph("Status Atual:", self.styles['Label']), Paragraph(status_display, self.styles['Value'])],
            [Paragraph("Data de Conclusão:", self.styles['Label']), Paragraph(finished_at_str, self.styles['Value'])],
        ]

        # Adiciona Garantia se estiver finalizado
        if finished_at_dt:
            warranty_date = finished_at_dt + timezone.timedelta(days=365)
            data.append([
                Paragraph("Garantia do Serviço:", self.styles['Label']),
                Paragraph(f"Válida até {warranty_date.strftime('%d/%m/%Y')} (365 dias)", self.styles['Value'])
            ])

        data.append([Paragraph("Descrição Original:", self.styles['Label']), Paragraph(self.service_order.description or "---", self.styles['Value'])])
        
        table = Table(data, colWidths=[5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_checklists(self):
        elements = []
        tasks_with_checklist = self.service_order.tasks.all().prefetch_related('checklist_responses__item', 'checklist_responses__medias')
        
        has_any_checklist = False
        for task in tasks_with_checklist:
            if task.checklist_responses.exists():
                has_any_checklist = True
                break
        
        if not has_any_checklist:
            return elements

        elements.append(Paragraph("CHECKLISTS DE VERIFICAÇÃO", self.styles['SectionHeader']))
        
        for task in tasks_with_checklist:
            responses = task.checklist_responses.all()
            if not responses.exists():
                continue
            
            elements.append(Paragraph(f"Etapa: {task.get_task_type_display()} ({task.scheduled_at.strftime('%d/%m/%Y') if task.scheduled_at else '---'})", self.styles['Label']))
            elements.append(Spacer(1, 0.2*cm))
            
            for resp in responses:
                status = " [X] " if resp.completed else " [ ] "
                elements.append(Paragraph(f"{status} {resp.item.name}", self.styles['ChecklistItem']))
                if resp.text_response:
                    elements.append(Paragraph(f"R: {resp.text_response}", self.styles['ChecklistResponse']))
                
                # Mídias do checklist
                media_elements = []
                for media in resp.medias.all():
                    if media.is_video():
                        # Link para vídeo com ícone 🎬
                        url = f"{settings.SITE_URL}{media.file.url}" if hasattr(settings, 'SITE_URL') else media.file.url
                        link = f'<link href="{url}"><font color="blue">🎬 Ver Vídeo</font></link>'
                        media_elements.append(Paragraph(link, self.styles['ChecklistResponse']))
                    elif media.file:
                        try:
                            if os.path.exists(media.file.path):
                                img = Image(media.file.path, width=4*cm, height=3*cm, kind='proportional')
                                media_elements.append(img)
                        except ValueError:
                            continue
                
                if media_elements:
                    t = Table([[m] for m in media_elements], colWidths=[15*cm])
                    t.setStyle(TableStyle([('LEFTPADDING', (0,0), (-1,-1), 20)]))
                    elements.append(t)

            elements.append(Spacer(1, 0.5*cm))
            
        return elements

    def _get_general_media(self):
        elements = []
        photos = []
        videos = []
        
        for task in self.service_order.tasks.all():
            for media in task.medias.all():
                if media.is_video():
                    videos.append(media)
                elif media.file:
                    try:
                        if os.path.exists(media.file.path):
                            photos.append(media.file.path)
                    except ValueError:
                        continue
        
        if photos or videos:
            elements.append(PageBreak())
            elements.append(Paragraph("EVIDÊNCIAS GERAIS", self.styles['SectionHeader']))
            elements.append(Spacer(1, 0.5*cm))
            
            if videos:
                elements.append(Paragraph("VÍDEOS ANEXADOS:", self.styles['Label']))
                for vid in videos:
                    url = f"{settings.SITE_URL}{vid.file.url}" if hasattr(settings, 'SITE_URL') else vid.file.url
                    link = f'<link href="{url}"><font color="blue">🎬 Assistir Vídeo: {os.path.basename(vid.file.name)}</font></link>'
                    elements.append(Paragraph(link, self.styles['Normal']))
                elements.append(Spacer(1, 0.5*cm))

            if photos:
                elements.append(Paragraph("FOTOS:", self.styles['Label']))
                img_data = []
                row = []
                for i, photo_path in enumerate(photos):
                    img = Image(photo_path, width=8*cm, height=6*cm, kind='proportional')
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
                    ('BOTTOMPADDING', (0,0), (-1,-1), 12),
                ]))
                elements.append(table)
            
        return elements

    def _get_footer(self):
        elements = []
        elements.append(Spacer(1, 1*cm))
        now = timezone.now().astimezone(timezone.get_current_timezone())
        elements.append(Paragraph(f"Relatório gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')}", self.styles['Normal']))
        elements.append(Paragraph("Este documento comprova a execução dos serviços e a verificação dos itens de controle.", self.styles['Normal']))
        return elements

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        elements = []
        elements.extend(self._get_header())
        elements.extend(self._get_client_info())
        elements.extend(self._get_completion_info())
        elements.extend(self._get_checklists())
        elements.extend(self._get_general_media())
        elements.extend(self._get_footer())
        doc.build(elements)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
