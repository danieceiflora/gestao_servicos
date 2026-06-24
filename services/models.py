from django.db import models
from django.db.models import Sum, F
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid
from .utils import fiscal_logic
from integracoes.models import SystemConfig

MONEY_PLACES = Decimal('0.01')


def quantize_money(value):
    return (value or Decimal('0')).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

# --- SISTEMA DE USUÁRIOS & AUTENTICAÇÃO ---

class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        COLLABORATOR = 'COLABORADOR', 'Colaborador'
        MANAGER = 'GERENTE', 'Gerente'

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

class BusinessEntityBase(models.Model):
    ENTITY_TYPE_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    client_type = models.CharField(
        max_length=2,
        choices=ENTITY_TYPE_CHOICES,
        default='PF',
        verbose_name="Tipo (PF/PJ)"
    )
    
    name = models.CharField(
        max_length=255,
        verbose_name="Nome Completo / Razão Social"
    )
    
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
        null=True, blank=True,
        verbose_name="Inscrição Estadual"
    )
    municipal_registration = models.CharField(
        max_length=20,
        null=True, blank=True,
        verbose_name="Inscrição Municipal"
    )
    contact_person = models.CharField(
        max_length=255,
        null=True, blank=True,
        verbose_name="Responsável/Contato"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

    @property
    def document(self):
        return self.cpf if self.client_type == 'PF' else self.cnpj
    
    @property
    def display_name(self):
        if self.client_type == 'PJ' and self.trade_name:
            return self.trade_name
        return self.name
    
    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        
        if self.client_type == 'PF':
            if self.cpf:
                cpf_limpo = re.sub(r'\D', '', self.cpf)
                if len(cpf_limpo) != 11:
                    raise ValidationError({'cpf': 'CPF deve ter 11 dígitos'})
            self.trade_name = None
            self.cnpj = None
            self.state_registration = None
            self.municipal_registration = None
            self.contact_person = None
            
        elif self.client_type == 'PJ':
            if self.cnpj:
                cnpj_limpo = re.sub(r'\D', '', self.cnpj)
                if len(cnpj_limpo) != 14:
                    raise ValidationError({'cnpj': 'CNPJ deve ter 14 dígitos'})
            self.cpf = None
            self.rg = None


class Client(BusinessEntityBase):
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Limite de Crédito (R$)")

    def __str__(self):
        doc = self.document or "Sem documento"
        return f"{self.display_name} ({doc})"

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['name']


class Supplier(BusinessEntityBase):
    phone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Telefone")
    email = models.EmailField(null=True, blank=True, verbose_name="E-mail")
    address = models.CharField(max_length=255, null=True, blank=True, verbose_name="Endereço")
    notes = models.TextField(null=True, blank=True, verbose_name="Observações")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        ordering = ['name']


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
    ibge_code = models.CharField(max_length=7, null=True, blank=True, verbose_name="Código IBGE do Município")

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
        TEXTO = 'TEXTO', 'Texto'
        FOTO = 'FOTO', 'Foto'
        VIDEO = 'VIDEO', 'Vídeo'

    # Pode pertencer a um serviço específico OU a um template global
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='checklist_items', verbose_name="Serviço", null=True, blank=True)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='items', verbose_name="Modelo", null=True, blank=True)
    
    name = models.CharField(max_length=255, verbose_name="Nome do Item")
    description = models.TextField(verbose_name="Descrição/Instrução", blank=True)
    evidence_type = models.CharField(
        max_length=10, 
        choices=EvidenceType.choices, 
        default=EvidenceType.TEXTO,
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

class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nome da Categoria")
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Categoria de Produto"
        verbose_name_plural = "Categorias de Produtos"
        ordering = ['name']


class Product(models.Model):
    class UnitType(models.TextChoices):
        UNIDADE = 'UNIDADE', 'Unidade (un)'
        METRO = 'METRO', 'Metro (mt)'
        M2 = 'M2', 'Metro Quadrado (m²)'
        LITRO = 'LITRO', 'Litro (lt)'
        QUILO = 'QUILO', 'Quilo (kg)'

    class Format(models.TextChoices):
        SIMPLES = 'SIMPLES', 'Simples'
        COM_VARIACOES = 'COM_VARIACOES', 'Com variações'
        COM_COMPOSICAO = 'COM_COMPOSICAO', 'Com composição'

    class Type(models.TextChoices):
        PRODUTO = 'PRODUTO', 'Produto'
        SERVICO = 'SERVICO', 'Serviço'
        PRODUTO_ACABADO = 'PRODUTO_ACABADO', 'Produto acabado'
        MATERIA_PRIMA = 'MATERIA_PRIMA', 'Matéria prima'

    name = models.CharField(max_length=255, unique=True, verbose_name="Produto")
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        verbose_name="Categoria"
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        verbose_name="Fornecedor Padrão"
    )
    code = models.CharField(max_length=60, unique=True, null=True, blank=True, verbose_name="Código")
    barcode = models.CharField(max_length=14, blank=True, null=True, verbose_name="Código de Barras (GTIN/EAN)")
    image = models.ImageField(upload_to='products/', null=True, blank=True, verbose_name="Imagem do Produto")
    unit_type = models.CharField(max_length=10, choices=UnitType.choices, default=UnitType.UNIDADE, verbose_name="Unidade de Venda")
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.SIMPLES, verbose_name="Formato")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.PRODUTO, verbose_name="Tipo")
    
    # Dados Fiscais
    ncm = models.CharField(max_length=8, blank=True, null=True, verbose_name="NCM", help_text="Nomenclatura Comum do Mercosul (8 dígitos)")
    cest = models.CharField(max_length=7, blank=True, null=True, verbose_name="CEST", help_text="Código Especificador da Substituição Tributária (7 dígitos)")
    cfop_padrao = models.CharField(max_length=4, blank=True, null=True, verbose_name="CFOP Padrão")
    origem_mercadoria = models.IntegerField(default=0, verbose_name="Origem da Mercadoria", choices=[
        (0, '0 - Nacional'),
        (1, '1 - Estrangeira - Importação direta'),
        (2, '2 - Estrangeira - Adquirida no mercado interno'),
        (3, '3 - Nacional, mercadoria ou bem com Conteúdo de Importação superior a 40%'),
        (4, '4 - Nacional, cuja produção tenha sido feita em conformidade com os processos produtivos básicos'),
        (5, '5 - Nacional, mercadoria ou bem com Conteúdo de Importação inferior ou igual a 40%'),
        (6, '6 - Estrangeira - Importação direta, sem similar nacional, constante em lista de Resolução CAMEX'),
        (7, '7 - Estrangeira - Adquirida no mercado interno, sem similar nacional, constante em lista de Resolução CAMEX'),
        (8, '8 - Nacional, mercadoria ou bem com Conteúdo de Importação superior a 70%'),
    ])
    
    # Tributação (CST/CSOSN)
    csosn = models.CharField(max_length=3, blank=True, null=True, verbose_name="CSOSN", help_text="Código de Situação da Operação no Simples Nacional")
    cst_icms = models.CharField(max_length=2, blank=True, null=True, verbose_name="CST ICMS", help_text="Código de Situação Tributária do ICMS (Regime Normal)")
    cst_pis = models.CharField(max_length=2, blank=True, null=True, verbose_name="CST PIS")
    cst_cofins = models.CharField(max_length=2, blank=True, null=True, verbose_name="CST COFINS")
    
    # Alíquotas IBPT (Transparência de Impostos)
    aliquota_ibpt_fed = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Alíquota IBPT Federal (%)")
    aliquota_ibpt_est = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Alíquota IBPT Estadual (%)")
    aliquota_ibpt_mun = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Alíquota IBPT Municipal (%)")

    preco_custo = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Preço de Custo")
    preco_custo_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Custo Total")
    preco_venda_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Preço Venda Total")

    default_unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Preço Padrão")
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Atual")
    min_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Mínimo")
    max_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Máximo")
    weight = models.DecimalField(max_digits=8, decimal_places=3, default=0, verbose_name="Peso Bruto (kg)")
    width = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Largura (cm)")
    height = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Altura (cm)")
    depth = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Profundidade (cm)")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def reduce_stock(self, quantity, user=None, reason=None, notes=None, service_order=None):
        """
        Reduz o estoque do produto e, se for composto, reduz também os componentes.
        """
        from django.db import transaction
        from .models import StockMovement
        
        with transaction.atomic():
            # Reduz o estoque do produto principal
            self.current_stock -= quantity
            self.save()

            # Registra a movimentação
            StockMovement.objects.create(
                product=self,
                quantity=quantity,
                movement_type=StockMovement.MovementType.SAIDA,
                reason=reason or StockMovement.Reason.ADJUSTMENT,
                user=user,
                notes=notes,
                service_order=service_order,
                saldo_apos=self.current_stock,
            )

            # Se for composto, reduz os componentes recursivamente
            if self.format == self.Format.COM_COMPOSICAO:
                for comp in self.compositions.all():
                    comp_qty = comp.quantity * quantity
                    comp.component.reduce_stock(
                        comp_qty, 
                        user=user, 
                        reason=reason, 
                        notes=f"Componente de {self.name}: {notes}" if notes else f"Componente de {self.name}",
                        service_order=service_order
                    )

    def increase_stock(self, quantity, user=None, reason=None, notes=None, service_order=None):
        """
        Aumenta o estoque do produto. Geralmente não aumenta componentes automaticamente
        (pois a produção/entrada é do item final).
        """
        from django.db import transaction
        from .models import StockMovement
        
        with transaction.atomic():
            self.current_stock += quantity
            self.save()

            StockMovement.objects.create(
                product=self,
                quantity=quantity,
                movement_type=StockMovement.MovementType.ENTRADA,
                reason=reason or StockMovement.Reason.PURCHASE,
                user=user,
                notes=notes,
                service_order=service_order,
                saldo_apos=self.current_stock,
            )

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['name']


class ProductComposition(models.Model):
    parent = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='compositions', verbose_name="Produto Pai")
    component = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='used_in_compositions', verbose_name="Componente")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade")

    class Meta:
        verbose_name = "Composição de Produto"
        verbose_name_plural = "Composições de Produtos"
        unique_together = ('parent', 'component')

    def __str__(self):
        return f"{self.quantity} x {self.component.name} em {self.parent.name}"


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants', verbose_name="Produto")
    name = models.CharField(max_length=100, verbose_name="Nome da Variação (ex: Azul P, Vermelho GG)")
    code = models.CharField(max_length=60, blank=True, null=True, unique=True, verbose_name="Código")
    barcode = models.CharField(max_length=14, blank=True, null=True, verbose_name="EAN/Código de Barras")
    additional_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Diferença de Preço (R$)")
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Atual")
    min_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Mínimo")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    def reduce_stock(self, quantity, user=None, reason=None, notes=None):
        from django.db import transaction
        with transaction.atomic():
            self.current_stock -= quantity
            self.save()
            StockMovement.objects.create(
                product=self.product,
                quantity=quantity,
                movement_type=StockMovement.MovementType.SAIDA,
                reason=reason or StockMovement.Reason.VENDA_DIRETA,
                user=user,
                notes=notes,
            )

    def increase_stock(self, quantity, user=None, reason=None, notes=None):
        from django.db import transaction
        with transaction.atomic():
            self.current_stock += quantity
            self.save()
            StockMovement.objects.create(
                product=self.product,
                quantity=quantity,
                movement_type=StockMovement.MovementType.ENTRADA,
                reason=reason or StockMovement.Reason.DEVOLUCAO,
                user=user,
                notes=notes,
            )

    def __str__(self):
        return f"{self.product.name} — {self.name}"

    class Meta:
        verbose_name = "Variação de Produto"
        verbose_name_plural = "Variações de Produto"


class ImportHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Usuário")
    filename = models.CharField(max_length=255, verbose_name="Arquivo")
    file_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name="Hash do Arquivo (Prevenção Duplicidade)")
    created_count = models.PositiveIntegerField(default=0, verbose_name="Produtos Criados")
    updated_count = models.PositiveIntegerField(default=0, verbose_name="Produtos Atualizados")
    movements_count = models.PositiveIntegerField(default=0, verbose_name="Movimentações Geradas")
    errors = models.TextField(blank=True, verbose_name="Erros/Alertas")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora")

    class Meta:
        verbose_name = "Histórico de Importação"
        verbose_name_plural = "Histórico de Importações"
        ordering = ['-created_at']

    def __str__(self):
        user_name = self.user.username if self.user else "Sistema"
        return f"Importação {self.created_at.strftime('%d/%m/%Y %H:%M')} por {user_name}"


class ImportItem(models.Model):
    import_history = models.ForeignKey(ImportHistory, on_delete=models.CASCADE, related_name='items_logged', verbose_name="Importação")
    row_number = models.PositiveIntegerField(verbose_name="Linha")
    identifier = models.CharField(max_length=255, verbose_name="Identificador (Código/Nome)")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Produto")
    action = models.CharField(max_length=50, verbose_name="Ação")
    details = models.TextField(verbose_name="Detalhes da Alteração")
    is_error = models.BooleanField(default=False, verbose_name="É Erro?")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Item da Importação"
        verbose_name_plural = "Itens da Importação"
        ordering = ['row_number']


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        ENTRADA = 'ENTRADA', 'Entrada'
        SAIDA = 'SAIDA', 'Saída'

    class Reason(models.TextChoices):
        COMPRA = 'COMPRA', 'Compra'
        VENDA_OS = 'VENDA_OS', 'Venda OS'
        VENDA_DIRETA = 'VENDA_DIRETA', 'Venda Direta (PDV)'
        AJUSTE = 'AJUSTE', 'Ajuste de Estoque'
        PERDA = 'PERDA', 'Perda/Extravio'
        DEVOLUCAO = 'DEVOLUCAO', 'Devolução'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements', verbose_name="Produto")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade")
    movement_type = models.CharField(max_length=10, choices=MovementType.choices, verbose_name="Tipo de Movimento")
    reason = models.CharField(max_length=20, choices=Reason.choices, verbose_name="Motivo")
    service_order = models.ForeignKey('ServiceOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements', verbose_name="Ordem de Serviço")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Usuário")
    import_history = models.ForeignKey(ImportHistory, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements', verbose_name="Origem (Importação)")
    notes = models.TextField(blank=True, verbose_name="Observações")
    saldo_apos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Saldo Após")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora")

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product.name} ({self.quantity})"

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"
        ordering = ['-created_at']


class Billing(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PARCIAL = 'PARCIAL', 'Parcialmente Pago'
        PAGO = 'PAGO', 'Pago'
        CANCELADO = 'CANCELADO', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.PositiveIntegerField(unique=True, null=True, blank=True, verbose_name="Número da Cobrança")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='billings', verbose_name="Cliente")
    
    sale = models.OneToOneField('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='billing', verbose_name="Venda")
    service_order = models.ForeignKey('ServiceOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='billings', verbose_name="Ordem de Serviço")
    task = models.ForeignKey('ServiceOrderTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='billings', verbose_name="Etapa")
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Bruto")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, verbose_name="Status")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.number:
            from django.db.models import Max
            max_number = Billing.objects.aggregate(Max('number'))['number__max']
            self.number = (max_number or 5000) + 1
        super().save(*args, **kwargs)

    @property
    def public_page_path(self):
        return f"pagar/{self.public_token}/"

    @property
    def public_page_url(self):
        return f"{settings.SITE_URL.rstrip('/')}/pagar/{self.public_token}/"

    @property
    def origem(self):
        if self.task:
            if self.service_order:
                return f"OS #{self.service_order.number} — Etapa {self.task.get_task_type_display()}"
            return f"Etapa {self.task.get_task_type_display()}"
        if self.sale and hasattr(self.sale, 'number'):
            return f"Venda #{self.sale.number}"
        if self.service_order:
            return f"OS #{self.service_order.number}"
        return "Manual"

    def __str__(self):
        return f"Cobrança #{self.number} ({self.origem})"

    def get_total_paid(self):
        return sum(inst.get_total_paid() for inst in self.installments.all())

    def get_remaining_balance(self):
        return (self.total_amount - self.discount) - self.get_total_paid()

    class Meta:
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        ordering = ['-created_at']

class Installment(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PARCIAL = 'PARCIAL', 'Parcial'
        PAGO = 'PAGO', 'Pago'
        ATRASADO = 'ATRASADO', 'Atrasado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    billing = models.ForeignKey(Billing, on_delete=models.CASCADE, related_name='installments', verbose_name="Cobrança")
    installment_number = models.PositiveIntegerField(verbose_name="Nº Parcela")
    due_date = models.DateField(verbose_name="Data de Vencimento")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor")
    
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Forma de Pagto")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, verbose_name="Status")
    
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Pago em")
    notes = models.TextField(blank=True, null=True, verbose_name="Observações")

    def __str__(self):
        return f"{self.billing} - Parc {self.installment_number}"

    def get_total_paid(self):
        from django.db.models import Sum
        return self.actual_payments.aggregate(Sum('valor_bruto'))['valor_bruto__sum'] or Decimal('0.00')

    def get_remaining_balance(self):
        return self.amount - self.get_total_paid()

    @property
    def active_gateway_charge(self):
        return self.gateway_charges.filter(status='PENDING').order_by('-created_at').first()

    @property
    def gateway_pix_code(self):
        charge = self.active_gateway_charge
        if charge and charge.method == 'PIX':
            return charge.pix_copy_paste or ''
        return ''

    @property
    def gateway_payment_link(self):
        charge = self.active_gateway_charge
        return charge.invoice_url if charge else ''

    @property
    def gateway_boleto_barcode(self):
        charge = self.active_gateway_charge
        if charge and charge.method == 'BOLETO':
            return charge.boleto_barcode or ''
        return ''

    class Meta:
        verbose_name = "Parcela"
        verbose_name_plural = "Parcelas"
        ordering = ['billing', 'installment_number']

# --- MÓDULO DE VENDAS E PAGAMENTOS (PDV) ---

class ProviderType(models.TextChoices):
    DINHEIRO = 'DINHEIRO', 'Dinheiro'
    CARTAO_CREDITO = 'CARTAO_CREDITO', 'Cartão de Crédito'
    CARTAO_DEBITO = 'CARTAO_DEBITO', 'Cartão de Débito'
    PIX = 'PIX', 'Pix'
    BOLETO = 'BOLETO', 'Boleto'
    CREDIARIO = 'CREDIARIO', 'Crediário'

class PaymentMethod(models.Model):
    descricao = models.CharField(max_length=100, verbose_name="Descrição")
    tipo_provedor = models.CharField(max_length=20, choices=ProviderType.choices, verbose_name="Tipo de Provedor")
    tarifa_porcentagem = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Tarifa (%)")
    tarifa_minima = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Tarifa Mínima (R$)", help_text="Se a tarifa percentual resultar em valor menor que este, aplica este mínimo.")
    tarifa_fixa = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Tarifa Fixa (R$)")
    prazo_recebimento = models.IntegerField(default=0, verbose_name="Prazo de Recebimento (dias)")
    codigo_sefaz = models.CharField(max_length=2, verbose_name="Código SEFAZ")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Método de Pagamento"
        verbose_name_plural = "Métodos de Pagamento"

    def __str__(self):
        return self.descricao

class SalePayment(models.Model):
    venda = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='payments', null=True, blank=True, verbose_name="Venda")
    os = models.ForeignKey('ServiceOrder', on_delete=models.CASCADE, related_name='sale_payments', null=True, blank=True, verbose_name="Ordem de Serviço")
    installment = models.ForeignKey(Installment, on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_payments', verbose_name="Parcela")
    metodo_pagamento = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name="Método de Pagamento")
    valor_bruto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Bruto")
    valor_tarifa = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Tarifa")
    valor_liquido = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Líquido")
    data_pagamento = models.DateTimeField(default=timezone.now, verbose_name="Data do Pagamento")
    data_previsao = models.DateField(verbose_name="Previsão de Recebimento")

    class Meta:
        verbose_name = "Pagamento da Venda/OS"
        verbose_name_plural = "Pagamentos de Vendas/OS"

class Sale(models.Model):
    class Status(models.TextChoices):
        ATENDIDO = 'ATENDIDO', 'Atendido'
        CANCELADO = 'CANCELADO', 'Cancelado'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
        PRONTO = 'PRONTO', 'Pronto'
        RECEBIDO = 'RECEBIDO', 'Recebido'
        VENDA_AGENCIADA = 'VENDA_AGENCIADA', 'Venda Agenciada'
        RASCUNHO = 'RASCUNHO', 'Rascunho'
        FINALIZADA = 'FINALIZADA', 'Finalizada'

    class PaymentMethod(models.TextChoices):
        DINHEIRO = 'DINHEIRO', 'Dinheiro'
        PIX = 'PIX', 'Pix'
        CARTAO_DEBITO = 'CARTAO_DEBITO', 'Cartão de Débito'
        CARTAO_CREDITO = 'CARTAO_CREDITO', 'Cartão de Crédito'

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    number = models.PositiveIntegerField(unique=True, null=True, blank=True, verbose_name="Número da Venda")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cliente")
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Vendedor")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO, verbose_name="Status")
    
    # Dados Fiscais da Venda
    indicador_presenca = models.IntegerField(default=1, verbose_name="Indicador de Presença", choices=[
        (1, '1 - Operação presencial'),
        (2, '2 - Operação não presencial, pela Internet'),
        (3, '3 - Operação não presencial, Teleatendimento'),
        (4, '4 - NFC-e em operação com entrega a domicílio'),
        (9, '9 - Operação não presencial, outros'),
    ])
    modalidade_frete = models.IntegerField(default=9, verbose_name="Modalidade do Frete", choices=[
        (0, '0 - Contratação do Frete por conta do Remetente (CIF)'),
        (1, '1 - Contratação do Frete por conta do Destinatário (FOB)'),
        (2, '2 - Contratação do Frete por conta de Terceiros'),
        (3, '3 - Próprio por conta do Remetente'),
        (4, '4 - Próprio por conta do Destinatário'),
        (9, '9 - Sem Ocorrência de Transporte'),
    ])
    forma_pagamento_sefaz = models.CharField(max_length=2, default='01', verbose_name="Forma de Pagamento (SEFAZ)", choices=[
        ('01', '01 - Dinheiro'),
        ('02', '02 - Cheque'),
        ('03', '03 - Cartão de Crédito'),
        ('04', '04 - Cartão de Débito'),
        ('05', '05 - Crédito Loja'),
        ('10', '10 - Vale Alimentação'),
        ('11', '11 - Vale Refeição'),
        ('12', '12 - Vale Presente'),
        ('13', '13 - Vale Combustível'),
        ('15', '15 - Boleto Bancário'),
        ('17', '17 - PIX'),
        ('90', '90 - Sem pagamento'),
        ('99', '99 - Outros'),
    ])

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Total")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto")
    surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Acréscimo")
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, null=True, blank=True, verbose_name="Forma de Pagamento")
    service_order = models.ForeignKey('ServiceOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', verbose_name="OS Vinculada")

    # Controle de Fluxo
    stock_reduced = models.BooleanField(default=False, verbose_name="Estoque Baixado")

    # Campos Comerciais
    external_po_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="N° Pedido do Cliente (PO)")
    delivery_date = models.DateField(null=True, blank=True, verbose_name="Prazo de Entrega")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Comissão do Vendedor (%)")
    notes_internal = models.TextField(blank=True, null=True, verbose_name="Observações Internas")
    notes_customer = models.TextField(blank=True, null=True, verbose_name="Observações para o Cliente")

    # Endereço de Entrega
    delivery_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Destinatário")
    delivery_cep = models.CharField(max_length=9, blank=True, null=True, verbose_name="CEP Entrega")
    delivery_address = models.CharField(max_length=255, blank=True, null=True, verbose_name="Logradouro Entrega")
    delivery_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Número Entrega")
    delivery_complement = models.CharField(max_length=255, blank=True, null=True, verbose_name="Complemento Entrega")
    delivery_neighborhood = models.CharField(max_length=100, blank=True, null=True, verbose_name="Bairro Entrega")
    delivery_city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Cidade Entrega")
    delivery_state = models.CharField(max_length=2, blank=True, null=True, verbose_name="UF Entrega")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Venda"
        verbose_name_plural = "Vendas"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.number:
            from django.db.models import Max
            max_number = Sale.objects.aggregate(Max('number'))['number__max']
            self.number = (max_number or 1000) + 1

        # Garantir decimais
        self.discount = self.discount or Decimal('0.00')
        self.surcharge = self.surcharge or Decimal('0.00')
        self.total_amount = self.total_amount or Decimal('0.00')

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Venda #{self.number} - {self.get_status_display()}"

    def can_be_edited(self):
        """
        Retorna True se a venda puder ser editada.
        Bloqueia se a venda estiver FINALIZADA ou se houver uma cobrança vinculada
        com parcelas geradas (Contas a Receber).
        """
        if self.status == self.Status.FINALIZADA:
            return False

        if not hasattr(self, 'billing'):
            return True

        # Bloqueia se houver qualquer parcela não cancelada (mesmo que apenas PENDENTE)
        return not self.billing.installments.exclude(
            status=Installment.Status.CANCELADO
        ).exists()


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Produto")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Subtotal (Líquido)")
    variant = models.ForeignKey('ProductVariant', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Variação")
    cost_price_ato = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Preço de Custo no ato")

    # Dados Fiscais "Congelados" no ato da venda
    ncm_ato = models.CharField(max_length=8, blank=True, null=True, verbose_name="NCM no ato")
    cest_ato = models.CharField(max_length=7, blank=True, null=True, verbose_name="CEST no ato")
    origem_ato = models.IntegerField(blank=True, null=True, verbose_name="Origem no ato")
    cfop_aplicado = models.CharField(max_length=4, blank=True, null=True, verbose_name="CFOP Aplicado")
    vlr_tributos_ibpt = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Tributos IBPT")

    class Meta:
        verbose_name = "Item de Venda"
        verbose_name_plural = "Itens de Venda"

    def save(self, *args, **kwargs):
        self.discount = self.discount or Decimal('0.00')
        self.subtotal = (self.quantity * self.unit_price) - self.discount
        
        # Lógica Fiscal (Inteligência Fiscal)
        if self.product:
            # Detecta se é criação ou mudança de produto
            is_new = self._state.adding
            product_changed = False
            if not is_new:
                old_instance = SaleItem.objects.filter(pk=self.pk).first()
                if old_instance and old_instance.product_id != self.product_id:
                    product_changed = True
            
            if is_new or product_changed or not self.ncm_ato:
                # Congela dados do produto
                self.ncm_ato = self.product.ncm
                self.cest_ato = self.product.cest
                self.origem_ato = self.product.origem_mercadoria
                
                # CFOP
                config = SystemConfig.load()
                origem_uf = config.state
                
                # Tenta determinar o destino_uf
                destino_uf = origem_uf
                if self.sale.service_order:
                    destino_uf = self.sale.service_order.client_property.state
                elif self.sale.client:
                    # Tenta pegar a UF do cliente (via primeira propriedade cadastrada)
                    # No futuro, o Client/BusinessEntityBase pode ter um estado principal
                    prop = self.sale.client.properties.first()
                    if prop:
                        destino_uf = prop.state
                
                tem_st = bool(self.product.cest)
                self.cfop_aplicado = fiscal_logic.get_cfop(origem_uf, destino_uf, tem_st)
                self.cost_price_ato = self.product.preco_custo

            # Cálculo de Impostos IBPT (sempre atualiza baseado no subtotal atual)
            self.vlr_tributos_ibpt = fiscal_logic.calculate_ibpt(
                self.subtotal,
                self.product.aliquota_ibpt_fed,
                self.product.aliquota_ibpt_est,
                self.product.aliquota_ibpt_mun
            )

        super().save(*args, **kwargs)


class SaleReturn(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        APROVADA = 'APROVADA', 'Aprovada'
        CANCELADA = 'CANCELADA', 'Cancelada'

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='returns', verbose_name="Venda")
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Registrado por")
    reason = models.TextField(verbose_name="Motivo da Devolução")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, verbose_name="Status")
    total_refund = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Total Devolvido")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Devolução #{self.pk} — Venda #{self.sale.number}"

    class Meta:
        verbose_name = "Devolução de Venda"
        verbose_name_plural = "Devoluções de Venda"
        ordering = ['-created_at']


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items', verbose_name="Devolução")
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, verbose_name="Item da Venda")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade Devolvida")
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Restituído")
    restock = models.BooleanField(default=True, verbose_name="Retornar ao Estoque")

    class Meta:
        verbose_name = "Item da Devolução"
        verbose_name_plural = "Itens da Devolução"


# --- ORDENS DE SERVIÇO ---


class ServiceOrder(models.Model):
    class ServiceType(models.TextChoices):
        INSTALACAO = 'INSTALACAO', 'Instalação'
        MANUTENCAO_CORRETIVA = 'MANUTENCAO_CORRETIVA', 'Manutenção Corretiva'
        MANUTENCAO_PREVENTIVA = 'MANUTENCAO_PREVENTIVA', 'Manutenção Preventiva'

    class Status(models.TextChoices):
        AGUARDANDO_VISITA = 'AGUARDANDO_VISITA', 'Aguardando visita inicial'
        ORCAMENTO_AGENDADO = 'ORCAMENTO_AGENDADO', 'Orçamento Agendado'
        ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO = 'ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO', 'Orçamento realizado, aguardando envio'
        AGUARDANDO_APROVACAO = 'AGUARDANDO_APROVACAO', 'Orçamento enviado - aguardando aprovação'
        APROVADO_AGUARDANDO_AGENDAMENTO = 'APROVADO_AGUARDANDO_AGENDAMENTO', 'Aprovado pelo cliente - Aguardando Agendamento de execução'
        REPROVADO_PELO_CLIENTE = 'REPROVADO_PELO_CLIENTE', 'Reprovado pelo cliente'
        AGUARDANDO_EXECUCAO = 'AGUARDANDO_EXECUCAO', 'Aguardando Execução'
        AGUARDANDO_PAGAMENTO = 'AGUARDANDO_PAGAMENTO', 'Aguardando Pagamento'
        PAGAMENTO_PARCIAL = 'PAGAMENTO_PARCIAL', 'Pagamento Parcial'
        FINALIZADO = 'FINALIZADO', 'Finalizado'
        CONCLUIDA = 'CONCLUIDA', 'Concluída'
        CANCELADO = 'CANCELADO', 'Cancelado'
        GARANTIA = 'GARANTIA', 'Em Garantia'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True, null=True, blank=True, verbose_name="Número da OS")
    client_property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='service_orders', verbose_name="Imóvel")
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.AGUARDANDO_VISITA, verbose_name="Status")
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
    
    # Controle de Cobrança e Recibo
    pix_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Cobrança/PIX enviada em")
    chatwoot_payment_receipt_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Recibo/Avaliação enviada em")
    
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
    
    service_type = models.CharField(
        max_length=30,
        choices=ServiceType.choices,
        null=True,
        blank=True,
        verbose_name="Tipo de OS",
    )
    stock_lowered = models.BooleanField(default=False, verbose_name="Estoque Baixado")

    public_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Token da Página Pública",
    )

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
    def public_page_path(self):
        return f"os/{self.public_token}/"

    @property
    def public_page_url(self):
        from django.conf import settings
        return f"{settings.SITE_URL.rstrip('/')}/os/{self.public_token}/"

    @property
    def total_value(self):
        # Itens de ORCAMENTO são referência histórica — nunca cobrados diretamente.
        # Quando existem tarefas de EXECUCAO, GARANTIA ou RETORNO, apenas os itens dessas
        # entram no total (evita soma dupla após clonagem de itens do orçamento).
        exec_garantia_types = [
            ServiceOrderTask.TaskType.EXECUCAO,
            ServiceOrderTask.TaskType.GARANTIA,
            ServiceOrderTask.TaskType.RETORNO,
        ]
        has_exec_or_garantia = self.tasks.filter(task_type__in=exec_garantia_types).exists()
        if has_exec_or_garantia:
            billable = self.items.filter(task__task_type__in=exec_garantia_types)
        else:
            billable = self.items.all()
        items_total = sum((item.total_price for item in billable), Decimal('0'))
        return quantize_money(items_total)

    @property
    def total_value_net(self):
        """Valor total após descontos por etapa (ou desconto legado da OS)."""
        exec_garantia_types = [
            ServiceOrderTask.TaskType.EXECUCAO,
            ServiceOrderTask.TaskType.GARANTIA,
            ServiceOrderTask.TaskType.RETORNO,
        ]
        billable_tasks = list(self.tasks.filter(task_type__in=exec_garantia_types))
        if billable_tasks:
            return quantize_money(sum((t.billing_value_net for t in billable_tasks), Decimal('0')))
        return quantize_money(self.total_value - (self.discount or Decimal('0')))

    @property
    def total_paid(self):
        """Soma apenas pagamentos confirmados"""
        paid_total = sum((payment.amount for payment in self.payments.filter(status='CONFIRMADO')), Decimal('0'))
        return quantize_money(paid_total)

    @property
    def total_collected_pending(self):
        """Soma pagamentos recebidos por técnicos mas ainda não baixados pelo financeiro"""
        pending_total = sum((payment.amount for payment in self.payments.filter(status='PENDENTE')), Decimal('0'))
        return quantize_money(pending_total)

    @property
    def balance_due(self):
        return quantize_money(self.total_value - self.total_paid - quantize_money(self.discount))

    def update_status(self):
        """Lógica centralizada de atualização de status da OS — apenas estado operacional do trabalho."""
        import django.utils.timezone
        from django.db import transaction

        self.estimated_value = self.total_value - self.discount

        tasks = self.tasks.all()

        # 1. Prioridade: Garantia
        if tasks.filter(task_type=ServiceOrderTask.TaskType.GARANTIA).exists():
            if tasks.filter(task_type=ServiceOrderTask.TaskType.GARANTIA, status=ServiceOrderTask.TaskStatus.CONCLUIDO).exists():
                self.status = self.Status.CONCLUIDA
            else:
                self.status = self.Status.GARANTIA

        # 2. Lógica baseada em Tasks (operacional, sem pagamentos)
        else:
            budget_tasks = tasks.filter(task_type=ServiceOrderTask.TaskType.ORCAMENTO)
            exec_tasks = tasks.filter(task_type=ServiceOrderTask.TaskType.EXECUCAO)

            # Todas as execuções concluídas → OS concluída
            if exec_tasks.exists() and not exec_tasks.exclude(status=ServiceOrderTask.TaskStatus.CONCLUIDO).exists():
                self.status = self.Status.CONCLUIDA
                if not self.finished_at:
                    self.finished_at = django.utils.timezone.now()

            # Tem execução agendada ou em andamento
            elif exec_tasks.filter(status__in=[ServiceOrderTask.TaskStatus.AGENDADO, ServiceOrderTask.TaskStatus.EM_ANDAMENTO]).exists():
                self.status = self.Status.AGUARDANDO_EXECUCAO

            # Tem execução aprovada mas não agendada
            elif exec_tasks.filter(is_approved=True).exists():
                self.status = self.Status.APROVADO_AGUARDANDO_AGENDAMENTO

            # Orçamento concluído aguardando envio
            elif budget_tasks.filter(status=ServiceOrderTask.TaskStatus.CONCLUIDO).exists():
                self.status = self.Status.ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO

            # Orçamento agendado
            elif budget_tasks.filter(status=ServiceOrderTask.TaskStatus.AGENDADO).exists():
                self.status = self.Status.ORCAMENTO_AGENDADO

        # 3. GESTÃO DE ESTOQUE
        # Usa o mesmo critério de total_value: apenas itens de EXECUCAO/GARANTIA/RETORNO
        # quando essas tarefas existem, evitando baixa dupla dos itens clonados do orçamento.
        exec_garantia_types = [
            ServiceOrderTask.TaskType.EXECUCAO,
            ServiceOrderTask.TaskType.GARANTIA,
            ServiceOrderTask.TaskType.RETORNO,
        ]
        has_exec_or_garantia = self.tasks.filter(task_type__in=exec_garantia_types).exists()
        if has_exec_or_garantia:
            stock_items_qs = self.items.filter(product__isnull=False, task__task_type__in=exec_garantia_types)
        else:
            stock_items_qs = self.items.filter(product__isnull=False)

        with transaction.atomic():
            if not self.stock_lowered and self.status == self.Status.CONCLUIDA:
                for item in stock_items_qs:
                    item.product.reduce_stock(
                        item.quantity,
                        reason=StockMovement.Reason.VENDA_OS,
                        service_order=self,
                        notes="Baixa automática na conclusão da OS"
                    )
                self.stock_lowered = True

            elif self.stock_lowered and self.status == self.Status.CANCELADO:
                for item in stock_items_qs:
                    item.product.increase_stock(
                        item.quantity,
                        reason=StockMovement.Reason.DEVOLUCAO,
                        service_order=self,
                        notes="Estorno automático por cancelamento da OS"
                    )
                self.stock_lowered = False

            self.save()


    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"


class ServiceOrderTask(models.Model):
    class TaskType(models.TextChoices):
        ORCAMENTO = 'ORCAMENTO', 'Vistoria/Orçamento'
        EXECUCAO = 'EXECUCAO', 'Execução/Instalação'
        GARANTIA = 'GARANTIA', 'Garantia'
        RETORNO = 'RETORNO', 'Retorno'

    class TaskStatus(models.TextChoices):
        AGENDADO = 'AGENDADO', 'Agendado'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        PARCIALMENTE_EXECUTADO = 'PARCIALMENTE_EXECUTADO', 'Parcialmente Executado'
        CANCELADO = 'CANCELADO', 'Cancelado'
        NAO_EXECUTADO = 'NAO_EXECUTADO', 'Não Executado'

    PAYMENT_METHODS = [
        ('PIX', 'PIX'),
        ('CARTAO_CREDITO', 'Cartão de Crédito'),
        ('CARTAO_DEBITO', 'Cartão de Débito'),
        ('DINHEIRO', 'Dinheiro'),
        ('TRANSFERENCIA', 'Transferência Bancária'),
        ('BOLETO', 'Boleto'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='tasks', verbose_name="Ordem de Serviço")
    parent_task = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='continuations', verbose_name="Etapa de Origem"
    )
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.EXECUCAO, verbose_name="Tipo de Etapa")
    status = models.CharField(max_length=30, choices=TaskStatus.choices, default=TaskStatus.AGENDADO, verbose_name="Status")
    
    # Valor e Aprovação
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Valor da Etapa (R$)")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto (R$)")
    requires_client_approval = models.BooleanField(default=False, verbose_name="Requer Aprovação do Cliente?")
    is_approved = models.BooleanField(default=False, verbose_name="Aprovado pelo Cliente?")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True, verbose_name="Método de Pagamento Preferencial")

    # Datas e Horários
    scheduled_at = models.DateTimeField(verbose_name="Agendado para")
    scheduled_end_at = models.DateTimeField(null=True, blank=True, verbose_name="Data Fim de Agendamento")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Iniciado em")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado em")
    
    
    notes = models.TextField(verbose_name="Observações Técnicas desta Etapa", blank=True)
    
    # Confirmação de Agendamento via WhatsApp
    class WhatsAppConfirmationStatus(models.TextChoices):
        ENVIADO = 'ENVIADO', 'Enviado'
        AGUARDANDO = 'AGUARDANDO', 'Aguardando Confirmação'
        CONFIRMADO = 'CONFIRMADO', 'Confirmado'
        REAGENDAR = 'REAGENDAR', 'Reagendar'

    send_whatsapp_confirmation = models.BooleanField(default=False, verbose_name="Enviar WhatsApp de Confirmação?")
    whatsapp_confirmation_status = models.CharField(
        max_length=20, 
        choices=WhatsAppConfirmationStatus.choices, 
        null=True, 
        blank=True, 
        verbose_name="Status da Confirmação WhatsApp"
    )
    whatsapp_notification_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Notificação enviada em")
    whatsapp_confirmation_received_at = models.DateTimeField(null=True, blank=True, verbose_name="Resposta recebida em")
    whatsapp_response_content = models.TextField(null=True, blank=True, verbose_name="Conteúdo da Resposta WhatsApp")
    chatwoot_confirmation_conversation_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Chatwoot Conversation ID (Confirmação)"
    )
    chatwoot_confirmation_message_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Chatwoot Message ID (Confirmação)"
    )
    chatwoot_confirmation_contact_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Chatwoot Contact ID (Confirmação)"
    )
    confirmation_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name="Token de Confirmação Pública"
    )

    # Preferência de pagamento registrada pelo cliente na página pública
    preferred_payment_method = models.ForeignKey(
        'PaymentMethod',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preferred_tasks',
        verbose_name="Método de Pagamento Preferido (cliente)"
    )
    preferred_installments = models.PositiveIntegerField(
        default=1,
        null=True,
        blank=True,
        verbose_name="Parcelas Preferidas (cliente)"
    )

    @property
    def confirmation_url(self):
        from django.conf import settings
        return f"{settings.SITE_URL.rstrip('/')}/confirmar/{self.confirmation_token}/"

    # Assinatura Digital do Cliente (Salva apenas o caminho do arquivo)
    customer_signature = models.CharField(max_length=255, null=True, blank=True, verbose_name="Caminho da Assinatura")
    customer_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nome de quem assinou")
    
    @property
    def get_signature_url(self):
        if self.customer_signature:
            from django.core.files.storage import default_storage
            try:
                # Se já for uma URL completa (ex: de um cache ou base64 antigo), retorna direto
                if self.customer_signature.startswith('http') or self.customer_signature.startswith('data:'):
                    return self.customer_signature
                return default_storage.url(self.customer_signature)
            except Exception:
                return None
        return None

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        numero_visual = self.service_order.number if self.service_order.number else "S/N"
        return f"{self.get_task_type_display()} - OS #{numero_visual}"

    @property
    def billing_value(self):
        """Valor bruto: soma dos itens da etapa onde cobrar_cliente=True."""
        result = self.items.filter(cobrar_cliente=True).aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total']
        return quantize_money(result or Decimal('0'))

    @property
    def billing_value_net(self):
        """Valor a cobrar após desconto da etapa."""
        return quantize_money(max(self.billing_value - (self.discount or Decimal('0')), Decimal('0')))

    @property
    def team_display(self):
        """Retorna a equipe alocada formatada: 'Nome (Função), Nome (Função)'."""
        members = self.team_members.select_related('professional', 'role').all()
        if not members.exists():
            return ""
        parts = []
        for m in members:
            role_name = m.role.name if m.role else "Sem função"
            parts.append(f"{m.professional.name} ({role_name})")
        return ", ".join(parts)

    def save(self, *args, **kwargs):
        if not self.pk and self.service_order.status == ServiceOrder.Status.CONCLUIDA:
            self.requires_client_approval = True
        super().save(*args, **kwargs)
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
    cobrar_cliente = models.BooleanField(default=True, verbose_name="Cobrar do cliente")

    # Dados Fiscais "Congelados" no ato da venda/OS
    ncm_ato = models.CharField(max_length=8, blank=True, null=True, verbose_name="NCM no ato")
    cest_ato = models.CharField(max_length=7, blank=True, null=True, verbose_name="CEST no ato")
    origem_ato = models.IntegerField(blank=True, null=True, verbose_name="Origem no ato")
    cfop_aplicado = models.CharField(max_length=4, blank=True, null=True, verbose_name="CFOP Aplicado")
    vlr_tributos_ibpt = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Tributos IBPT")

    @property
    def total_price(self):
        return quantize_money(self.quantity * self.unit_price)
    
    def __str__(self):
        task_info = f" (Etapa: {self.task.get_task_type_display()})" if self.task else " (Orçamento Geral)"
        return f"{self.description} - Qtd: {self.quantity}{task_info}"

    def save(self, *args, **kwargs):
        # Lógica Fiscal (Inteligência Fiscal)
        if self.product:
            # Detecta se é criação ou mudança de produto
            is_new = self._state.adding
            product_changed = False
            if not is_new:
                old_instance = ServiceItem.objects.filter(pk=self.pk).first()
                if old_instance and old_instance.product_id != self.product_id:
                    product_changed = True
            
            if is_new or product_changed or not self.ncm_ato:
                # Congela dados do produto
                self.ncm_ato = self.product.ncm
                self.cest_ato = self.product.cest
                self.origem_ato = self.product.origem_mercadoria
                
                # CFOP
                config = SystemConfig.load()
                origem_uf = config.state
                destino_uf = self.service_order.client_property.state
                
                tem_st = bool(self.product.cest)
                self.cfop_aplicado = fiscal_logic.get_cfop(origem_uf, destino_uf, tem_st)

            # Cálculo de Impostos IBPT
            self.vlr_tributos_ibpt = fiscal_logic.calculate_ibpt(
                self.quantity * self.unit_price,
                self.product.aliquota_ibpt_fed,
                self.product.aliquota_ibpt_est,
                self.product.aliquota_ibpt_mun
            )

        super().save(*args, **kwargs)
        self.service_order.update_status()

    def delete(self, *args, **kwargs):
        order = self.service_order
        super().delete(*args, **kwargs)
        order.update_status()

    class Meta:
        verbose_name = "Item de Serviço"


class ServicePayment(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente de Baixa'
        CONFIRMADO = 'CONFIRMADO', 'Baixa Realizada'

    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='payments', verbose_name="Ordem de Serviço")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Pago")
    payment_method = models.CharField(max_length=20, choices=ServiceOrderTask.PAYMENT_METHODS, verbose_name="Método de Pagamento")
    paid_at = models.DateTimeField(verbose_name="Data do Pagamento")
    notes = models.CharField(max_length=255, blank=True, verbose_name="Observações")
    
    # Controle de Recebimento por Técnicos
    received_by = models.ForeignKey(Professional, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_payments', verbose_name="Recebido por")
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.CONFIRMADO, verbose_name="Status")
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="Confirmado em")
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_payments', verbose_name="Confirmado por")

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
        IMPEDITIVA = 'IMPEDITIVA', 'Impeditiva'
        SOLICITACAO_MATERIAL = 'SOLICITACAO_MATERIAL', 'Solicitação de Material'
        GERAL = 'GERAL', 'Ocorrência'

    class OccurrenceType(models.TextChoices):
        ATRASO = 'ATRASO', 'Atraso'
        FALTA_MATERIAL = 'FALTA_MATERIAL', 'Falta de Material'
        CLIENTE_AUSENTE = 'CLIENTE_AUSENTE', 'Cliente Ausente'
        IMPEDIMENTO_LOCAL = 'IMPEDIMENTO_LOCAL', 'Impedimento no Local'
        ACIONAMENTO_GARANTIA = 'ACIONAMENTO_GARANTIA', 'Acionamento de Garantia'
        OUTRO = 'OUTRO', 'Outro'

    class OccurrenceStatus(models.TextChoices):
        REGISTRADA = 'REGISTRADA', 'Registrada'
        RESOLVIDA = 'RESOLVIDA', 'Resolvida'

    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='occurrences', verbose_name="Etapa/Tarefa")
    category = models.CharField(max_length=20, choices=OccurrenceCategory.choices, default=OccurrenceCategory.GERAL, verbose_name="Categoria")
    occurrence_type = models.CharField(max_length=20, choices=OccurrenceType.choices, default=OccurrenceType.OUTRO, verbose_name="Tipo de Ocorrência")
    description = models.TextField(verbose_name="Descrição")
    status = models.CharField(max_length=20, choices=OccurrenceStatus.choices, default=OccurrenceStatus.REGISTRADA, verbose_name="Status")
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


class MediaProcessingJob(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PROCESSANDO = 'PROCESSANDO', 'Processando'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        ERRO = 'ERRO', 'Erro'

    task = models.ForeignKey(ServiceOrderTask, on_delete=models.CASCADE, related_name='media_jobs', verbose_name="Etapa/Tarefa")
    response = models.ForeignKey(
        TaskChecklistResponse,
        on_delete=models.SET_NULL,
        related_name='media_jobs',
        verbose_name="Resposta do Check-list",
        null=True,
        blank=True,
    )
    occurrence = models.ForeignKey(
        Occurrence,
        on_delete=models.SET_NULL,
        related_name='media_jobs',
        verbose_name="Ocorrência",
        null=True,
        blank=True,
    )
    raw_path = models.CharField(max_length=500, verbose_name="Arquivo bruto (local)")
    original_name = models.CharField(max_length=255, blank=True, verbose_name="Nome original")
    content_type = models.CharField(max_length=120, blank=True, verbose_name="Content-Type")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, verbose_name="Status")
    error_message = models.TextField(blank=True, verbose_name="Mensagem de erro")
    result_media_type = models.CharField(max_length=20, blank=True, verbose_name="Tipo de mídia gerada")
    result_media_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="ID da mídia gerada")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Job de Processamento de Mídia"
        verbose_name_plural = "Jobs de Processamento de Mídia"
        ordering = ['created_at']


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


class PushNotificationJob(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PROCESSANDO = 'PROCESSANDO', 'Processando'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        ERRO = 'ERRO', 'Erro'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_jobs', verbose_name="Usuário")
    title = models.CharField(max_length=255, verbose_name="Título")
    body = models.TextField(verbose_name="Corpo")
    url = models.CharField(max_length=500, default='/', verbose_name="URL de destino")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, verbose_name="Status")
    error_message = models.TextField(blank=True, verbose_name="Mensagem de erro")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Job de Notificação Push"
        verbose_name_plural = "Jobs de Notificação Push"
        ordering = ['created_at']

    def __str__(self):
        return f"PushJob [{self.status}] → {self.user.username}: {self.title}"


# --- CONTAS A PAGAR ---

class FinancialCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome")
    category_type = models.CharField(
        max_length=10, 
        choices=[('ENTRADA', 'Entrada'), ('SAIDA', 'Saída')], 
        default='SAIDA', 
        verbose_name="Tipo"
    )

    class Meta:
        verbose_name = "Categoria Financeira"
        verbose_name_plural = "Categorias Financeiras"

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    class AccountType(models.TextChoices):
        CORRENTE = 'CORRENTE', 'Conta Corrente'
        POUPANCA = 'POUPANCA', 'Conta Poupança'
        CAIXA = 'CAIXA', 'Caixa'
        INVESTIMENTO = 'INVESTIMENTO', 'Investimento'

    name = models.CharField(max_length=100, verbose_name="Nome")
    bank = models.CharField(max_length=100, blank=True, verbose_name="Banco")
    account_type = models.CharField(
        max_length=20, choices=AccountType.choices,
        default=AccountType.CORRENTE, verbose_name="Tipo"
    )
    initial_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo Inicial")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")

    class Meta:
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"
        ordering = ['name']

    def __str__(self):
        if self.bank:
            return f"{self.name} — {self.bank}"
        return self.name

    @property
    def current_balance(self):
        from django.db.models import Sum
        from decimal import Decimal
        paid_out = InstallmentPayment.objects.filter(
            bank_account=self,
            is_discount=False,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return self.initial_balance - paid_out


class FinanceSettings(models.Model):
    days_before_generation = models.PositiveIntegerField(
        default=7,
        verbose_name="Dias de antecedência para geração",
        help_text="Quantos dias antes do vencimento o sistema deve gerar o registro de contas a pagar"
    )
    enable_commission = models.BooleanField(
        default=False,
        verbose_name="Habilitar módulo de comissão",
        help_text="Quando ativo, exibe o relatório de comissões por etapa no painel financeiro."
    )
    auto_billing_on_task_completion = models.BooleanField(
        default=True,
        verbose_name="Gerar cobrança automaticamente ao concluir etapa",
        help_text="Quando ativo, uma cobrança é criada automaticamente ao concluir etapas de Execução, Garantia ou Retorno com valor > 0."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configurações Financeiras"
        verbose_name_plural = "Configurações Financeiras"

    def __str__(self):
        return f"Configurações Financeiras (geração com {self.days_before_generation} dias de antecedência)"


class SaleSettings(models.Model):
    class BillingTrigger(models.TextChoices):
        MANUAL = 'MANUAL', 'Somente Manual (não gerar automaticamente)'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
        PRONTO = 'PRONTO', 'Pronto'
        ATENDIDO = 'ATENDIDO', 'Atendido'
        RECEBIDO = 'RECEBIDO', 'Recebido'
        VENDA_AGENCIADA = 'VENDA_AGENCIADA', 'Venda Agenciada'
        FINALIZADA = 'FINALIZADA', 'Finalizada'

    billing_trigger_status = models.CharField(
        max_length=20,
        choices=BillingTrigger.choices,
        default=BillingTrigger.FINALIZADA,
        verbose_name="Gerar cobrança automática quando a venda atingir o status",
    )

    class Meta:
        verbose_name = "Configurações de Vendas"
        verbose_name_plural = "Configurações de Vendas"

    def __str__(self):
        return f"Configurações de Vendas"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RecurrenceRule(models.Model):
    class Frequency(models.TextChoices):
        DIARIA = 'DIARIA', 'Diária'
        SEMANAL = 'SEMANAL', 'Semanal'
        QUINZENAL = 'QUINZENAL', 'Quinzenal'
        MENSAL = 'MENSAL', 'Mensal'
        ANUAL = 'ANUAL', 'Anual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, verbose_name="Fornecedor")
    category = models.ForeignKey(FinancialCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoria")
    description = models.CharField(max_length=255, verbose_name="Descrição")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor")
    frequency = models.CharField(max_length=20, choices=Frequency.choices, verbose_name="Frequência")
    start_date = models.DateField(verbose_name="Data de Início")
    end_date = models.DateField(null=True, blank=True, verbose_name="Data de Fim")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Criado por")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Regra de Recorrência"
        verbose_name_plural = "Regras de Recorrência"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.description} ({self.get_frequency_display()}) — {self.supplier.display_name}"

    def get_due_dates_in_range(self, start, end):
        """Calcula as datas de vencimento dentro do intervalo sem persistir nada."""
        from dateutil.relativedelta import relativedelta
        delta_map = {
            'DIARIA':    relativedelta(days=1),
            'SEMANAL':   relativedelta(weeks=1),
            'QUINZENAL': relativedelta(weeks=2),
            'MENSAL':    relativedelta(months=1),
            'ANUAL':     relativedelta(years=1),
        }
        delta = delta_map.get(self.frequency)
        if not delta:
            return []

        dates = []
        current = self.start_date
        rule_end = self.end_date or end

        while current <= min(end, rule_end):
            if current >= start:
                dates.append(current)
            current += delta

        return dates

    @property
    def next_due_date(self):
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta
        today = timezone.localdate()
        dates = self.get_due_dates_in_range(today, today + relativedelta(years=2))
        return dates[0] if dates else None


class Expense(models.Model):
    class Frequency(models.TextChoices):
        DIARIA = 'DIARIA', 'Diária'
        SEMANAL = 'SEMANAL', 'Semanal'
        QUINZENAL = 'QUINZENAL', 'Quinzenal'
        MENSAL = 'MENSAL', 'Mensal'
        ANUAL = 'ANUAL', 'Anual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, verbose_name="Fornecedor")
    category = models.ForeignKey(FinancialCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoria")
    description = models.CharField(max_length=255, verbose_name="Descrição")
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor Total")
    issue_date = models.DateField(default=timezone.now, verbose_name="Data de Emissão")
    
    is_recurrent = models.BooleanField(default=False, verbose_name="Recorrência")
    frequency = models.CharField(max_length=20, choices=Frequency.choices, null=True, blank=True, verbose_name="Frequência")
    installments_count = models.PositiveIntegerField(default=1, verbose_name="Número de Parcelas")
    recurrence_rule = models.ForeignKey(
        'RecurrenceRule', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expense_templates', verbose_name="Regra de Recorrência"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"

    def __str__(self):
        return f"{self.description} - {self.supplier.display_name}"


class ExpenseInstallment(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PARCIAL = 'PARCIAL', 'Parcial'
        PAGO = 'PAGO', 'Pago'
        ATRASADO = 'ATRASADO', 'Atrasado'

    class PaymentMethod(models.TextChoices):
        PIX = 'PIX', 'Pix'
        BOLETO = 'BOLETO', 'Boleto'
        CARTAO_CREDITO = 'CARTAO_CREDITO', 'Cartão de Crédito'
        DINHEIRO = 'DINHEIRO', 'Dinheiro'
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferência/TED'

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='installments', verbose_name="Despesa")
    installment_number = models.CharField(max_length=20, verbose_name="Número da Parcela")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor da Parcela")
    due_date = models.DateField(db_index=True, verbose_name="Data de Vencimento")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, db_index=True, verbose_name="Status")

    recurrence_rule = models.ForeignKey(
        RecurrenceRule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_installments', verbose_name="Regra de Recorrência"
    )
    recurrence_due_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Data de Ocorrência da Recorrência")

    payment_date = models.DateField(null=True, blank=True, verbose_name="Data de Pagamento")
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, null=True, blank=True, verbose_name="Meio de Pagamento")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Conta Bancária de Saída")
    document_ref = models.CharField(
        max_length=100, blank=True,
        verbose_name="Nº Documento (NF/Boleto/PIX)"
    )

    class Meta:
        verbose_name = "Parcela de Despesa"
        verbose_name_plural = "Parcelas de Despesa"
        ordering = ['due_date']

    def __str__(self):
        return f"{self.expense.description} - Parcela {self.installment_number}"

    @property
    def installment_label(self):
        """Returns '1 de 3' for regular installments or '1 de 20' for bounded recurrences."""
        from dateutil.relativedelta import relativedelta as rdelta
        num = self.installment_number
        if num and '/' in num:
            parts = num.split('/')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"{parts[0]} de {parts[1]}"
        if self.recurrence_rule_id and self.recurrence_due_date:
            rule = self.recurrence_rule
            end = rule.end_date or (rule.start_date + rdelta(years=5))
            all_dates = rule.get_due_dates_in_range(rule.start_date, end)
            try:
                pos = all_dates.index(self.recurrence_due_date) + 1
                total = len(all_dates)
                return f"{pos} de {total}" if rule.end_date else f"#{pos}"
            except ValueError:
                pass
        return num or '—'

    @property
    def amount_paid(self):
        from decimal import Decimal
        from django.db.models import Sum
        return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    @property
    def amount_remaining(self):
        from decimal import Decimal
        remaining = self.amount - self.amount_paid
        return remaining if remaining > Decimal('0') else Decimal('0')

    def recalculate_status(self):
        from decimal import Decimal
        paid = self.amount_paid
        if paid >= self.amount:
            self.status = self.Status.PAGO
        elif paid > Decimal('0'):
            self.status = self.Status.PARCIAL
        elif self.due_date < timezone.localdate():
            self.status = self.Status.ATRASADO
        else:
            self.status = self.Status.PENDENTE
        self.save(update_fields=['status'])


class ExpenseAttachment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='attachments', verbose_name="Despesa")
    file = models.FileField(upload_to='expenses/%Y/%m/%d/', verbose_name="Arquivo")
    description = models.CharField(max_length=255, blank=True, verbose_name="Descrição")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anexo de Despesa"
        verbose_name_plural = "Anexos de Despesa"

    def __str__(self):
        return f"Anexo para {self.expense.description}"


class InstallmentPayment(models.Model):
    installment = models.ForeignKey(
        ExpenseInstallment, on_delete=models.CASCADE,
        related_name='payments', verbose_name="Parcela"
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor Pago")
    payment_date = models.DateField(verbose_name="Data do Pagamento")
    payment_method = models.CharField(
        max_length=20, choices=ExpenseInstallment.PaymentMethod.choices,
        null=True, blank=True, verbose_name="Meio de Pagamento"
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='installment_payments', verbose_name="Conta de Origem"
    )
    notes = models.TextField(blank=True, verbose_name="Observação")
    is_discount = models.BooleanField(default=False, verbose_name="É Desconto/Isenção")
    discount_reason = models.CharField(max_length=255, blank=True, verbose_name="Motivo do Desconto")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Registrado por"
    )

    class Meta:
        verbose_name = "Baixa de Parcela"
        verbose_name_plural = "Baixas de Parcela"
        ordering = ['payment_date', 'created_at']

    def __str__(self):
        return f"Baixa R$ {self.amount} em {self.payment_date}"


class PaymentAttachment(models.Model):
    payment = models.ForeignKey(
        InstallmentPayment, on_delete=models.CASCADE,
        related_name='attachments', verbose_name="Baixa"
    )
    file = models.FileField(
        upload_to='payment_attachments/%Y/%m/%d/',
        verbose_name="Arquivo"
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="Descrição")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comprovante de Pagamento"
        verbose_name_plural = "Comprovantes de Pagamento"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Comprovante de {self.payment}"


# --- MÓDULO DE CONTRATOS DE MANUTENÇÃO ---

class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nome da Categoria")
    icon = models.CharField(max_length=50, blank=True, default='tool', verbose_name="Ícone (Lucide)")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Categoria de Equipamento"
        verbose_name_plural = "Categorias de Equipamentos"
        ordering = ['name']


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_property = models.ForeignKey(
        Property, on_delete=models.CASCADE,
        related_name='assets', verbose_name="Imóvel"
    )
    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT,
        related_name='assets', verbose_name="Categoria"
    )
    name = models.CharField(max_length=255, verbose_name="Nome / Identificação")
    brand = models.CharField(max_length=100, blank=True, verbose_name="Marca")
    model_name = models.CharField(max_length=100, blank=True, verbose_name="Modelo")
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="Nº de Série")
    notes = models.TextField(blank=True, verbose_name="Observações Técnicas")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.client_property_id:
            return f"{self.name} — {self.client_property.address}, {self.client_property.number or ''}"
        return self.name

    @property
    def client(self):
        return self.client_property.client

    class Meta:
        verbose_name = "Equipamento / Bem"
        verbose_name_plural = "Equipamentos / Bens"
        ordering = ['name']


class MaintenanceContract(models.Model):
    class Frequency(models.TextChoices):
        SEMANAL = 'SEMANAL', 'Semanal'
        QUINZENAL = 'QUINZENAL', 'Quinzenal'
        MENSAL = 'MENSAL', 'Mensal'
        BIMESTRAL = 'BIMESTRAL', 'Bimestral'
        TRIMESTRAL = 'TRIMESTRAL', 'Trimestral'
        SEMESTRAL = 'SEMESTRAL', 'Semestral'
        ANUAL = 'ANUAL', 'Anual'

    class Status(models.TextChoices):
        ATIVO = 'ATIVO', 'Ativo'
        PAUSADO = 'PAUSADO', 'Pausado'
        ENCERRADO = 'ENCERRADO', 'Encerrado'

    DAYS_OF_WEEK = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT,
        related_name='contracts', verbose_name="Equipamento"
    )
    primary_technician = models.ForeignKey(
        Professional, on_delete=models.PROTECT,
        related_name='primary_maintenance_contracts', verbose_name="Técnico Titular"
    )
    monthly_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Mensal (R$)")
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('5.00'),
        verbose_name="Comissão do Técnico (%)"
    )
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices,
        default=Frequency.SEMANAL, verbose_name="Frequência"
    )
    # [0,2] = Segunda e Quarta; only used for SEMANAL/QUINZENAL
    visit_days = models.JSONField(default=list, verbose_name="Dias de Visita")
    description = models.TextField(blank=True, verbose_name="Descrição / Observações")
    start_date = models.DateField(verbose_name="Data de Início")
    end_date = models.DateField(null=True, blank=True, verbose_name="Data de Término (opcional)")
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.ATIVO, verbose_name="Status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.asset_id:
            return f"Contrato — {self.asset.name}"
        return "Contrato (sem equipamento)"

    @property
    def client(self):
        return self.asset.client_property.client

    @property
    def prop(self):
        return self.asset.client_property

    def calculate_expected_visits(self, month, year):
        import calendar as _cal
        if self.frequency == self.Frequency.SEMANAL:
            if not self.visit_days:
                return 4
            count = 0
            cal = _cal.monthcalendar(year, month)
            for day in self.visit_days:
                for week in cal:
                    if week[int(day)] != 0:
                        count += 1
            return count or 1
        elif self.frequency == self.Frequency.QUINZENAL:
            return max(len(self.visit_days) * 2, 1)
        return 1  # MENSAL, BIMESTRAL, TRIMESTRAL, SEMESTRAL, ANUAL

    def commission_per_visit(self, month, year):
        expected = self.calculate_expected_visits(month, year)
        return quantize_money(self.monthly_value * self.commission_rate / 100 / expected)

    class Meta:
        verbose_name = "Contrato de Manutenção"
        verbose_name_plural = "Contratos de Manutenção"
        ordering = ['-created_at']


class MaintenanceVisit(models.Model):
    class Status(models.TextChoices):
        AGENDADA = 'AGENDADA', 'Agendada'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
        CONCLUIDA = 'CONCLUIDA', 'Concluída'
        CANCELADA = 'CANCELADA', 'Cancelada'

    contract = models.ForeignKey(
        MaintenanceContract, on_delete=models.CASCADE,
        related_name='visits', verbose_name="Contrato"
    )
    scheduled_date = models.DateField(verbose_name="Data Agendada")
    executed_by = models.ForeignKey(
        Professional, on_delete=models.PROTECT,
        related_name='maintenance_visits_executed',
        null=True, blank=True, verbose_name="Técnico Executante"
    )
    # When the executante is someone not registered (rare)
    external_technician_name = models.CharField(
        max_length=255, blank=True, verbose_name="Técnico Externo (nome)"
    )
    is_coverage = models.BooleanField(default=False, verbose_name="É Cobertura?")
    coverage_receives_commission = models.BooleanField(
        default=False, verbose_name="Substituto Recebe Comissão?"
    )
    is_extra = models.BooleanField(
        default=False, verbose_name="Visita Extra (não gera comissão)"
    )
    check_in_at = models.DateTimeField(null=True, blank=True, verbose_name="Check-in")
    check_out_at = models.DateTimeField(null=True, blank=True, verbose_name="Check-out")
    notes = models.TextField(blank=True, verbose_name="Observações")
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.AGENDADA, verbose_name="Status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def commission_recipient(self):
        """Returns the Professional who earns commission, or None."""
        if self.is_extra:
            return None
        if self.is_coverage and self.coverage_receives_commission:
            return self.executed_by
        return self.contract.primary_technician

    def commission_value(self):
        recipient = self.commission_recipient()
        if not recipient:
            return Decimal('0')
        return self.contract.commission_per_visit(
            self.scheduled_date.month, self.scheduled_date.year
        )

    def __str__(self):
        return f"Visita {self.scheduled_date} — {self.contract.asset.name}"

    class Meta:
        verbose_name = "Visita de Manutenção"
        verbose_name_plural = "Visitas de Manutenção"
        ordering = ['-scheduled_date']


class MaintenanceVisitMedia(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visit = models.ForeignKey(
        MaintenanceVisit, on_delete=models.CASCADE,
        related_name='media', verbose_name="Visita"
    )
    file = models.FileField(upload_to='maintenance_media/%Y/%m/', verbose_name="Arquivo")
    file_type = models.CharField(max_length=50, blank=True, verbose_name="Tipo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mídia da Visita de Manutenção"
        verbose_name_plural = "Mídias das Visitas de Manutenção"
        ordering = ['created_at']


class MaintenanceMonthlyClosing(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', 'Rascunho'
        APROVADO = 'APROVADO', 'Aprovado'

    month = models.PositiveIntegerField(verbose_name="Mês")
    year = models.PositiveIntegerField(verbose_name="Ano")
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.RASCUNHO, verbose_name="Status"
    )
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Data de Aprovação")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="Criado por"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def month_display(self):
        MONTHS = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ]
        return f"{MONTHS[self.month]}/{self.year}"

    def __str__(self):
        return f"Fechamento {self.month:02d}/{self.year}"

    class Meta:
        verbose_name = "Fechamento Mensal de Manutenção"
        verbose_name_plural = "Fechamentos Mensais de Manutenção"
        unique_together = ('month', 'year')
        ordering = ['-year', '-month']


class MaintenanceClosingEntry(models.Model):
    closing = models.ForeignKey(
        MaintenanceMonthlyClosing, on_delete=models.CASCADE,
        related_name='entries', verbose_name="Fechamento"
    )
    technician = models.ForeignKey(
        Professional, on_delete=models.PROTECT,
        related_name='maintenance_closing_entries', verbose_name="Técnico"
    )
    total_commission = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Total de Comissão (R$)"
    )
    visits_count = models.PositiveIntegerField(default=0, verbose_name="Visitas Realizadas")
    # [{contract_id, asset_name, client, property, visits, commission_per_visit, subtotal}]
    detail = models.JSONField(default=list, verbose_name="Detalhamento")

    def __str__(self):
        return f"{self.technician.name} — {self.closing}"

    class Meta:
        verbose_name = "Entrada de Fechamento"
        verbose_name_plural = "Entradas de Fechamento"
        unique_together = ('closing', 'technician')
