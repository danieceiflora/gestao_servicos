"""Modelos de Expedição / Produção.

Uma Ordem de Produção (OP) é a fila de trabalho físico de um documento de
origem: uma `Sale` ou uma etapa de OS (`ServiceOrderTask` de EXECUCAO,
GARANTIA ou RETORNO).

PREMISSA CENTRAL: a OP **não** movimenta estoque. A baixa já acontece nos
caminhos de venda (`views_finance`, `views_pos`, `pos_payments`) e de OS
(`ServiceOrder.update_status`), e `Product.reduce_stock` já consome os
componentes de produtos compostos. Se a OP também movimentasse, seria dupla
baixa. A OP é um painel de trabalho, não um documento de estoque — e
`producao/tests.py` trava essa premissa com um teste.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from services.models import (
    Product, ProductVariant, Sale, SaleItem, ServiceItem, ServiceOrder,
    ServiceOrderTask,
)


class DeliveryMode(models.TextChoices):
    RETIRADA = 'RETIRADA', 'Retirada no balcão'
    TECNICO = 'TECNICO', 'Entrega ao técnico'
    ENVIO = 'ENVIO', 'Envio ao cliente'


#: Ícone (Lucide) e cores por situação — serve tanto para item quanto para
#: ordem, porque os valores dos dois enums não colidem.
#:
#: As classes são escritas por extenso de propósito: o Tailwind varre nomes
#: literais (inclusive em arquivos .py), então algo como `text-{cor}-500`
#: nunca seria gerado. Os nomes de ícone são os que o projeto já usa.
STATUS_UI = {
    # Itens de produção
    'PENDENTE': {
        'icon': 'circle-dashed', 'color': 'text-slate-400',
        'badge': 'bg-slate-100 text-slate-600', 'accent': 'border-l-slate-200',
    },
    'EM_ANDAMENTO': {
        'icon': 'play-circle', 'color': 'text-blue-500',
        'badge': 'bg-blue-100 text-blue-800', 'accent': 'border-l-blue-400',
    },
    'CONCLUIDO': {
        'icon': 'check-circle-2', 'color': 'text-emerald-600',
        'badge': 'bg-emerald-100 text-emerald-800', 'accent': 'border-l-emerald-500',
    },
    # Ordens de produção
    'AGUARDANDO': {
        'icon': 'clock', 'color': 'text-slate-400',
        'badge': 'bg-slate-100 text-slate-700', 'accent': 'border-l-slate-200',
    },
    'EM_SEPARACAO': {
        'icon': 'package-search', 'color': 'text-amber-500',
        'badge': 'bg-amber-100 text-amber-800', 'accent': 'border-l-amber-400',
    },
    'EM_PRODUCAO': {
        'icon': 'hammer', 'color': 'text-blue-500',
        'badge': 'bg-blue-100 text-blue-800', 'accent': 'border-l-blue-400',
    },
    'AGUARDANDO_MATERIAL': {
        'icon': 'alert-triangle', 'color': 'text-red-500',
        'badge': 'bg-red-100 text-red-800', 'accent': 'border-l-red-400',
    },
    'PRONTO': {
        'icon': 'check-circle-2', 'color': 'text-emerald-600',
        'badge': 'bg-emerald-100 text-emerald-800', 'accent': 'border-l-emerald-500',
    },
    'ENTREGUE': {
        'icon': 'truck', 'color': 'text-slate-500',
        'badge': 'bg-slate-900 text-white', 'accent': 'border-l-slate-800',
    },
    # Comum aos dois
    'CANCELADO': {
        'icon': 'x-circle', 'color': 'text-slate-300',
        'badge': 'bg-slate-200 text-slate-600', 'accent': 'border-l-slate-200',
    },
}

#: Eventos de histórico sem transição de status (ajuste de quantidade, nota).
NEUTRAL_UI = {
    'icon': 'info', 'color': 'text-slate-400',
    'badge': 'bg-slate-100 text-slate-600', 'accent': 'border-l-slate-200',
}


def status_ui(status):
    return STATUS_UI.get(status or '', NEUTRAL_UI)


class ProductionSettings(models.Model):
    """Singleton de configuração, no padrão de `fiscal.NFeConfig.load()`."""

    class ItemScope(models.TextChoices):
        TODOS = 'TODOS', 'Todos os produtos do pedido (lista de separação completa)'
        SOMENTE_PREPARO = 'SOMENTE_PREPARO', 'Apenas itens que exigem preparo (composição ou acabamento)'

    enabled = models.BooleanField(
        default=False, verbose_name="Módulo de Expedição / Produção ativo",
        help_text="Desligado, nenhuma ordem de produção é criada automaticamente.",
    )
    sale_trigger_statuses = models.JSONField(
        default=list, blank=True,
        verbose_name="Gerar ordem de produção quando a venda atingir",
        help_text="Rascunho não é oferecido de propósito: até a venda sair do "
                  "rascunho suas linhas ainda são apagadas e recriadas, e a "
                  "ordem de produção perderia o vínculo com os itens.",
    )
    task_trigger_statuses = models.JSONField(
        default=list, blank=True,
        verbose_name="Gerar ordem de produção quando a etapa de OS atingir",
        help_text="Vale apenas para etapas de Execução, Garantia e Retorno.",
    )
    require_task_approval = models.BooleanField(
        default=True, verbose_name="Exigir aprovação do cliente na etapa",
        help_text="Etapas marcadas como \"requer aprovação do cliente\" só entram "
                  "na fila depois de aprovadas.",
    )
    skip_sale_linked_to_order = models.BooleanField(
        default=True, verbose_name="Ignorar venda vinculada a uma OS",
        help_text="Evita que o mesmo material entre duas vezes na fila quando a "
                  "venda está vinculada a uma ordem de serviço. Nesse caso a "
                  "ordem de produção da etapa é a que vale.",
    )
    item_scope = models.CharField(
        max_length=20, choices=ItemScope.choices, default=ItemScope.TODOS,
        verbose_name="Quais itens entram na ordem de produção",
    )
    default_delivery_mode_sale = models.CharField(
        max_length=20, choices=DeliveryMode.choices, default=DeliveryMode.RETIRADA,
        verbose_name="Destino padrão para vendas",
        help_text="Vendas com endereço de entrega preenchido assumem \"Envio ao cliente\".",
    )
    default_delivery_mode_order = models.CharField(
        max_length=20, choices=DeliveryMode.choices, default=DeliveryMode.TECNICO,
        verbose_name="Destino padrão para etapas de OS",
    )

    class Meta:
        verbose_name = "Configurações de Expedição / Produção"
        verbose_name_plural = "Configurações de Expedição / Produção"

    def __str__(self):
        return "Configurações de Expedição / Produção"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ProductionOrder(models.Model):
    class Status(models.TextChoices):
        AGUARDANDO = 'AGUARDANDO', 'Aguardando início'
        EM_SEPARACAO = 'EM_SEPARACAO', 'Em separação'
        EM_PRODUCAO = 'EM_PRODUCAO', 'Em produção'
        AGUARDANDO_MATERIAL = 'AGUARDANDO_MATERIAL', 'Aguardando material'
        PRONTO = 'PRONTO', 'Pronto'
        ENTREGUE = 'ENTREGUE', 'Entregue'
        CANCELADO = 'CANCELADO', 'Cancelado'

    class Priority(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        URGENTE = 'URGENTE', 'Urgente'

    #: Status em que a OP ainda está no painel de trabalho.
    ACTIVE_STATUSES = (
        Status.AGUARDANDO, Status.EM_SEPARACAO, Status.EM_PRODUCAO,
        Status.AGUARDANDO_MATERIAL, Status.PRONTO,
    )
    #: Status terminais: `update_status()` não os sobrescreve.
    TERMINAL_STATUSES = (Status.ENTREGUE, Status.CANCELADO)

    number = models.PositiveIntegerField(unique=True, editable=False, verbose_name="Número")

    sale = models.OneToOneField(
        Sale, on_delete=models.CASCADE, null=True, blank=True,
        related_name='production_order', verbose_name="Venda",
    )
    service_order_task = models.OneToOneField(
        ServiceOrderTask, on_delete=models.CASCADE, null=True, blank=True,
        related_name='production_order', verbose_name="Etapa da OS",
    )
    # Denormalizado a partir da etapa. Serve para filtro/índice e faz o anexo de
    # PDF do motor de notificações funcionar sem código novo — ele resolve o
    # documento com getattr(instance, 'service_order') / getattr(instance, 'sale').
    service_order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, null=True, blank=True,
        related_name='production_orders', verbose_name="Ordem de Serviço",
    )

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.AGUARDANDO,
        db_index=True, verbose_name="Situação",
    )
    #: Status da origem que gerou/atualizou esta OP. É o que dispensa um
    #: `pre_save` para detectar transição — ver producao/signals.py.
    source_status = models.CharField(max_length=50, blank=True, editable=False)
    waiting_material = models.BooleanField(
        default=False, verbose_name="Aguardando material",
        help_text="Marcado manualmente pelo operador. O módulo não detecta falta "
                  "de saldo automaticamente — a baixa de estoque do pedido já "
                  "aconteceu antes de a ordem chegar aqui.",
    )
    waiting_material_note = models.CharField(max_length=255, blank=True, verbose_name="O que falta")

    delivery_mode = models.CharField(
        max_length=20, choices=DeliveryMode.choices, default=DeliveryMode.RETIRADA,
        verbose_name="Destino",
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL,
        verbose_name="Prioridade",
    )
    due_date = models.DateField(null=True, blank=True, verbose_name="Prazo")
    notes = models.TextField(blank=True, verbose_name="Observações")

    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="Entregue em")
    delivered_to = models.CharField(max_length=255, blank=True, verbose_name="Entregue a")
    received_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders_received', verbose_name="Recebido por",
    )
    carrier = models.CharField(max_length=120, blank=True, verbose_name="Transportadora")
    tracking_code = models.CharField(max_length=120, blank=True, verbose_name="Código de rastreio")
    delivery_notes = models.TextField(blank=True, verbose_name="Observações da entrega")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ordem de Produção"
        verbose_name_plural = "Ordens de Produção"
        ordering = ['-priority', 'due_date', 'number']
        permissions = [
            ('operate_production', 'Pode operar o painel de produção'),
            ('manage_production', 'Pode configurar a expedição / produção'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(sale__isnull=False) & Q(service_order_task__isnull=True))
                    | (Q(sale__isnull=True) & Q(service_order_task__isnull=False))
                ),
                name='production_order_exactly_one_source',
            ),
        ]

    def __str__(self):
        return f"OP #{self.number} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.number:
            from django.db.models import Max
            max_number = ProductionOrder.objects.aggregate(Max('number'))['number__max']
            self.number = (max_number or 0) + 1
        if self.service_order_task_id and not self.service_order_id:
            self.service_order_id = self.service_order_task.service_order_id
        super().save(*args, **kwargs)

    # --- Origem -------------------------------------------------------------

    @property
    def is_sale_origin(self):
        return self.sale_id is not None

    @property
    def origin_label(self):
        if self.sale_id:
            return f"Venda #{self.sale.number}"
        task = self.service_order_task
        if task:
            return f"OS #{task.service_order.number} — {task.get_task_type_display()}"
        return "—"

    @property
    def origin_url(self):
        from django.urls import reverse
        if self.sale_id:
            return reverse('sale_detail', args=[self.sale.number])
        if self.service_order_id:
            return reverse('service_order_detail', args=[self.service_order_id])
        return ''

    @property
    def client(self):
        if self.sale_id:
            return self.sale.client
        if self.service_order_id:
            prop = self.service_order.client_property
            return prop.client if prop else None
        return None

    @property
    def client_phone(self):
        from integracoes.utils import get_client_phone
        return get_client_phone(self.client)

    @property
    def technician_phone(self):
        """Telefone do primeiro profissional alocado na etapa.

        `integracoes.utils.get_client_phone` aceita string direta, então esta
        property serve como `phone_field_path` de uma regra de notificação.
        """
        task = self.service_order_task
        if not task:
            return None
        member = task.team_members.select_related('professional').first()
        return member.professional.phone if member else None

    @property
    def technician_users(self):
        """Usuários dos profissionais alocados na etapa (para push interno)."""
        task = self.service_order_task
        if not task:
            return []
        return [
            m.professional.user
            for m in task.team_members.select_related('professional__user')
            if m.professional.user_id
        ]

    # --- Progresso ----------------------------------------------------------

    @property
    def active_items(self):
        return [i for i in self.items.all() if i.status != ProductionItem.Status.CANCELADO]

    @property
    def progress_percent(self):
        """Use com `prefetch_related('items')` — em lista isto é N+1."""
        items = self.active_items
        total = sum((i.quantity for i in items), Decimal('0'))
        if not total:
            return 0
        done = sum((min(i.quantity_done, i.quantity) for i in items), Decimal('0'))
        return int((done / total) * 100)

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL_STATUSES

    @property
    def ui(self):
        """Ícone e cores da situação, para o template não montar classes."""
        return status_ui(self.status)


class ProductionItem(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em andamento'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        CANCELADO = 'CANCELADO', 'Cancelado'

    class Kind(models.TextChoices):
        SEPARACAO = 'SEPARACAO', 'Separação'
        FABRICACAO = 'FABRICACAO', 'Fabricação'
        ACABAMENTO = 'ACABAMENTO', 'Acabamento'

    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name='items',
    )

    #: Identidade estável da linha de origem, ex. "sale_item:1234".
    #: É a chave de matching da sincronização — NUNCA a FK, que é SET_NULL
    #: porque os três caminhos de edição de venda/OS deletam linhas de verdade.
    source_key = models.CharField(max_length=80, blank=True, db_index=True)
    sale_item = models.ForeignKey(
        SaleItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_items',
    )
    service_item = models.ForeignKey(
        ServiceItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_items',
    )

    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_items', verbose_name="Produto",
    )
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_items', verbose_name="Variação",
    )
    #: Snapshot textual: sobrevive à exclusão ou inativação do produto.
    description = models.CharField(max_length=255, verbose_name="Descrição")

    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'), verbose_name="Quantidade")
    quantity_done = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'), verbose_name="Quantidade pronta")

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDENTE,
        db_index=True, verbose_name="Situação",
    )
    needs_review = models.BooleanField(
        default=False, verbose_name="Revisar",
        help_text="A origem reduziu a quantidade abaixo do que já foi produzido.",
    )

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    finished_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_items_finished',
    )
    notes = models.TextField(blank=True, verbose_name="Observações")

    created_at = models.DateTimeField(auto_now_add=True)
    #: Necessário para o cálculo de versão do painel (resposta 204 no polling).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item de Produção"
        verbose_name_plural = "Itens de Produção"
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['production_order', 'source_key'],
                condition=~Q(source_key=''),
                name='uniq_production_item_source',
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.description}"

    # ATENÇÃO: `save()` NÃO chama `production_order.update_status()`.
    # Esse é o anti-padrão de `ServiceItem.save()`, que faz um save da OS por
    # item do formset. Toda mutação passa por `producao/services.py`, que
    # recalcula o status uma única vez.

    @property
    def kind(self):
        product = self.product
        if product is None:
            return self.Kind.SEPARACAO
        if getattr(product, 'requires_finishing', False):
            return self.Kind.ACABAMENTO
        if product.format == Product.Format.COM_COMPOSICAO:
            return self.Kind.FABRICACAO
        return self.Kind.SEPARACAO

    @property
    def kind_display(self):
        return self.Kind(self.kind).label

    @property
    def ui(self):
        return status_ui(self.status)

    @property
    def is_done(self):
        return self.status == self.Status.CONCLUIDO

    @property
    def quantity_pending(self):
        return max(self.quantity - self.quantity_done, Decimal('0'))

    @property
    def stock_target(self):
        """Alvo de saldo: a variação quando houver, senão o produto."""
        return self.variant or self.product


class ProductionEvent(models.Model):
    """Timeline append-only. Dá auditoria ao acompanhamento entre departamentos."""

    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name='events',
    )
    production_item = models.ForeignKey(
        ProductionItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_events',
    )
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25, blank=True)
    message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de Produção"
        verbose_name_plural = "Eventos de Produção"
        ordering = ['-created_at', '-id']

    @property
    def ui(self):
        """Derivado de `to_status`.

        As ações de item também gravam `to_status` (ver `producao/services.py`),
        então o histórico ganha o mesmo ícone do item sem precisar de um campo
        novo. Eventos puramente informativos caem no ícone neutro.
        """
        return status_ui(self.to_status)

    @property
    def label(self):
        if self.message:
            return self.message
        labels = {s: str(l) for s, l in ProductionOrder.Status.choices}
        labels.update({s: str(l) for s, l in ProductionItem.Status.choices})
        origem = labels.get(self.from_status, self.from_status)
        destino = labels.get(self.to_status, self.to_status)
        return f"{origem} → {destino}" if origem or destino else "Evento"

    def __str__(self):
        return self.label
