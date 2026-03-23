from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

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

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

# --- CLIENTES & CONTATOS ---

class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name="Nome Completo")
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True, verbose_name="CPF")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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
    cep = models.CharField(max_length=9, verbose_name="CEP")
    address = models.CharField(max_length=255, verbose_name="Logradouro")
    number = models.CharField(max_length=20, verbose_name="Número")
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Profissional"
        verbose_name_plural = "Profissionais"

class ProfessionalAvailability(models.Model):
    DAYS_OF_WEEK = [
        (0, 'Segunda-feira'),
        (1, 'Terça-feira'),
        (2, 'Quarta-feira'),
        (3, 'Quinta-feira'),
        (4, 'Sexta-feira'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name="Dia da Semana")
    start_time = models.TimeField(verbose_name="Início")
    end_time = models.TimeField(verbose_name="Fim")

    class Meta:
        verbose_name = "Disponibilidade"
        verbose_name_plural = "Disponibilidades"
        ordering = ['day_of_week', 'start_time']

# --- ORDENS DE SERVIÇO & FLUXO OPERACIONAL ---

class ServiceOrder(models.Model):
    class Status(models.TextChoices):
        WAITING_VISIT = 'WAITING_VISIT', 'Aguardando visita inicial'
        WAITING_BUDGET = 'WAITING_BUDGET', 'Aguardando envio de orçamento'
        BUDGET_SCHEDULED = 'BUDGET_SCHEDULED', 'Orçamento Agendado'
        WAITING_APPROVAL = 'WAITING_APPROVAL', 'Aguardando Aprovação do Cliente'
        APPROVED_WAITING_SCHEDULE = 'APPROVED_WAITING_SCHEDULE', 'Aprovado - Aguardando Agendamento de execução'
        WAITING_EXECUTION = 'WAITING_EXECUTION', 'Aguardando Execução'
        FINISHED = 'FINISHED', 'Finalizado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='service_orders', verbose_name="Imóvel")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.WAITING_BUDGET, verbose_name="Status")
    # ...
    
    description = models.TextField(verbose_name="Descrição do Problema/Solicitação", blank=True)
    technical_notes = models.TextField(verbose_name="Notas Técnicas/Vistoria", blank=True)
    
    # Datas
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Agendamentos Distintos
    budget_scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name="Visita de Orçamento Agendada para")
    execution_scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name="Execução de Serviço Agendada para")
    
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado em")

    def __str__(self):
        return f"OS {self.id.hex[:8]} - {self.client_property.client.name}"

    @property
    def total_value(self):
        return sum(item.total_price for item in self.items.all())

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"

# --- AGENDAMENTO & BLOQUEIOS ---

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

class ServiceOrderTeam(models.Model):
    class Category(models.TextChoices):
        INSPECTION = 'INSPECTION', 'Vistoria/Orçamento'
        EXECUTION = 'EXECUTION', 'Execução/Instalação'
        WARRANTY = 'WARRANTY', 'Garantia'

    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='team_members')
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name='service_alocations')
    role = models.ForeignKey(ProfessionalRole, on_delete=models.SET_NULL, null=True, verbose_name="Função no Serviço")
    category = models.CharField(
        max_length=20, 
        choices=Category.choices, 
        default=Category.EXECUTION,
        verbose_name="Categoria de Atuação"
    )

    class Meta:
        verbose_name = "Membro da Equipe"
        verbose_name_plural = "Equipe do Serviço"
        unique_together = ('service_order', 'professional', 'category')

class ServiceItem(models.Model):
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255, verbose_name="Serviço/Material")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário")

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    class Meta:
        verbose_name = "Item de Serviço"

class ServiceMedia(models.Model):
    class MediaType(models.TextChoices):
        INSPECTION = 'INSPECTION', 'Vistoria (Antes)'
        EXECUTION = 'EXECUTION', 'Execução (Durante)'
        FINAL = 'FINISHED', 'Finalizado (Depois)'

    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='medias')
    file = models.FileField(upload_to='services/%Y/%m/%d/', verbose_name="Arquivo (Foto/Vídeo)")
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.INSPECTION)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_video(self):
        return self.file.name.lower().endswith(('.mp4', '.mov', '.avi'))

    class Meta:
        verbose_name = "Mídia de Serviço"
