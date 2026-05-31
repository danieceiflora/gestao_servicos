# Plano de Ação: Estruturação de Métodos de Pagamento e Preparação Fiscal

Este documento especifica a arquitetura de banco de dados, regras de negócio e fluxo de interface para o novo submódulo de **Formas e Métodos de Pagamento**. A estrutura isola a operação comercial (maquininhas/bancos) da classificação fiscal, deixando o sistema pronto para a emissão de notas no futuro.

---

## 1. Arquitetura do Banco de Dados

Para suportar múltiplos provedores (Stone, Cielo, PIX Banco do Brasil, etc.) e conciliação financeira, utilizaremos uma estrutura relacional de duas tabelas.

### A. Cadastro de Métodos de Pagamento (`metodos_pagamento`)
Esta tabela gerencia as opções que a empresa aceita e suas respectivas taxas/regras.

| Campo | Tipo | Nulável | Descrição / Exemplo |
| :--- | :--- | :--- | :--- |
| `id` | BigInt | Não | Chave primária. |
| `descricao` | String | Não | Nome legível para o operador (Ex: "Crédito - Stone", "PIX - BB"). |
| `tipo_provedor` | Enum | Não | `DINHEIRO`, `CARTAO_CREDITO`, `CARTAO_DEBITO`, `PIX`, `BOLETO`, `CREDIARIO`. |
| `tarifa_porcentagem` | Decimal(5,2) | Não | Taxa cobrada pelo intermediador (Ex: `2.50` para 2,5%). Padrão `0.00`. |
| `tarifa_fixa` | Decimal(10,2)| Não | Taxa fixa por transação (Ex: `0.50` por boleto). Padrão `0.00`. |
| `prazo_recebimento` | Integer | Não | Dias para o dinheiro ficar disponível (Ex: `0` para PIX, `30` para Crédito). |
| `codigo_sefaz` | String | Não | **Código oficial da SEFAZ para mapeamento fiscal futuro (Ver Seção 4).** |
| `ativo` | Boolean | Não | Permite desativar um método sem apagar o histórico. Padrão `True`. |

### B. Registro de Pagamentos da Venda (`venda_pagamentos`)
Tabela associativa que guarda as transações financeiras de cada pedido de venda ou Ordem de Serviço. Suporta pagamentos parciais e múltiplos métodos na mesma venda.

| Campo | Tipo | Nulável | Descrição / Exemplo |
| :--- | :--- | :--- | :--- |
| `id` | BigInt | Não | Chave primária. |
| `venda_id` | BigInt | Sim | Chave estrangeira para a tabela de vendas (nulo se for atrelado direto à OS). |
| `os_id` | BigInt | Sim | Chave estrangeira para a tabela de OS (nulo se for venda direta de balcão). |
| `metodo_pagamento_id`| BigInt | Não | Chave estrangeira apontando para `metodos_pagamento`. |
| `valor_bruto` | Decimal(10,2)| Não | O valor exato que o cliente pagou na maquininha/dinheiro. |
| `valor_tarifa` | Decimal(10,2)| Não | Calculado no backend: $(\text{valor\_bruto} \times \text{tarifa\_porcentagem}) + \text{tarifa\_fixa}$. |
| `valor_liquido` | Decimal(10,2)| Não | Calculado no backend: $\text{valor\_bruto} - \text{valor\_tarifa}$. |
| `data_pagamento` | DateTime | Não | Momento em que o pagamento foi registrado. |
| `data_previsao` | Date | Não | `data_pagamento` + `prazo_recebimento` (Para projeção de fluxo de caixa). |

---

## 2. Fluxo de Interface (UX) no Fechamento da Venda

A interface da tela de vendas consumirá esses dados dinamicamente na coluna de fechamento (Painel Direito).

1. **Seleção do Valor:** O sistema exibe o "Saldo Devedor". O operador pode manter o valor total ou digitar um valor menor (Pagamento Parcial).
2. **Seleção do Método:** Um dropdown exibe apenas os métodos cadastrados que estão com `ativo = True`. 
   * *Exibição amigável:* O dropdown mostra a `descricao` (Ex: "PIX - Banco do Brasil").
3. **Confirmação:** Ao clicar em **"Registrar Pagamento"**:
   * O sistema insere o registro na tabela `venda_pagamentos`.
   * Recalcula imediatamente os totais na tela (Subtrai o `valor_bruto` do Saldo Devedor).
   * Adiciona o pagamento a uma lista visual de "Pagamentos Realizados nesta Venda" com um botão para estornar/remover caso o operador tenha errado.

---

## 3. Regras de Negócio e Casos de Uso (Parcial / Prazo)

* **Venda Paga Integralmente:** O Saldo Devedor chega a `0.00`. O sistema libera o botão de "Finalizar Venda" e imprime o cupom não fiscal.
* **Venda Paga Parcialmente (Com Entrega Imediata):** O cliente paga uma parte e o resto fica "fiado" (Crediário) ou será pago depois. O operador registra o pagamento parcial usando o método desejado. O valor restante deve ser registrado obrigatoriamente utilizando um método cadastrado como `tipo_provedor = CREDIARIO` (ou "Conta Cliente"), zerando o saldo da tela e gerando uma conta a receber para o cliente.
* **Venda para Pagar Depois (Venda Online / Faturamento na OS):** Nenhum pagamento é lançado na hora da abertura do pedido. O pedido/OS é salvo com o status "Pendente de Pagamento". Os lançamentos financeiros só serão feitos quando o cliente vier retirar/receber o produto.

---

## 4. Tabela de Mapeamento Oficial SEFAZ (`codigo_sefaz`)

Ao cadastrar os métodos de pagamento na retaguarda do sistema, o campo `codigo_sefaz` deverá ser preenchido seguindo rigorosamente a tabela oficial da Nota Fiscal Eletrônica. 

Mesmo que o cupom gerado agora seja **sem efeito fiscal**, este código será impresso no layout do cupom para homologação visual e validação do fluxo.

| Tipo de Provedor (Sistema) | Código SEFAZ | Descrição Oficial da SEFAZ |
| :--- | :--- | :--- |
| `DINHEIRO` | `01` | Dinheiro |
| - | `02` | Cheque |
| `CARTAO_CREDITO` | `03` | Cartão de Crédito |
| `CARTAO_DEBITO` | `04` | Cartão de Débito |
| - | `05` | Crédito Loja (Crediário Próprio) |
| - | `10` | Vale Alimentação |
| - | `11` | Vale Refeição |
| - | `12` | Vale Presente |
| - | `13` | Vale Combustível |
| `BOLETO` | `15` | Boleto Bancário |
| `PIX` | `17` | Pagamento Instantâneo (PIX) |
| `CREDIARIO` / Outros | `99` | Outros |

### Exemplo de Carga Inicial (Seed/Insert) no Banco:
* **Registro 1:** `descricao: "Dinheiro Balcão"`, `tipo_provedor: "DINHEIRO"`, `codigo_sefaz: "01"`, `tarifa_porcentagem: 0.00`.
* **Registro 2:** `descricao: "Cartão de Crédito - Maquininha Stone"`, `tipo_provedor: "CARTAO_CREDITO"`, `codigo_sefaz: "03"`, `tarifa_porcentagem: 2.99`.
* **Registro 3:** `descricao: "PIX QrCode - Sicredi"`, `tipo_provedor: "PIX"`, `codigo_sefaz: "17"`, `tarifa_porcentagem: 0.00`.

---

## 5. Próximos Passos para Desenvolvimento

1. Criar a migration das tabelas `metodos_pagamento` e `venda_pagamentos`.
2. Criar a tela de cadastro/configuração de Métodos de Pagamento na retaguarda (Dashboard do Administrador).
3. Desenvolver o componente visual de listagem e inserção de pagamentos na tela de vendas.
4. Ajustar a query de fechamento da Venda/OS para verificar se a soma de `venda_pagamentos` bate com o total geral do pedido antes de concluir.