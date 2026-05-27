# Plano de Implementação: Módulo de Vendas (PDV)

Este documento descreve as etapas para implementar o módulo de Vendas Diretas no sistema **Gestão de Serviços PWA**. O objetivo é permitir a venda de produtos independentemente de uma Ordem de Serviço, com baixa automática no estoque e registro financeiro.

## 1. Arquitetura de Dados (Models)

### 1.1 Criar `Sale` (Venda)
Representa o cabeçalho da venda.
- `uuid`: `UUIDField` (ID público)
- `client`: `ForeignKey(Client, null=True, blank=True)` (Venda para cliente cadastrado ou "Consumidor Final")
- `user`: `ForeignKey(User)` (Vendedor/Operador que realizou a venda)
- `status`: `Choices` (RASCUNHO, CONCLUIDA, CANCELADA)
- `total_amount`: `DecimalField` (Valor total da venda)
- `discount`: `DecimalField` (Desconto aplicado no total)
- `payment_method`: `Choices` (DINHEIRO, PIX, CARTAO_DEBITO, CARTAO_CREDITO)
- `service_order`: `ForeignKey(ServiceOrder, null=True, blank=True)` (Opcional: vincular venda a uma OS específica)
- `created_at`: `DateTimeField`
- `updated_at`: `DateTimeField`

### 1.2 Criar `SaleItem` (Itens da Venda)
Itens individuais da venda.
- `sale`: `ForeignKey(Sale, related_name='items')`
- `product`: `ForeignKey(Product)`
- `quantity`: `DecimalField`
- `unit_price`: `DecimalField` (Preço no momento da venda)
- `subtotal`: `DecimalField`

---

## 2. Fluxo de Trabalho (Workflow)

1.  **Abertura de Venda:** O vendedor inicia uma nova venda.
2.  **Seleção de Produtos:** Adição de itens via busca por nome ou código (leitura de código de barras futuro).
3.  **Seleção do Cliente:** Opcional (pode ser "Venda Balcão").
4.  **Pagamento e Fechamento:** Escolha do método de pagamento e aplicação de descontos.
5.  **Processamento:**
    - Baixa automática no estoque (`StockMovement` do tipo SAÍDA, motivo VENDA).
    - Geração de entrada no módulo Financeiro (futuro).
    - Geração de recibo simples (PDF).

---

## 3. Interface (UI/UX) - Mobile First

### 3.1 Terminal de Vendas (PDV)
- Interface limpa e rápida.
- Busca reativa de produtos.
- Carrinho de compras visível com totalizador em tempo real.

### 3.2 Listagem de Vendas
- Histórico de vendas realizadas.
- Filtros por data, vendedor e status.
- Ação para estorno (cancelamento) de venda.

---

## 4. Cronograma de Implementação (Sprints)

### Sprint 1: Estrutura Base
1. Criar modelos `Sale` e `SaleItem` em `services/models.py`.
2. Criar migrações e aplicar.
3. Registrar no `admin.py` para testes iniciais.

### Sprint 2: Interface de Venda (Backend + Frontend)
1. Criar `SaleCreateView` e `SaleDetailView`.
2. Implementar lógica de adição de itens via Formset dinâmico ou AJAX.
3. Criar templates responsivos para o PDV.

### Sprint 3: Integrações e Finalização
1. Implementar signals/lógica para baixa automática de estoque.
2. Criar view para geração de Recibo de Venda (PDF).
3. Implementar cancelamento de venda com estorno de estoque.
4. Adicionar dashboard simples de vendas (Total do dia/mês).

---

## 5. Considerações Técnicas
- **Performance:** A busca de produtos deve ser otimizada (Select2 ou similar).
- **Offline:** Considerar o registro da venda localmente se o PWA estiver offline, sincronizando ao voltar o sinal.
- **IHC:** Garantir que o botão de "Finalizar Venda" seja proeminente e exija confirmação se o valor for alto.
