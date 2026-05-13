from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal, ROUND_HALF_UP
import uuid

MONEY_PLACES = Decimal('0.01')


def quantize_money(value):
    return (value or Decimal('0')).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

# --- SISTEMA DE USUÁRIOS & AUTENTICAÇÃO ---

class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        COLLABORATOR = 'COLLABORATOR', 'Colaborador'
        MANAGER = 'MANAGER', 'Gerente'

    role = models.CharField(
        max_length=20, 
        choices=Roles.choices, 
        default=Roles.COLLABORATOR,
        verbose_name="Papel/Função"
    )
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Telefone/WhatsApp")

    @property
    def is_manager(self):
        return self.is_superuser or self.role in [self.Roles.ADMIN, self.Roles.MANAGER]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

# --- CLIENTES & CONTATOS ---

class Client(models.Model):
    CLIENT_TYPE_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Tipo de cliente
    client_type = models.CharField(
        max_length=2,
        choices=CLIENT_TYPE_CHOICES,
        default='PF',
        verbose_name="Tipo de Cliente"
    )
    
    # ============ CAMPOS COMUNS ============
    # Nome completo (PF) ou Razão Social (PJ)
    name = models.CharField(
        max_length=255,
        verbose_name="Nome Completo / Razão Social"
    )
    
    # ============ PESSOA FÍSICA ============
    cpf = models.CharField(
        max_length=14,
        unique=True,
        null=True,
        blank=True,
        verbose_name="CPF"
    )
    rg = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="RG"
    )
    
    # ============ PESSOA JURÍDICA ============
    trade_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Nome Fantasia"
    )
    cnpj = models.CharField(
        max_length=18,
        unique=True,
        null=True,
        blank=True,
        verbose_name="CNPJ"
    )
    state_registration = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Inscrição Estadual"
    )
    municipal_registration = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Inscrição Municipal"
    )
    contact_person = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Responsável/Contato"
    )
    
    # ============ CAMPOS DE AUDITORIA ============
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ============ PROPRIEDADES ============
    @property
    def document(self):
        """Retorna CPF ou CNPJ dependendo do tipo"""
        return self.cpf if self.client_type == 'PF' else self.cnpj
    
    @property
    def display_name(self):
        """Nome para exibição (considera nome fantasia)"""
        if self.client_type == 'PJ' and self.trade_name:
            return self.trade_name
        return self.name
    
    # ============ VALIDAÇÃO ============
    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        
        if self.client_type == 'PF':
            if self.cpf:
                # Valida formato CPF
                cpf_limpo = re.sub(r'\D', '', self.cpf)
                if len(cpf_limpo) != 11:
                    raise ValidationError({'cpf': 'CPF deve ter 11 dígitos'})
            
            # Limpa campos de PJ
            self.trade_name = None
            self.cnpj = None
            self.state_registration = None
            self.municipal_registration = None
            self.contact_person = None
            
        elif self.client_type == 'PJ':
            if self.cnpj:
                # Valida formato CNPJ
                cnpj_limpo = re.sub(r'\D', '', self.cnpj)
                if len(cnpj_limpo) != 14:
                    raise ValidationError({'cnpj': 'CNPJ deve ter 14 dígitos'})
            
            # Limpa campos de PF
            self.cpf = None
            self.rg = None

    def __str__(self):
        doc = self.document or "Sem documento"
        return f"{self.display_name} ({doc})"

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

class ClientPhone(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='phones')
    phone = models.CharField(max_length=20, verbose_name="Telefone")
    is_primary = models.BooleanField(default=False, verbose_name="Principal/WhatsApp")

    class Meta:
        verbose_name = "Telefone do Cliente"

class ClientEmail(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='emails')
    email = models.EmailField(verbose_name="E-mail")
    is_primary = models.BooleanField(default=False, verbose_name="Principal")

    class Meta:
        verbose_name = "E-mail do Cliente"

# --- IMÓVEIS ---

class Property(models.Model):
    class PropertyType(models.TextChoices):
        CASA = 'CASA', 'Casa'
        PREDIO = 'PREDIO', 'Prédio'
        SOBRADO = 'SOBRADO', 'Sobrado'
        OUTRO = 'OUTRO', 'Outro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='properties', verbose_name="Proprietário")
    classification = models.CharField(
        max_length=20, 
        choices=PropertyType.choices, 
        default=PropertyType.CASA,
        verbose_name="Tipo de Imóvel"
    )
    
    # Endereço
    cep = models.CharField(max_length=9, verbose_name="CEP", null=True, blank=True)
    address = models.CharField(max_length=255, verbose_name="Logradouro")
    number = models.CharField(max_length=20, verbose_name="Número", null=True, blank=True)
    complement = models.CharField(max_length=255, null=True, blank=True, verbose_name="Complemento")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    city = models.CharField(max_length=100, verbose_name="Cidade")
    state = models.CharField(max_length=2, verbose_name="UF")

    # Geolocalização
    latitude = models.DecimalField(
        max_length=20,
        max_digits=22, 
        decimal_places=16, 
        null=True, 
        blank=True,
        verbose_name="Latitude"
    )
    longitude = models.DecimalField(
        max_length=20,
        max_digits=22, 
        decimal_places=16, 
        null=True, 
        blank=True,
        verbose_name="Longitude"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_address(self):
        components = [
            self.address,
            self.number,
            self.complement,
            self.neighborhood,
        ]

        city_state = []
        if self.city:
            city_state.append(self.city)
        if self.state:
            city_state.append(self.state)
        if city_state:
            components.append(' - '.join(city_state))

        components.append('Brasil')

        cleaned = [str(part).strip() for part in components if part]
        return ", ".join(cleaned)

    @property
    def gps_address(self):
        """Endereço sem o complemento para melhor precisão nas buscas do Google Maps/Waze"""
        components = []
        if self.address:
            addr = self.address
            if self.number:
                addr += f", {self.number}"
            components.append(addr)
        
        if self.neighborhood:
            components.append(self.neighborhood)
            
        if self.city:
            city_str = self.city
            if self.state:
                city_str += f" - {self.state}"
            components.append(city_str)
            
        return ", ".join(filter(bool, components))

    def __str__(self):
        return f"{self.classification} - {self.address}, {self.number}"

    class Meta:
        verbose_name = "Imóvel"
        verbose_name_plural = "Imóveis"

# --- PROFISSIONAIS & COLABORADORES ---

class ProfessionalRole(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome da Função")
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0, 
        verbose_name="Comissão (%)",
        help_text="Percentual de comissão padrão para esta função"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Função Profissional"
        verbose_name_plural = "Funções Profissionais"

class WorkSchedule(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome da Escala (Ex: Padrão, Manhã)")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Escala de Trabalho"
        verbose_name_plural = "Escalas de Trabalho"

class WorkScheduleDay(models.Model):
    DAYS_OF_WEEK = [
        (0, 'Segunda-feira'),
        (1, 'Terça-feira'),
        (2, 'Quarta-feira'),
        (3, 'Quinta-feira'),
        (4, 'Sexta-feira'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.CASCADE, related_name='days')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name="Dia da Semana")
    start_time = models.TimeField(verbose_name="Início")
    end_time = models.TimeField(verbose_name="Fim")

    class Meta:
        verbose_name = "Dia da Escala"
        verbose_name_plural = "Dias da Escala"
        ordering = ['day_of_week', 'start_time']

class Professional(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='professional_profile', verbose_name="Usuário Vinculado")
    name = models.CharField(max_length=255, verbose_name="Nome Completo")
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True, verbose_name="CPF")
    phone = models.CharField(max_length=20, verbose_name="Telefone/WhatsApp")
    email = models.EmailField(verbose_name="E-mail", null=True, blank=True)
    
    # Endereço (Opcional)
    cep = models.CharField(max_length=9, verbose_name="CEP", null=True, blank=True)
    address = models.CharField(max_length=255, verbose_name="Logradouro", null=True, blank=True)
    number = models.CharField(max_length=20, verbose_name="Número", null=True, blank=True)
    complement = models.CharField(max_length=255, null=True, blank=True, verbose_name="Complemento")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro", null=True, blank=True)
    city = models.CharField(max_length=100, verbose_name="Cidade", null=True, blank=True)
    state = models.CharField(max_length=2, verbose_name="UF", null=True, blank=True)
    
    # Financeiro
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Salário Base")
    
    roles = models.ManyToManyField(ProfessionalRole, related_name='professionals', verbose_name="Funções")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    
    work_schedule = models.ForeignKey(WorkSchedule, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Horário/Escala de Trabalho", related_name="professionals", help_text="Selecione a escala padrão de disponibilidade deste colaborador.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Profissional"
        verbose_name_plural = "Profissionais"


class ProfessionalScheduleBlock(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name='schedule_blocks', verbose_name="Profissional")
    start_at = models.DateTimeField(verbose_name="Início do Bloqueio")
    end_at = models.DateTimeField(verbose_name="Fim do Bloqueio")
    reason = models.CharField(max_length=255, verbose_name="Motivo (Ex: Férias, Folga, Manutenção)")
    is_all_day = models.BooleanField(default=False, verbose_name="Dia Inteiro")

    def __str__(self):
        return f"Bloqueio: {self.professional.name} ({self.start_at.strftime('%d/%m %H:%M')})"

    class Meta:
        verbose_name = "Bloqueio de Agenda"
        verbose_name_plural = "Bloqueios de Agenda"
        ordering = ['-start_at']

# --- SERVIÇOS DO CATÁLOGO & CHECKLISTS ---

class ServiceCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nome da Categoria")
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Categoria de Serviço"
        verbose_name_plural = "Categorias de Serviços"
        ordering = ['name']


class ChecklistTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nome do Modelo/Grupo")
    description = models.TextField(verbose_name="Descrição", blank=True)
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Modelo de Check-list"
        verbose_name_plural = "Modelos de Check-list"


class Service(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nome do Serviço")
    description = models.TextField(verbose_name="Descrição", blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Base")
    unit_of_measure = models.CharField(max_length=50, verbose_name="Unidade de Medida", default="un")
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='services', verbose_name="Categoria")
    
    # Vínculo com modelo de checklist (opcional)
    checklist_template = models.ForeignKey(ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='services', verbose_name="Modelo de Check-list")
    
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"
        ordering = ['name']


class ServiceChecklistItem(models.Model):
    class EvidenceType(models.TextChoices):
        TEXT = 'TEXT', 'Texto'
        PHOTO = 'PHOTO', 'Foto'
        VIDEO = 'VIDEO', 'Vídeo'

    # Pode pertencer a um serviço específico OU a um template global
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='checklist_items', verbose_name="Serviço", null=True, blank=True)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='items', verbose_name="Modelo", null=True, blank=True)
    
    name = models.CharField(max_length=255, verbose_name="Nome do Item")
    description = models.TextField(verbose_name="Descrição/Instrução", blank=True)
    evidence_type = models.CharField(
        max_length=10, 
        choices=EvidenceType.choices, 
        default=EvidenceType.TEXT,
        verbose_name="Tipo de Evidência"
    )
    is_required = models.BooleanField(default=True, verbose_name="Obrigatório")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem de Exibição")

    def __str__(self):
        owner = self.service.name if self.service else self.template.name
        return f"{owner} - {self.name}"

    class Meta:
        verbose_name = "Item de Check-list"
        verbose_name_plural = "Itens de Check-list"
        ordering = ['order', 'id']

# --- PRODUTOS ---

class Product(models.Model):
    class UnitType(models.TextChoices):
        UNIT = 'UNIT', 'Unidade (un)'
        METER = 'METER', 'Metro (mt)'

    name = models.CharField(max_length=255, unique=True, verbose_name="Produto")
    code = models.CharField(max_length=60, unique=True, null=True, blank=True, verbose_name="Código")
    unit_type = models.CharField(max_length=10, choices=UnitType.choices, default=UnitType.UNIT, verbose_name="Unidade de Venda")
    default_unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Preço Padrão")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['name']

# --- ORDENS DE SERVIÇO ---

class ServiceOrder(models.Model):
    class Status(models.TextChoices):
        WAITING_VISIT = 'WAITING_VISIT', 'Aguardando visita inicial'
        BUDGET_SCHEDULED = 'BUDGET_SCHEDULED', 'Orçamento Agendado'
        BUDGET_DONE_WAITING_SEND = 'BUDGET_DONE_WAITING_SEND', 'Orçamento realizado, aguardando envio'
        WAITING_APPROVAL = 'WAITING_APPROVAL', 'Orçamento enviado - aguardando aprovação'
        APPROVED_WAITING_SCHEDULE = 'APPROVED_WAITING_SCHEDULE', 'Aprovado pelo cliente - Aguardando Agendamento de execução'
        REJECTED_BY_CLIENT = 'REJECTED_BY_CLIENT', 'Reprovado pelo cliente'
        WAITING_EXECUTION = 'WAITING_EXECUTION', 'Aguardando Execução'
        WAITING_PAYMENT = 'WAITING_PAYMENT', 'Aguardando Pagamento'
        PARTIAL_PAYMENT = 'PARTIAL_PAYMENT', 'Pagamento Parcial'
        FINISHED = 'FINISHED', 'Finalizado'
        CANCELLED = 'CANCELLED', 'Cancelado'
        WARRANTY = 'WARRANTY', 'Em Garantia'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True, null=True, blank=True, verbose_name="Número da OS")
    client_property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='service_orders', verbose_name="Imóvel")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.WAITING_VISIT, verbose_name="Status")
    is_recurrent = models.BooleanField(default=False, verbose_name="É Recorrente?")
    
    description = models.TextField(verbose_name="Descrição do Problema/Solicitação", blank=True)
    technical_notes = models.TextField(verbose_name="Notas Técnicas Gerais", blank=True)
    client_observation = models.TextField(verbose_name="Observação para o Cliente", blank=True, null=True)
    
    # Valores e Pagamento
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Valor Estimado Total (R$)")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto (R$)")

    # Integração com Chatwoot (orçamento)
    chatwoot_budget_message_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="ID da Mensagem de Orçamento (Chatwoot)")
    chatwoot_budget_conversation_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="ID da Conversa (Chatwoot)")
    client_budget_response = models.TextField(null=True, blank=True, verbose_name="Resposta do Cliente ao Orçamento")
    client_budget_responded_at = models.DateTimeField(null=True, blank=True, verbose_name="Cliente respondeu o orçamento em")
    client_budget_approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Cliente aprovou o orçamento em")
    
    # Controle de Cobrança
    pix_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Cobrança/PIX enviada em")
    
    # Origem da OS
    origin_date = models.DateField(null=True, blank=True, verbose_name="Data de Origem")
    originator = models.ForeignKey(
        Professional, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='originated_orders',
        verbose_name="Originador (Vendedor)"
    )
    
    # Datas de Auditoria
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado em")
    warranty_until = models.DateField(null=True, blank=True, verbose_name="Garantia Válida até")

    def save(self, *args, **kwargs):
        if not self.number:
            from django.db.models import Max
            max_number = ServiceOrder.objects.aggregate(Max('number'))['number__max']
            self.number = (max_number or 1000) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        numero_visual = self.number if self.number else self.number
        return f"OS #{numero_visual} - {self.client_property.client.name}"

    @property
    def total_value(self):
        items_total = sum((item.total_price for item in self.items.all()), Decimal('0'))
        tasks_total = sum((task.value for task in self.tasks.all() if task.value), Decimal('0'))
        return quantize_money(items_total + tasks_total)

    @property
    def total_paid(self):
        paid_total = sum((payment.amount for payment in self.payments.all()), Decimal('0'))
        return quantize_money(paid_total)

    @property
    def balance_due(self):
        return quantize_money(self.total_value - self.total_paid - quantize_money(self.discount))

    def update_status(self):
        """Lógica centralizada de atualização de status da OS"""
        from datetime import timedelta
        import django.utils.timezone

        # Sempre atualiza o valor estimado para bater com o total líquido (Total - Desconto)
        self.estimated_value = self.total_value - self.discount

        tasks = self.tasks.all()
        
        # 1. Prioridade: Garantia
        if tasks.filter(task_type=ServiceOrderTask.TaskType.WARRANTY).exists():
            if tasks.filter(task_type=ServiceOrderTask.TaskType.WARRANTY, status=ServiceOrderTask.TaskStatus.COMPLETED).exists():
                self.status = self.Status.FINISHED
            else:
                self.status = self.Status.WARRANTY
            self.save()
            return

        # 2. Verificar Pagamentos
        if self.total_paid + self.discount >= self.total_value and self.total_value > 0:
            self.status = self.Status.FINISHED
            if not self.finished_at:
                self.finished_at = django.utils.timezone.now()
            self.save()
            return
        elif self.total_paid > 0:
            self.status = self.Status.PARTIAL_PAYMENT
            self.save()
            return

        # 3. Lógica baseada em Tasks
        budget_tasks = tasks.filter(task_type=ServiceOrderTask.TaskType.BUDGET)
        exec_tasks = tasks.filter(task_type=ServiceOrderTask.TaskType.EXECUTION)

        # Se todas as execuções acabaram, aguarda pagamento
        if exec_tasks.exists() and not exec_tasks.exclude(status=ServiceOrderTask.TaskStatus.COMPLETED).exists():
            self.status = self.Status.WAITING_PAYMENT
        
        # Se tem execução agendada ou em andamento
        elif exec_tasks.filter(status__in=[ServiceOrderTask.TaskStatus.SCHEDULED, ServiceOrderTask.TaskStatus.IN_PROGRESS]).exists():
            self.status = self.Status.WAITING_EXECUTION

        # Se tem execução aprovada mas não agendada
        elif exec_tasks.filter(is_approved=True).exists():
            self.status = self.Status.APPROVED_WAITING_SCHEDULE

        # Se orçamento foi concluído mas não aprovado
        elif budget_tasks.filter(status=ServiceOrderTask.TaskStatus.COMPLETED).exists():
            self.status = self.Status.BUDGET_DONE_WAITING_SEND

        # Se tem orçamento agendado
        elif budget_tasks.filter(status=ServiceOrderTask.TaskStatus.SCHEDULED).exists():
            self.status = self.Status.BUDGET_SCHEDULED
        
        self.save()

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"


class ServiceOrderTask(models.Model):
    class TaskType(models.TextChoices):
        BUDGET = 'BUDGET', 'Vistoria/Orçamento'
        EXECUTION = 'EXECUTION', 'Execução/Instalação'
        WARRANTY = 'WARRANTY', 'Garantia'

    class TaskStatus(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Agendado'
        IN_PROGRESS = 'IN_PROGRESS', 'Em Andamento'
        COMPLETED = 'COMPLETED', 'Concluído'
        CANCELLED = 'CANCELLED', 'Cancelado'
        NOT_EXECUTED = 'NOT_EXECUTED', 'Não Executado'

    PAYMENT_METHODS = [
        ('PIX', 'PIX'),
        ('CREDIT_CARD', 'Cartão de Crédito'),
        ('DEBIT_CARD', 'Cartão de Débito'),
        ('CASH', 'Dinheiro'),
        ('TRANSFER', 'Transferência Bancária'),
        ('BOLETO', 'Boleto'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='tasks', verbose_name="Ordem de Serviço")
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.EXECUTION, verbose_name="Tipo de Etapa")
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.SCHEDULED, verbose_name="Status")
    
    # Aprovação e Pagamento (específico da Task)
    is_approved = models.BooleanField(default=False, verbose_name="Aprovado pelo Cliente?")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True, verbose_name="Método de Pagamento Preferencial")

    # Datas e Horários
    scheduled_at = models.DateTimeField(verbose_name="Agendado para")
    scheduled_end_at = models.DateTimeField(null=True, blank=True, verbose_name="Data Fim de Agendamento")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Iniciado em")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado em")
    
    # Valor da Tarefa
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Valor do Serviço")
    
    notes = models.TextField(verbose_name="Observações Técnicas desta Etapa", blank=True)
    
    # Assinatura Digital do Cliente (Salva apenas o caminho do arquivo)
    customer_signature = models.CharField(max_length=255, null=True, blank=True, verbose_name="Caminho da Assinatura")
    customer_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nome de quem assinou")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        numero_visual = self.service_order.number if self.service_order.number else "S/N"
        return f"{self.get_task_type_display()} - OS #{numero_visual}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Ao salvar qualquer task, atualiza o status da OS pai
        self.service_order.update_status()

    class Meta:
        verbose_name = "Etapa de Serviço"
        verbose_name_plural = "Etapas de Serviço"
        ordering = ['scheduled_at']


class TaskChecklistResponse(models.Model):
    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='checklist_responses', verbose_name="Etapa")
    item = models.ForeignKey(ServiceChecklistItem, on_delete=models.CASCADE, related_name='responses', verbose_name="Item do Check-list")
    
    completed = models.BooleanField(default=False, verbose_name="Concluído")
    text_response = models.TextField(blank=True, null=True, verbose_name="Resposta em Texto")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Resposta: {self.item.name} na OS #{self.task.service_order.number}"

    class Meta:
        verbose_name = "Resposta de Check-list"
        verbose_name_plural = "Respostas de Check-list"
        unique_together = ('task', 'item')


class ChecklistResponseMedia(models.Model):
    response = models.ForeignKey(TaskChecklistResponse, on_delete=models.CASCADE, related_name='medias', verbose_name="Resposta")
    file = models.FileField(upload_to='checklist/evidence/%Y/%m/%d/', verbose_name="Arquivo de Evidência")
    created_at = models.DateTimeField(auto_now_add=True)

    def is_video(self):
        return self.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv'))

    class Meta:
        verbose_name = "Mídia de Check-list"
        verbose_name_plural = "Mídias de Check-list"


class ServiceItem(models.Model):
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='items')
    
    # Vínculo opcional à etapa
    task = models.ForeignKey(
        ServiceOrderTask,
        on_delete=models.CASCADE,
        related_name='items',
        null=True,
        blank=True,
        verbose_name="Etapa Específica",
        help_text="Deixe vazio para itens do orçamento geral. Preencha se o item foi adicionado durante uma etapa."
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_items', verbose_name="Produto")
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_items', verbose_name="Serviço do Catálogo")
    
    description = models.CharField(max_length=255, verbose_name="Descrição Manual/Complemento")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário")

    @property
    def total_price(self):
        return quantize_money(self.quantity * self.unit_price)
    
    def __str__(self):
        task_info = f" (Etapa: {self.task.get_task_type_display()})" if self.task else " (Orçamento Geral)"
        return f"{self.description} - Qtd: {self.quantity}{task_info}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.service_order.update_status()

    def delete(self, *args, **kwargs):
        order = self.service_order
        super().delete(*args, **kwargs)
        order.update_status()

    class Meta:
        verbose_name = "Item de Serviço"


class ServicePayment(models.Model):
    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='payments', verbose_name="Ordem de Serviço")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Pago")
    payment_method = models.CharField(max_length=20, choices=ServiceOrderTask.PAYMENT_METHODS, verbose_name="Método de Pagamento")
    paid_at = models.DateTimeField(verbose_name="Data do Pagamento")
    notes = models.CharField(max_length=255, blank=True, verbose_name="Observações")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order.update_status()

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ['-paid_at']


class ServiceOrderTeam(models.Model):
    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='team_members', verbose_name="Etapa/Tarefa", null=True, blank=True)
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name='service_alocations')
    role = models.ForeignKey(ProfessionalRole, on_delete=models.SET_NULL, null=True, verbose_name="Função no Serviço")

    class Meta:
        verbose_name = "Membro da Equipe"
        verbose_name_plural = "Equipe do Serviço"
        unique_together = ('task', 'professional')


class Occurrence(models.Model):
    class OccurrenceCategory(models.TextChoices):
        BLOCKING = 'BLOCKING', 'Impeditiva'
        MATERIAL_REQUEST = 'MATERIAL_REQUEST', 'Solicitação de Material'
        GENERAL = 'GENERAL', 'Ocorrência'

    class OccurrenceType(models.TextChoices):
        DELAY = 'DELAY', 'Atraso'
        MATERIAL_MISSING = 'MATERIAL_MISSING', 'Falta de Material'
        CUSTOMER_ABSENT = 'CUSTOMER_ABSENT', 'Cliente Ausente'
        IMPEDIMENT = 'IMPEDIMENT', 'Impedimento no Local'
        WARRANTY_ISSUE = 'WARRANTY_ISSUE', 'Acionamento de Garantia'
        OTHER = 'OTHER', 'Outro'

    class OccurrenceStatus(models.TextChoices):
        REGISTERED = 'REGISTERED', 'Registrada'
        RESOLVED = 'RESOLVED', 'Resolvida'

    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='occurrences', verbose_name="Etapa/Tarefa")
    category = models.CharField(max_length=20, choices=OccurrenceCategory.choices, default=OccurrenceCategory.GENERAL, verbose_name="Categoria")
    occurrence_type = models.CharField(max_length=20, choices=OccurrenceType.choices, default=OccurrenceType.OTHER, verbose_name="Tipo de Ocorrência")
    description = models.TextField(verbose_name="Descrição")
    status = models.CharField(max_length=20, choices=OccurrenceStatus.choices, default=OccurrenceStatus.REGISTERED, verbose_name="Status")
    observation = models.TextField(verbose_name="Observação (Resolução)", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    def __str__(self):
        return f"{self.get_occurrence_type_display()} - OS {self.task.service_order.number}"

    class Meta:
        verbose_name = "Ocorrência"
        verbose_name_plural = "Ocorrências"


class ServiceMedia(models.Model):
    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='medias', verbose_name="Etapa/Tarefa", null=True, blank=True)
    occurrence = models.ForeignKey(Occurrence, on_delete=models.CASCADE, related_name='medias', verbose_name="Ocorrência", null=True, blank=True)
    file = models.FileField(upload_to='services/%Y/%m/%d/', verbose_name="Arquivo (Foto/Vídeo)")
    created_at = models.DateTimeField(auto_now_add=True)

    def is_video(self):
        return self.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv'))

    class Meta:
        verbose_name = "Mídia de Serviço"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='push_subscriptions',
        verbose_name="Usuário"
    )
    endpoint = models.TextField(verbose_name="Endpoint", unique=True)
    p256dh = models.TextField(verbose_name="Chave P256DH")
    auth = models.TextField(verbose_name="Chave Auth")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Inscrição de Notificação Push"
        verbose_name_plural = "Inscrições de Notificações Push"
        ordering = ['-created_at']

    def __str__(self):
        return f"Push Subscription - {self.user.username}"
