# Especificação Técnica: Módulo de Estoque, Vendas e Requisitos Fiscais (NF-e / NFC-e)

Este documento estabelece os campos obrigatórios, regras de negócio e diretrizes de interface para adequar os módulos de Produtos e Vendas à legislação tributária brasileira, garantindo a emissão de Notas Fiscais (NF-e) e Cupons Fiscais (NFC-e) sem rejeições na SEFAZ.

---

## 1. Dicionário de Dados: Cadastro de Produtos (Estoque)

Para que um produto esteja apto a ser faturado, o banco de dados deve registrar e validar as seguintes propriedades fiscais, além dos dados comerciais existentes.

| Campo | Tipo | Tamanho | Validação / Regra de Negócio |
| :--- | :--- | :--- | :--- |
| `codigo_barras` | String | 8, 12, 13 ou 14 | GTIN/EAN. Se vazio, o sistema deve tratar internamente como `"SEM GTIN"`. |
| `unidade_comercial`| String | 6 | Ex: UN, KG, CX, PC, MT. Sempre em letras maiúsculas. |
| `ncm` | String | 8 | Nomenclatura Comum do Mercosul. Apenas números. Obrigatório. |
| `cest` | String | 7 | Código Especificador da Substituição Tributária. Obrigatório se o NCM possuir ST. |
| `origem_mercadoria`| Integer| 1 | Código de 0 a 8 (Ex: `0` - Nacional, `1` - Importada Direta). |
| `regime_tributario`| Enum | - | `SIMPLES_NACIONAL` ou `REGIME_NORMAL` (Define quais campos abaixo exibir). |
| `csosn` | String | 3 | Obrigatório se Simples Nacional (Ex: `102`, `500`). |
| `cst_icms` | String | 2 | Obrigatório se Regime Normal (Ex: `00`, `10`, `60`). |
| `cst_pis` | String | 2 | Código de Situação Tributária do PIS (Ex: `01`, `49`, `07`). |
| `cst_cofins` | String | 2 | Código de Situação Tributária do COFINS (Ex: `01`, `49`, `07`). |
| `aliquota_ibpt_fed` | Decimal | 5,2 | % Média de tributos Federais (Lei do Imposto na Nota). |
| `aliquota_ibpt_est` | Decimal | 5,2 | % Média de tributos Estaduais. |
| `aliquota_ibpt_mun` | Decimal | 5,2 | % Média de tributos Municipais. |

---

## 2. Dicionário de Dados: Pedido de Venda

O pedido de venda consolida a operação comercial e precisa capturar dados dinâmicos que variam a cada transação (dados que dependem de *para quem*, *como* e *onde* a venda ocorre).

### Cabeçalho do Pedido (`vendas`)
*   **`indicador_presenca` (Integer):** `1` = Presencial, `2` = Internet, `3` = Teleatendimento, `4` = NFC-e com entrega a domicílio.
*   **`modalidade_frete` (Integer):** `0` = CIF (Remetente), `1` = FOB (Destinatário), `9` = Sem Ocorrência de Transporte (Padrão para Balcão/NFC-e).
*   **`forma_pagamento_sefaz` (String):** Código oficial exigido na nota (`01` = Dinheiro, `03` = Cartão de Crédito, `15` = Boleto, `17` = PIX).
*   **Dados do Destinatário (Cliente):** CPF/CNPJ, Inscrição Estadual (ou marcar como Não Contribuinte), Endereço completo estruturado com o **Código do Município IBGE**.

### Itens do Pedido (`itens_venda`)
*   **`cfop` (String - 4 dígitos):** Determina a operação jurídica. *Calculado automaticamente pelo sistema (ver Seção 3).*
*   **`valor_desconto` (Decimal):** Desconto aplicado especificamente àquele item (a SEFAZ exige o desconto por item, não apenas no total).
*   **`valor_tributo_indireto` (Decimal):** Calculado automaticamente multiplicando o valor total do item pelas alíquotas do IBPT (Exigência legal para o rodapé do cupom/nota).

---

## 3. Relacionamento e Regras de Negócio (Estoque vs. Vendas)

Para manter a integridade dos dados e evitar erros humanos de digitação de códigos fiscais, o sistema deve seguir estas três automações de retaguarda:

### A. Herança de Atributos Fiscais
No momento em que um produto é inserido em um Pedido de Venda ou em uma Ordem de Serviço, o item do pedido **herda de forma estática** o `NCM`, `CEST`, `Origem`, `CST/CSOSN` do cadastro do produto naquele exato momento. Isso previne que alterações futuras no cadastro alterem o histórico de notas já emitidas.

### B. Cálculo Automatizado do CFOP
O usuário nunca deve digitar o CFOP. O sistema rodará a seguinte matriz lógica no fechamento da venda:
SE endereço_cliente.UF == endereco_empresa.UF ENTÃO
SE produto.cest ESTÁ PREENCHIDO ENTÃO
cfop = "5.405" (Venda de mercadoria com ST retido anteriormente)
SENÃO
cfop = "5.102" (Venda de mercadoria padrão dentro do Estado)
FIM SE
SENÃO (Venda Interestadual)
SE produto.cest ESTÁ PREENCHIDO ENTÃO
cfop = "6.403"
SENÃO
cfop = "6.102"
FIM SE
FIM SE

### C. Gatilho de Baixa Física e Fiscal
1.  **Venda Balcão (NFC-e):** A baixa do `estoque_atual` e a geração da `movimentacao_estoque` ocorrem imediatamente no ato da confirmação do pagamento.
2.  **Ordem de Serviço (OS):** As peças adicionadas ficam sob o status de **"Reservadas"** (sem alterar o estoque físico disponível para venda de balcão). A baixa definitiva no estoque e a emissão fiscal só ocorrem quando a OS transiciona para o status **"Finalizada"**.

---

## 4. Estratégia de Interface (UX) e Divisão por Seções

A complexidade fiscal deve ficar escondida ou organizada para não assustar o usuário comercial comum. A interface será dividida em zonas de fricção controlada.

### Layout do Cadastro de Produtos (Abas Dinâmicas)
1.  **Aba 1: Dados Gerais (Sem Fricção)**
    *   Campos: Nome, Código Interno, Código de Barras (Leitor), Preço de Custo, Preço de Venda e Categoria.
    *   *Objetivo:* Permitir um cadastro comercial em menos de 30 segundos.
2.  **Aba 2: Controle de Estoque**
    *   Campos: Estoque Atual, Estoque Mínimo, Fornecedor Padrão, Localização Física na Prateleira.
3.  **Aba 3: Dados Fiscais (Fricção Isolada)**
    *   Campos: Origem da Mercadoria, NCM, CEST e as réguas de impostos (CST/CSOSN).
    *   *Mecanismo de UX:* Se a empresa estiver configurada globalmente como Simples Nacional, os campos de Regime Normal (como IPI ou CSTs complexos de ICMS) ficam **ocultos**, exibindo apenas o CSOSN.
    *   *Dica de Automação:* Incluir um botão "Importar dados via XML de Compra", que lê um arquivo `.xml` do fornecedor e preenche toda essa Aba 3 automaticamente.

### Layout do Fluxo de Venda (PDV Simplificado)
*   **Visão do Operador:** O operador de caixa apenas visualiza o Produto, Quantidade, Preço e a Forma de Pagamento (PIX, Cartão, Dinheiro).
*   **Ocultação Fiscal:** Campos como CFOP, Alíquotas de ICMS e cálculos do IBPT rodam em segundo plano (background) e só aparecem se o operador clicar em um botão expandível de "Detalhes Fiscais do Item".
*   **Tratamento de Erros Amigável:** Se a SEFAZ rejeitar a nota por um NCM inválido, o sistema não deve exibir o erro bruto em XML. Deve exibir um alerta legível: *"Não foi possível emitir a nota: O NCM do produto 'X' está incorreto ou desatualizado. Por favor, corrija o cadastro do produto ou consulte sua contabilidade."*