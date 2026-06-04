# Estratégia: Contas a Pagar com Recorrência Inteligente

## Visão Geral

Substituir a geração antecipada de todas as parcelas por um sistema de três camadas:
1. **Regras de recorrência** persistidas no banco
2. **Job diário** que gera registros reais com antecedência configurável
3. **API de projeção dinâmica** que combina dados reais + projeções calculadas em memória

---

## Fase 1 — Modelos de Dados

### 1.1 Novo modelo: `RecurrenceRule`

```python
# services/models.py (ou finance/models.py)

class RecurrenceRule(models.Model):
    FREQUENCY_CHOICES = [
        ('DAILY',    'Diário'),
        ('WEEKLY',   'Semanal'),
        ('MONTHLY',  'Mensal'),
        ('YEARLY',   'Anual'),
    ]

    supplier        = models.ForeignKey('Supplier', on_delete=models.PROTECT)
    category        = models.ForeignKey('ExpenseCategory', null=True, blank=True, on_delete=models.SET_NULL)
    description     = models.CharField(max_length=255)
    amount          = models.DecimalField(max_digits=12, decimal_places=2)
    frequency       = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    start_date      = models.DateField()
    end_date        = models.DateField(null=True, blank=True)  # null = sem fim
    is_active       = models.BooleanField(default=True)
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Regra de Recorrência'
        verbose_name_plural = 'Regras de Recorrência'

    def get_due_dates_in_range(self, start, end):
        """Calcula datas de vencimento no intervalo. Não persiste nada."""
        from dateutil.relativedelta import relativedelta
        dates = []
        current = self.start_date
        delta_map = {
            'DAILY':   relativedelta(days=1),
            'WEEKLY':  relativedelta(weeks=1),
            'MONTHLY': relativedelta(months=1),
            'YEARLY':  relativedelta(years=1),
        }
        delta = delta_map[self.frequency]
        while current <= end:
            if current >= start:
                dates.append(current)
            current += delta
            if self.end_date and current > self.end_date:
                break
        return dates
```

### 1.2 Ajuste no modelo `ExpenseInstallment`

Adicionar FK opcional para rastrear origem da recorrência e evitar duplicatas:

```python
class ExpenseInstallment(models.Model):
    # ... campos existentes ...
    recurrence_rule = models.ForeignKey(
        'RecurrenceRule',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_installments'
    )
    recurrence_due_date = models.DateField(null=True, blank=True)  # data exata da ocorrência gerada
```

**Por que `recurrence_due_date`?** Permite saber qual ocorrência da regra já foi gerada, evitando duplicatas no job diário.

### 1.3 Novo modelo: `FinanceSettings` (configurações por empresa/cliente)

```python
class FinanceSettings(models.Model):
    # Se o sistema for multi-tenant, FK para company/tenant
    days_before_generation = models.PositiveIntegerField(
        default=7,
        help_text='Quantos dias antes do vencimento gerar o registro de contas a pagar'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configurações Financeiras'
```

### 1.4 Migration

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Fase 2 — Ajuste no Formulário de Despesa

### 2.1 Lógica do `expense_form.html`

Quando `is_recurrent = True`, o formulário deve:
- Mostrar campos: `frequency`, `start_date`, `end_date` (opcional)
- **Não** mostrar mais o campo `installments_count` (irrelevante para recorrência sem fim)
- Ao salvar: criar um `RecurrenceRule` em vez de gerar `ExpenseInstallment`s

Quando `is_recurrent = False`, comportamento atual mantido (parcelamento com `installments_count`).

### 2.2 Ajuste na View `expense_create`

```python
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            if form.cleaned_data['is_recurrent']:
                # Salva apenas a regra
                RecurrenceRule.objects.create(
                    supplier=form.cleaned_data['supplier'],
                    category=form.cleaned_data['category'],
                    description=form.cleaned_data['description'],
                    amount=form.cleaned_data['total_amount'],
                    frequency=form.cleaned_data['frequency'],
                    start_date=form.cleaned_data['issue_date'],
                    end_date=form.cleaned_data.get('end_date'),
                    created_by=request.user,
                )
                messages.success(request, 'Regra de recorrência criada com sucesso.')
                return redirect('expense_list')
            else:
                # Fluxo atual: gera parcelas normalmente
                expense = form.save()
                # ... gera installments ...
```

---

## Fase 3 — Job Diário de Geração

### 3.1 Management Command (opção simples, sem Celery)

```
services/management/commands/generate_recurring_expenses.py
```

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from services.models import RecurrenceRule, ExpenseInstallment, FinanceSettings

class Command(BaseCommand):
    help = 'Gera registros de contas a pagar a partir das regras de recorrência'

    def handle(self, *args, **kwargs):
        settings_obj = FinanceSettings.objects.first()
        days_ahead = settings_obj.days_before_generation if settings_obj else 7
        today = timezone.localdate()
        target_date = today + timezone.timedelta(days=days_ahead)

        rules = RecurrenceRule.objects.filter(is_active=True)

        for rule in rules:
            due_dates = rule.get_due_dates_in_range(today, target_date)
            for due_date in due_dates:
                already_exists = ExpenseInstallment.objects.filter(
                    recurrence_rule=rule,
                    recurrence_due_date=due_date
                ).exists()
                if not already_exists:
                    ExpenseInstallment.objects.create(
                        recurrence_rule=rule,
                        recurrence_due_date=due_date,
                        due_date=due_date,
                        amount=rule.amount,
                        description=rule.description,
                        supplier=rule.supplier,
                        category=rule.category,
                        status='PENDING',
                    )
                    self.stdout.write(f'Gerado: {rule.description} | Vencimento: {due_date}')
```

### 3.2 Agendamento via cron (servidor Linux)

```cron
0 6 * * * /path/to/venv/bin/python /path/to/manage.py generate_recurring_expenses
```

### 3.3 Agendamento via Celery Beat (se já usar Celery)

```python
# celery.py ou settings.py
CELERY_BEAT_SCHEDULE = {
    'generate-recurring-expenses': {
        'task': 'services.tasks.generate_recurring_expenses',
        'schedule': crontab(hour=6, minute=0),
    },
}
```

---

## Fase 4 — API de Projeção Dinâmica

### 4.1 Endpoint

```
GET /api/finance/expenses/forecast/?start=2026-06-01&end=2026-06-30
```

### 4.2 View da API

```python
# services/views_finance.py

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import ExpenseInstallment, RecurrenceRule

@require_GET
def expense_forecast_api(request):
    start_str = request.GET.get('start')
    end_str   = request.GET.get('end')

    if not start_str or not end_str:
        return JsonResponse({'error': 'Parâmetros start e end são obrigatórios'}, status=400)

    from datetime import date
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str)

    # 1. Registros reais já gerados no período
    real_installments = ExpenseInstallment.objects.filter(
        due_date__range=(start, end)
    ).select_related('supplier', 'category', 'recurrence_rule')

    real_data = [
        {
            'id':          inst.id,
            'type':        'real',
            'description': inst.description,
            'supplier':    inst.supplier.name if inst.supplier else '',
            'amount':      str(inst.amount),
            'due_date':    inst.due_date.isoformat(),
            'status':      inst.status,
        }
        for inst in real_installments
    ]

    # IDs de ocorrências já geradas (para não duplicar nas projeções)
    generated_keys = set(
        real_installments
        .filter(recurrence_rule__isnull=False)
        .values_list('recurrence_rule_id', 'recurrence_due_date')
    )

    # 2. Projeções: regras ativas, calculadas em memória
    rules = RecurrenceRule.objects.filter(is_active=True)
    projected_data = []

    for rule in rules:
        due_dates = rule.get_due_dates_in_range(start, end)
        for due_date in due_dates:
            if (rule.id, due_date) not in generated_keys:
                projected_data.append({
                    'id':          None,
                    'type':        'projected',
                    'description': rule.description,
                    'supplier':    rule.supplier.name if rule.supplier else '',
                    'amount':      str(rule.amount),
                    'due_date':    due_date.isoformat(),
                    'status':      'PROJECTED',
                    'rule_id':     rule.id,
                })

    # 3. Une e ordena por data
    all_entries = sorted(real_data + projected_data, key=lambda x: x['due_date'])

    return JsonResponse({'results': all_entries, 'count': len(all_entries)})
```

### 4.3 URL

```python
# urls.py
path('api/finance/expenses/forecast/', views_finance.expense_forecast_api, name='expense_forecast_api'),
```

---

## Fase 5 — Interface de Consulta (Frontend)

### 5.1 Filtro de período na listagem de contas a pagar

Adicionar ao template `expense_list.html`:
- Inputs de data (início e fim)
- Botão "Consultar"
- Tabela que exibe resultados com badge visual diferenciando `real` vs `projetado`

### 5.2 Chamada HTMX ou fetch

```javascript
async function loadForecast(start, end) {
    const res = await fetch(`/api/finance/expenses/forecast/?start=${start}&end=${end}`);
    const data = await res.json();
    renderTable(data.results);
}

function renderTable(entries) {
    // entries com type='real' -> badge verde "Gerado"
    // entries com type='projected' -> badge cinza "Previsto"
}
```

### 5.3 Diferenciação visual

| Tipo      | Badge          | Cor        | Ações disponíveis         |
|-----------|----------------|------------|---------------------------|
| `real`    | Gerado         | Emerald    | Ver, Editar, Pagar        |
| `projected` | Previsto     | Slate/Gray | Apenas visualizar         |

---

## Fase 6 — Configurações do Cliente

### 6.1 Tela de configurações financeiras

Rota: `/finance/settings/`

Campos:
- **Dias de antecedência para geração** (`days_before_generation`): input numérico, padrão 7

### 6.2 View simples

```python
def finance_settings_view(request):
    obj, _ = FinanceSettings.objects.get_or_create(pk=1)
    form = FinanceSettingsForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Configurações salvas.')
        return redirect('finance_settings')
    return render(request, 'services/finance/finance_settings.html', {'form': form})
```

---

## Ordem de Implementação Recomendada

1. [ ] Criar modelos `RecurrenceRule` e `FinanceSettings`, ajustar `ExpenseInstallment`
2. [ ] Gerar e rodar migrations
3. [ ] Ajustar `ExpenseForm` e view `expense_create` para bifurcar fluxo recorrente/parcelado
4. [ ] Criar management command `generate_recurring_expenses`
5. [ ] Criar endpoint `expense_forecast_api`
6. [ ] Criar tela de configurações (`FinanceSettings`)
7. [ ] Atualizar `expense_list.html` com filtro de período e renderização de projeções
8. [ ] Testar job manualmente com `python manage.py generate_recurring_expenses`
9. [ ] Configurar agendamento (cron ou Celery Beat)

---

## Dependências Necessárias

```
python-dateutil  # para relativedelta no cálculo de datas
```

```bash
pip install python-dateutil
```

---

## Notas Importantes

- **Idempotência do job:** A checagem por `(recurrence_rule_id, recurrence_due_date)` garante que rodar o job várias vezes no mesmo dia não gera duplicatas.
- **Editar uma regra de recorrência:** Apenas afeta ocorrências futuras ainda não geradas. Registros já gerados permanecem inalterados.
- **Cancelar uma recorrência:** Setar `is_active=False` na `RecurrenceRule`. O job para de gerar, ocorrências já criadas continuam existindo.
- **Fuso horário:** Usar sempre `timezone.localdate()` no job para respeitar o timezone configurado no Django (`TIME_ZONE` no `settings.py`).
