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

# --- ORDENS DE SERVIÇO & FLUXO OPERACIONAL ---

class ServiceOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Rascunho'
        INSPECTION = 'INSPECTION', 'Em Vistoria'
        BUDGETING = 'BUDGETING', 'Aguardando Orçamento'
        PENDING_APPROVAL = 'PENDING', 'Aguardando Aprovação'
        APPROVED = 'APPROVED', 'Aprovado / Pendente Execução'
        EXECUTING = 'EXECUTING', 'Em Execução'
        FINISHED = 'FINISHED', 'Finalizado'
        WARRANTY = 'WARRANTY', 'Em Garantia'
        CANCELLED = 'CANCELLED', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='service_orders', verbose_name="Imóvel")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="Status")
    
    description = models.TextField(verbose_name="Descrição do Problema/Solicitação", blank=True)
    technical_notes = models.TextField(verbose_name="Notas Técnicas/Vistoria", blank=True)
    
    # Datas
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_for = models.DateTimeField(null=True, blank=True, verbose_name="Agendado para")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado em")

    def __str__(self):
        return f"OS {self.id.hex[:8]} - {self.client_property.client.name}"

    @property
    def total_value(self):
        return sum(item.total_price for item in self.items.all())

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"

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
