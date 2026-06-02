# Especificação Completa de Engenharia: Módulo de Contas a Pagar (Single Tenant)

Este documento consolida toda a estratégia técnica, arquitetura de dados (Django ORM), regras de negócio transacionais e design de interface (IHC) para a implementação do módulo de **Contas a Pagar**. O fluxo e a disposição dos campos baseiam-se nos padrões de usabilidade do ERP Bling.

A arquitetura foi projetada de forma direta (**sem multi-tenancy** nesta fase inicial) para simplificar o desenvolvimento, testes e migrações.

---

## 1. Arquitetura do Banco de Dados (Django Models)

A modelagem separa o registro mestre da despesa (`DespesaRegistro`), que guarda a origem e a regra de recorrência, das parcelas reais (`DespesaParcela`), que são os títulos que entram no fluxo de caixa para receberem baixa. Isso evita inflar o banco de dados desnecessariamente.

```python
from django.db import models
from django.utils import timezone

class Fornecedor(models.Model):
    nome_razao = models.CharField(max_length=255, verbose_name="Razão Social/Nome")
    cnpj_cpf = models.CharField(max_length=18, blank=True, null=True, verbose_name="CNPJ/CPF")
    
    def __str__(self):
        return self.nome_razao

class CategoriaFinanceira(models.Model):
    nome = models.CharField(max_length=100) # Ex: Aluguel, Prolabore, Impostos, Licenças de Software
    
    def __str__(self):
        return self.nome

class ContaFinanceira(models.Model):
    nome = models.CharField(max_length=100) # Ex: Banco do Brasil, Itaú, Caixa Interno
    
    def __str__(self):
        return self.nome

class DespesaRegistro(models.Model):
    """Entidade mestre que armazena as regras de ocorrência e dados gerais da despesa."""
    OCORRENCIA_CHOICES = [
        ('unica', 'Única'),
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('anual', 'Anual'),
    ]
    
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    data_emissao = models.DateField(default=timezone.now)
    competencia = models.DateField()
    historico = models.TextField(max_length=2000, blank=True)
    num_documento = models.CharField(max_length=50, blank=True)
    
    # Bloco da Aba: Ocorrência (Inspirado no Bling)
    tipo_ocorrencia = models.CharField(max_length=20, choices=OCORRENCIA_CHOICES, default='unica')
    dia_vencimento_1 = models.PositiveIntegerField(help_text="Primeiro dia ou dia fixo de vencimento")
    dia_vencimento_2 = models.PositiveIntegerField(blank=True, null=True, help_text="Usado exclusivamente para a ocorrência Quinzenal")
    data_limite = models.DateField(blank=True, null=True, help_text="Data limite para a repetição acabar")
    considerar_dias_uteis = models.BooleanField(default=False)
    
    # Bloco da Aba: Taxas e Classificação
    juros_mensal = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    multa_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    categoria = models.ForeignKey(CategoriaFinanceira, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

class DespesaParcela(models.Model):
    """Entidade operacional que guarda os vencimentos reais que serão pagos."""
    STATUS_CHOICES = [
        ('aberto', 'Aberto'),
        ('pago', 'Pago'),
        ('cancelado', 'Cancelado'),
    ]
    
    FORMA_PAGAMENTO_CHOICES = [
        ('pix', 'Pix'),
        ('boleto', 'Boleto Bancário'),
        ('cartao', 'Cartão de Crédito'),
        ('dinheiro', 'Dinheiro'),
        ('transferencia', 'Transferência/TED'),
    ]

    despesa_registro = models.ForeignKey(DespesaRegistro, on_delete=models.CASCADE, related_name='parcelas')
    numero_parcela = models.PositiveIntegerField(default=1)
    valor_parcela = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aberto')
    
    # Bloco da Aba: Pagamento (Campos alimentados no momento da baixa)
    forma_pagamento = models.CharField(max_length=20, choices=FORMA_PAGAMENTO_CHOICES, blank=True, null=True)
    conta_financeira = models.ForeignKey(ContaFinanceira, on_delete=models.SET_NULL, null=True, blank=True)
    data_pagamento = models.DateField(blank=True, null=True)

class AnexoDespesa(models.Model):
    """Bloco da Aba: Anexos"""
    despesa_registro = models.ForeignKey(DespesaRegistro, on_delete=models.CASCADE, related_name='anexos')
    arquivo = models.FileField(upload_to='comprovantes_pagar/%Y/%m/%d/')
    enviado_em = models.DateTimeField(auto_now_add=True)
```

---

## 2. Regras de Negócio e Motor de Ocorrências

A geração de parcelas deve ocorrer de forma automatizada no momento em que a `DespesaRegistro` é salva. O sistema calcula o intervalo entre a data de competência inicial e a `data_limite` para gerar os vencimentos.

### 2.1. Ajuste de Fins de Semana (Filtro Dias Úteis)
Caso a flag `considerar_dias_uteis` seja marcada como verdadeira, o backend aplica a seguinte validação antes de persistir as parcelas, empurrando o vencimento que cair em fins de semana para o próximo dia útil:

```python
from datetime import timedelta

def calcular_dia_util(data_alvo):
    # 5 representa Sábado, 6 representa Domingo
    if data_alvo.weekday() == 5:
        return data_alvo + timedelta(days=2) # Pula para Segunda-feira
    elif data_alvo.weekday() == 6:
        return data_alvo + timedelta(days=1) # Pula para Segunda-feira
    return data_alvo
```

### 2.2. Geração Algorítmica da Recorrência Quinzenal
A ocorrência quinzenal extraída do Bling exige duas datas de pagamento dentro do mesmo mês civil. 
O gerador do seu backend deve realizar um laço de repetição que avança mês a mês. Para cada mês ativo, ele cria duas instâncias de `DespesaParcela`:
1. Uma substituindo o dia do vencimento pelo valor de `dia_vencimento_1`.
2. Outra substituindo o dia pelo valor de `dia_vencimento_2`.

Ambas as datas passam pela validação do método `calcular_dia_util` se a opção estiver ativada.

---

## 3. Arquitetura de Interface e Usabilidade (IHC)

A interface herda a estilização limpa do Tailwind CSS e o dinamismo de Single Page Applications (SPA) utilizando o **HTMX** dentro dos Django Templates, evitando recarregamentos desnecessários de página.

### 3.1. Navegação por Abas (Tabs)
As seções secundárias (**Pagamento**, **Ocorrência**, **Anexos**) ficam agrupadas na parte inferior do formulário. 
* A alternância entre as abas manipula apenas a classe `.hidden` do Tailwind via JavaScript leve.
* Isso retém os dados que o usuário já preencheu no topo do formulário (Fornecedor, Valor, Competência) enquanto ele navega pelas configurações adicionais.

### 3.2. Gatilhos de Inputs Condicionais (HTMX)
O select de Ocorrência monitora alterações do usuário.
* Se selecionado **"Quinzenal"**, o HTMX faz uma requisição assíncrona ao backend e injeta os inputs extras do `dia_vencimento_2` e `data_limite`.
* Se alterado de volta para **"Única"**, o bloco de recorrência é removido da tela pelo HTMX, reduzindo a carga cognitiva e impedindo o envio de dados incorretos.

```html
<div class="mb-4">
    <label class="block text-sm font-semibold text-gray-700">Ocorrência *</label>
    <select name="tipo_ocorrencia" 
            hx-get="/financeiro/contas-a-pagar/render-campos-ocorrencia/" 
            hx-target="#container-campos-dinamicos"
            hx-trigger="change"
            class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500">
        <option value="unica">Única</option>
        <option value="quinzenal">Quinzenal</option>
        <option value="mensal">Mensal</option>
    </select>
</div>

<div id="container-campos-dinamicos" class="mt-4">
    </div>
```