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
        self._setup_custom_styles()
        self.grid_color = colors.HexColor('#9CA3AF') # Gray 400 - Darker lines
        self.bg_light = colors.HexColor('#F9FAFB') # Gray 50
        self.bg_header = colors.HexColor('#F3F4F6') # Gray 100

    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='CompanyTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#111827'),
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1F2937'), # Gray 800
            spaceBefore=12,
            spaceAfter=8,
            borderPadding=2,
            borderWidth=0,
            leftIndent=0,
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='Label',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#374151') # Gray 700
        ))
        self.styles.add(ParagraphStyle(
            name='Value',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#111827') # Gray 900
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
            name='TotalValue',
            parent=self.styles['Normal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#059669'),
            alignment=2
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

    def _get_header(self):
        elements = []
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
            img = RLImage(logo_path, width=3*cm, height=3*cm, kind='proportional')
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
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
            ('BACKGROUND', (0,0), (0,-1), self.bg_light),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_processed_image(self, img_path, max_width=18*cm, max_height=12*cm):
        """Prepara imagem com Pillow para garantir orientação e proporções corretas"""
        try:
            if not os.path.exists(img_path):
                return None
            
            with PILImage.open(img_path) as img:
                # Corrigir orientação EXIF
                img = ImageOps.exif_transpose(img)
                
                # Calcular proporções
                img_w, img_h = img.size
                aspect = img_w / float(img_h)
                
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
            print(f"Erro ao processar imagem {img_path}: {e}")
            return None

class BudgetPDFGenerator(BasePDFGenerator):
    def _get_order_info(self):
        elements = []
        elements.append(Paragraph(f"ORÇAMENTO DE SERVIÇO #{self.service_order.number}", self.styles['SectionHeader']))
        tech_name = "Não identificado"
        inspection_date = "Não realizada"
        budget_task = self.service_order.tasks.filter(task_type='BUDGET').first()
        if budget_task:
            first_member = budget_task.team_members.first()
            if first_member: tech_name = first_member.professional.name
            if budget_task.scheduled_at: inspection_date = budget_task.scheduled_at.strftime('%d/%m/%Y')

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
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
            ('BACKGROUND', (0,0), (0,-1), self.bg_light),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(Paragraph("ITENS E SERVIÇOS", self.styles['SectionHeader']))
        data = [['Descrição', 'Quantidade', 'Total']]
        for item in self.service_order.items.all():
            description = item.description or (item.product.name if item.product else (item.service.name if item.service else "---"))
            quantity = str(item.quantity).replace('.', ',')
            total = f"R$ {item.total_price:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            data.append([
                Paragraph(description, self.styles['Value']),
                Paragraph(quantity, self.styles['Value']),
                Paragraph(total, self.styles['Value'])
            ])
        if len(data) == 1:
            data.append(["Nenhum item detalhado", "-", "-"])
        table = Table(data, colWidths=[11*cm, 2.5*cm, 4.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), self.bg_header),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#1F2937')),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('ALIGN', (1,1), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'RIGHT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
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
                        if os.path.exists(media.file.path): photos.append(media.file.path)
                    except ValueError: continue
        if photos:
            elements.append(PageBreak())
            elements.append(Paragraph("REGISTROS FOTOGRÁFICOS", self.styles['SectionHeader']))
            elements.append(Spacer(1, 0.5*cm))
            img_data = []
            row = []
            for i, photo_path in enumerate(photos):
                img = self._get_processed_image(photo_path, max_width=8.5*cm, max_height=7*cm)
                if img:
                    row.append(img)
                    if (i + 1) % 2 == 0:
                        img_data.append(row)
                        row = []
            if row:
                if len(row) == 1: row.append("")
                img_data.append(row)
            table = Table(img_data, colWidths=[9*cm, 9*cm])
            table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('BOTTOMPADDING', (0,0), (-1,-1), 15)]))
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
        elements.append(Paragraph("RESUMO DA EXECUÇÃO", self.styles['SectionHeader']))
        status_display = self.service_order.get_status_display()
        finished_at_dt = None
        finished_at_str = "Não finalizado"
        last_execution = self.service_order.tasks.filter(task_type='EXECUTION', status='COMPLETED').order_by('-finished_at').first()
        if last_execution and last_execution.finished_at:
            finished_at_dt = last_execution.finished_at
            finished_at_str = finished_at_dt.strftime('%d/%m/%Y %H:%M')

        data = [
            [Paragraph("Ordem de Serviço:", self.styles['Label']), Paragraph(f"#{self.service_order.number}", self.styles['Value'])],
            [Paragraph("Status Atual:", self.styles['Label']), Paragraph(status_display, self.styles['Value'])],
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
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
            ('BACKGROUND', (0,0), (0,-1), self.bg_light),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_items_table(self):
        elements = []
        elements.append(Paragraph("ITENS E VALORES DO SERVIÇO", self.styles['SectionHeader']))
        data = [['Descrição', 'Quantidade', 'Valor']]
        items_total = 0

        for item in self.service_order.items.all():
            description = item.description or (item.product.name if item.product else (item.service.name if item.service else "---"))
            quantity = str(item.quantity).replace('.', ',')
            item_total = item.total_price or 0
            items_total += item_total
            item_total_display = f"R$ {item_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            data.append([
                Paragraph(description, self.styles['SmallValue']),
                Paragraph(quantity, self.styles['SmallValue']),
                Paragraph(item_total_display, self.styles['SmallValue'])
            ])

        has_items = len(data) > 1
        if not has_items:
            data.append(["Nenhum item detalhado", "-", "-"])
        else:
            total_display = f"R$ {items_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            data.append([
                Paragraph("<b>Total dos itens</b>", self.styles['Value']),
                "",
                Paragraph(f"<b>{total_display}</b>", self.styles['Value'])
            ])

        table = Table(data, colWidths=[11*cm, 2.5*cm, 4.5*cm])
        table_style = [
            ('BACKGROUND', (0,0), (-1,0), self.bg_header),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#1F2937')),
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (1,1), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ]

        if has_items:
            total_row_index = len(data) - 1
            table_style.extend([
                ('BACKGROUND', (0,total_row_index), (-1,total_row_index), self.bg_light),
                ('FONTNAME', (0,total_row_index), (-1,total_row_index), 'Helvetica-Bold'),
            ])

        table.setStyle(TableStyle(table_style))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
        return elements

    def _get_tasks_timeline(self):
        elements = []
        elements.append(Paragraph("CRONOGRAMA DE ETAPAS", self.styles['SectionHeader']))
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
            ('GRID', (0,0), (-1,-1), 0.8, self.grid_color),
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
        elements.append(Paragraph("CHECKLISTS DE VERIFICAÇÃO", self.styles['SectionHeader']))
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
                        img = self._get_processed_image(media.file.path, max_width=6*cm, max_height=5*cm)
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
                    try:
                        if os.path.exists(media.file.path): photos.append(media.file.path)
                    except ValueError: continue
        if photos or videos:
            elements.append(PageBreak())
            elements.append(Paragraph("EVIDÊNCIAS GERAIS", self.styles['SectionHeader']))
            if videos:
                elements.append(Paragraph("VÍDEOS:", self.styles['Label']))
                for vid in videos:
                    url = f"{settings.SITE_URL}{vid.file.url}" if hasattr(settings, 'SITE_URL') else vid.file.url
                    elements.append(Paragraph(f'<link href="{url}"><font color="blue">🎬 Assistir Vídeo: {os.path.basename(vid.file.name)}</font></link>', self.styles['Normal']))
                elements.append(Spacer(1, 0.5*cm))
            if photos:
                elements.append(Paragraph("REGISTROS FOTOGRÁFICOS:", self.styles['Label']))
                img_data, row = [], []
                for i, photo_path in enumerate(photos):
                    img = self._get_processed_image(photo_path, max_width=8.5*cm, max_height=7*cm)
                    if img:
                        row.append(img)
                        if (i + 1) % 2 == 0: img_data.append(row); row = []
                if row: row.append(""); img_data.append(row)
                table = Table(img_data, colWidths=[9*cm, 9*cm])
                table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('BOTTOMPADDING', (0,0), (-1,-1), 15)]))
                elements.append(table)
        return elements

    def _get_footer(self):
        elements = [Spacer(1, 1*cm)]
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
        elements.extend(self._get_items_table())
        elements.extend(self._get_tasks_timeline())
        elements.extend(self._get_checklists())
        elements.extend(self._get_general_media())
        elements.extend(self._get_footer())
        doc.build(elements)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
