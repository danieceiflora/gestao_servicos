# Plano de Implementação: Controle de Estoque

Este documento descreve as etapas para implementar o módulo de controle de estoque no sistema **Gestão de Serviços PWA**.

## 1. Alterações no Banco de Dados (Models)

### 1.1 Atualizar `Product`
Adicionar campo para saldo atual.
- `current_stock`: `DecimalField(max_digits=10, decimal_places=2, default=0)`

### 1.2 Criar `StockMovement`
Registrar todo o histórico de entradas e saídas.
- `product`: `ForeignKey(Product)`
- `quantity`: `DecimalField` (sempre positivo)
- `movement_type`: `Choices` (ENTRADA, SAÍDA)
- `reason`: `Choices` (COMPRA, VENDA_OS, AJUSTE, PERDA, DEVOLUCAO)
- `service_order`: `ForeignKey(ServiceOrder, null=True, blank=True)` (para vincular saídas à OS)
- `user`: `ForeignKey(User)` (quem realizou o movimento)
- `created_at`: `DateTimeField`

---

## 2. Interface Administrativa (Templates & Views)

### 2.1 Gestão de Produtos
Criar telas para gerenciar o cadastro de produtos sem depender do Admin do Django.
- **Lista de Produtos**: Tabela com nome, código, unidade e saldo atual.
- **Cadastro/Edição**: Form para `Product`.

### 2.2 Movimentação de Estoque
- **Registrar Entrada/Saída**: Tela simples para selecionar produto, quantidade, tipo e motivo.
- **Histórico**: Visualização dos últimos movimentos de um produto específico.

---

## 3. Integração com Ordem de Serviço (Automação)

### 3.1 Saída Automática
Ao adicionar um `ServiceItem` que possua um `product` vinculado na OS:
- Criar automaticamente um `StockMovement` do tipo **SAÍDA** (motivo: VENDA_OS).
- Atualizar o `current_stock` do `Product`.

### 3.2 Estorno Automático
Ao remover um `ServiceItem` da OS:
- Criar automaticamente um `StockMovement` do tipo **ENTRADA** (motivo: DEVOLUCAO).
- Atualizar o `current_stock` do `Product`.

---

## 4. Passo a Passo da Implementação

### Sprint 1: Infraestrutura e Cadastro
1.  Modificar `services/models.py` com os novos campos e modelos.
2.  Executar `makemigrations` e `migrate`.
3.  Criar `ProductForm` e `StockMovementForm` em `services/forms.py`.
4.  Implementar Views de Lista e Cadastro de Produtos em `services/views.py`.
5.  Criar templates `product_list.html` e `product_form.html`.

### Sprint 2: Movimentação Manual
1.  Implementar View para registrar movimento de estoque.
2.  Criar template `stock_movement_form.html`.
3.  Adicionar aba "Histórico de Estoque" no detalhe do produto.

### Sprint 3: Automação e Validação
1.  Ajustar a view `order_item_add` para processar a baixa no estoque.
2.  Ajustar a view `order_item_delete` para processar o estorno.
3.  (Opcional) Adicionar aviso visual na OS quando um produto estiver sem saldo.

---

## 5. Próximos Passos
1.  Revisar este plano.
2.  Iniciar a Sprint 1.
