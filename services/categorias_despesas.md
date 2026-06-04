# Plano de Implementação: Categorias Financeiras Hierárquicas no Django

Este plano detalha passo a passo como construir um sistema de categorias de receitas e despesas estruturado em árvore (estilo ERP Bling) utilizando **Django** no ecossistema Python e a biblioteca **`django-mptt`** para gerenciar a hierarquia sem perda de performance.

O plano cobre desde a infraestrutura do banco de dados até a renderização de views e templates HTML customizados (sem depender do Django Admin integrado), incluindo regras de negócio estritas (ex: impedir lançamentos em categorias pai).

---

## 📅 Índice de Atividades
1. [Fase 1: Preparação do Ambiente](#fase-1-preparacao-do-ambiente)
2. [Fase 2: Arquitetura de Modelos (Banco de Dados)](#fase-2-arquitetura-de-modelos-banco-de-dados)
3. [Fase 3: Camada de Negócio e Validações](#fase-3-camada-de-negocio-e-validacoes)
4. [Fase 4: Formulários Customizados](#fase-4-formularios-customizados)
5. [Fase 5: Criação das Controladoras (Views)](#fase-5-criacao-das-controladoras-views)
6. [Fase 6: Criação dos Templates HTML (Interface Customizada)](#fase-6-criacao-dos-templates-html-interface-customizada)
7. [Fase 7: Motor de Relatório (DRE / Agregações)](#fase-7-motor-de-relatorio-dre-agregacoes)

---

## Fase 1: Preparação do Ambiente

Para manipular árvores com alta performance (evitando o problema de consultas recursivas `N+1` no banco de dados), utilizaremos o algoritmo MPTT (*Modified Preorder Tree Traversal*) integrado nativamente ao Django através do pacote `django-mptt`.

### 1. Instalação do Pacote
Instale a biblioteca utilizando o gerenciador de pacotes no seu ambiente virtual:
```bash
pip install django-mptt
```

### 2. Configuração do `settings.py`
Adicione `'mptt'` à lista de aplicações instaladas no seu projeto Django:
```python
INSTALLED_APPS = [
    # ... apps padrao do django ...
    'mptt',
    # ... seus apps ...
    'financas',
]
```

---

## Fase 2: Arquitetura de Modelos (Banco de Dados)

No arquivo `financas/models.py`, criaremos o modelo de categoria herdando de `MPTTModel` e configurando uma chave estrangeira especializada (`TreeForeignKey`).

```python
from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from django.core.exceptions import ValidationError

class CategoriaFinanceira(MPTTModel):
    TIPO_CHOICES = [
        ('RECEITA', 'Receita'),
        ('DESPESA', 'Despesa'),
    ]
    
    GRUPO_DRE_CHOICES = [
        ('DED_REC', 'Deduções da Receita Bruta'),
        ('DESP_OP', 'Despesas Operacionais'),
        ('DESP_FIN', 'Despesas Financeiras'),
        ('IMPOSTO', 'Impostos (IRPJ/CSLL)'),
        ('NENHUM', 'Não se aplica / Receitas'),
    ]

    nome = models.CharField(max_length=100, verbose_name="Nome da Categoria")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='DESPESA', verbose_name="Tipo")
    grupo_dre = models.CharField(max_length=10, choices=GRUPO_DRE_CHOICES, default='DESP_OP', verbose_name="Grupo do DRE")
    
    # Auto-relacionamento estruturado em árvore via MPTT
    parent = TreeForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='children', 
        verbose_name='Categoria Pai'
    )

    class MPTTMeta:
        order_insertion_by = ['nome']

    class Meta:
        verbose_name = 'Categoria Financeira'
        verbose_name_plural = 'Categorias Financeiras'

    def __str__(self):
        return self.nome

    @property
    def eh_agrupador(self):
        # Retorna True se a categoria possui subcategorias filhos (nao e uma folha)
        return not self.is_leaf_node()
```

---

## Fase 3: Camada de Negócio e Validações

Para seguir rigorosamente a regra de negócio do Bling, uma categoria com filhos atua **apenas como um agrupador**. Logo, lançamentos financeiros não podem ser vinculados diretamente a ela.

Abaixo, no mesmo arquivo `financas/models.py`, estruture o modelo de `LancamentoFinanceiro` aplicando essa validação na camada de persistência:

```python
class LancamentoFinanceiro(models.Model):
    descricao = models.CharField(max_length=200, verbose_name="Descrição")
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Valor (R$)")
    data = models.DateField(verbose_name="Data do Lançamento")
    categoria = models.ForeignKey(
        CategoriaFinanceira, 
        on_delete=models.PROTECT, 
        related_name='lancamentos',
        verbose_name="Categoria"
    )

    def clean(self):
        super().clean()
        # Impede o vinculo se a categoria contiver subcategorias associadas
        if self.categoria.eh_agrupador:
            raise ValidationError({
                'categoria': f"A categoria '{self.categoria.nome}' possui subcategorias ativas. "
                             f"Selecione uma subcategoria específica (nível folha) para salvar o lançamento."
            })

    def save(self, *args, **kwargs):
        self.full_clean() # Forca a validacao do metodo clean no ciclo de salvamento via ORM
        return super().save(*args, **kwargs)
```

### 🚀 Aplicação de Migrações
Execute os comandos no terminal para gerar e aplicar a nova estrutura de dados:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Fase 4: Formulários Customizados

No arquivo `financas/forms.py`, vamos customizar o comportamento do campo de seleção (`Select`) para que o usuário consiga identificar visualmente o nível hierárquico no HTML pelo recuo (`---`). Usaremos o `TreeNodeChoiceField` fornecido pelo MPTT.

```python
from django import forms
from mptt.forms import TreeNodeChoiceField
from .models import CategoriaFinanceira, LancamentoFinanceiro

class CategoriaForm(forms.ModelForm):
    # Campo especializado que ja renderiza a arvore identada com prefixos no HTML
    parent = TreeNodeChoiceField(
        queryset=CategoriaFinanceira.objects.all(),
        required=False,
        level_indicator='---',
        label="Categoria Pai"
    )

    class Meta:
        model = CategoriaFinanceira
        fields = ['nome', 'tipo', 'grupo_dre', 'parent']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'grupo_dre': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }


class LancamentoForm(forms.ModelForm):
    categoria = TreeNodeChoiceField(
        queryset=CategoriaFinanceira.objects.all(),
        level_indicator='---',
        label="Categoria Financeira"
    )

    class Meta:
        model = LancamentoFinanceiro
        fields = ['descricao', 'valor', 'data', 'categoria']
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'data': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
        }
```

---

## Fase 5: Criação das Controladoras (Views)

No arquivo `financas/views.py`, criaremos a lógica para listar a árvore de categorias e salvar novas entradas.

```python
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import CategoriaFinanceira
from .forms import CategoriaForm

def lista_categorias(request):
    # .all() traz os dados ordenados pela arvore correta gracas ao MPTT
    categorias = CategoriaFinanceira.objects.all()
    
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria cadastrada com sucesso!")
            return redirect('lista_categorias')
    else:
        form = CategoriaForm()

    context = {
        'categorias': categorias,
        'form': form
    }
    return render(request, 'financas/lista_categorias.html', context)
```

---

## Fase 6: Criação dos Templates HTML (Interface Customizada)

Crie o arquivo em `financas/templates/financas/lista_categorias.html`. Utilizaremos a template tag `recursetree` fornecida pelo `django-mptt` para renderizar subníveis recursivos de forma limpa, elegante e performática.

```html
{% load mptt_tags %}
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <title>Gerenciador de Categorias Financeiras</title>
    <!-- Exemplo usando CDN CSS do Bootstrap para agilizar layout -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        ul.tree-root, ul.tree-children {
            list-style-type: none;
            padding-left: 20px;
        }
        ul.tree-root { padding-left: 0; }
        .tree-node-item {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-left: 4px solid #0d6efd;
            padding: 8px 15px;
            margin-bottom: 5px;
            border-radius: 0 4px 4px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .tree-node-item.is-agrupador {
            border-left-color: #6c757d;
            background: #e9ecef;
            font-weight: bold;
        }
    </style>
</head>
<body class="bg-light">

<div class="container my-5">
    <div class="row">
        <!-- Coluna do Formulario -->
        <div class="col-md-4">
            <div class="card shadow-sm border-0">
                <div class="card-header bg-dark text-white">
                    <h5 class="card-title mb-0">Nova Categoria</h5>
                </div>
                <div class="card-body">
                    <form method="POST">
                        {% csrf_token %}
                        {% for field in form %}
                            <div class="mb-3">
                                <label class="form-label">{{ field.label }}</label>
                                {{ field }}
                                {% if field.errors %}
                                    <div class="text-danger small">{{ field.errors.0 }}</div>
                                {% endif %}
                            </div>
                        {% endfor %}
                        <button type="submit" class="btn btn-primary w-100">Salvar Categoria</button>
                    </form>
                </div>
            </div>
        </div>

        <!-- Coluna da Arvore Visual -->
        <div class="col-md-8">
            <div class="card shadow-sm border-0">
                <div class="card-header bg-dark text-white">
                    <h5 class="card-title mb-0">Plano de Contas Atual</h5>
                </div>
                <div class="card-body">
                    {% if messages %}
                        {% for msg in messages %}
                            <div class="alert alert-success">{{ msg }}</div>
                        {% endfor %}
                    {% endif %}

                    <ul class="tree-root">
                        {% recursetree categorias %}
                            <li>
                                <div class="tree-node-item {% if not node.is_leaf_node %}is-agrupador{% endif %}">
                                    <div>
                                        <span class="me-2">{% if not node.is_leaf_node %}📁{% else %}📄{% endif %}</span>
                                        {{ node.nome }}
                                    </div>
                                    <div>
                                        <span class="badge bg-secondary">{{ node.get_tipo_display }}</span>
                                        <span class="badge bg-info text-dark">{{ node.get_grupo_dre_display }}</span>
                                    </div>
                                </div>
                                
                                {# Verificacao do proprio MPTT se o no possui descendentes #}
                                {% if not node.is_leaf_node %}
                                    <ul class="tree-children">
                                        {{ children }}
                                    </ul>
                                {% endif %}
                            </li>
                        {% endrecursetree %}
                    </ul>

                </div>
            </div>
        </div>
    </div>
</div>

</body>
</html>
```

---

## Fase 7: Motor de Relatório (DRE / Agregações)

Para consolidar os relatórios financeiros e os totais por categoria Pai de forma otimizada (como coletar a soma de "Despesas Operacionais" capturando recursivamente todos os seus sub-níveis), utilize o método `get_descendants` provido pelo MPTT.

Abaixo, um exemplo prático de implementação de uma View agregadora:

```python
from django.db.models import Sum
from .models import CategoriaFinanceira, LancamentoFinanceiro

def obtener_total_categoria_com_filhos(categoria_nome):
    try:
        categoria_pai = CategoriaFinanceira.objects.get(nome=categoria_nome)
        
        # O argumento include_self=True garante que o valor da pai entre no somatorio, 
        # juntamente com os valores de todas as suas subcategorias filhos/netos.
        categorias_alvo = categoria_pai.get_descendants(include_self=True)
        
        resultado = LancamentoFinanceiro.objects.filter(
            categoria__in=categorias_alvo
        ).aggregate(total=Sum('valor'))
        
        return resultado['total'] or 0.00
    except CategoriaFinanceira.DoesNotExist:
        return 0.00

# Exemplo de chamada em uma view de Dashboard ou DRE:
# total_operacional = obter_total_categoria_com_filhos("Despesas Operacionais")
```

---
Este plano garante um ecossistema limpo, escalável e perfeitamente aderente ao comportamento de sistemas ERP profissionais de mercado.