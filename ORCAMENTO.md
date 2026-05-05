# Plano de Ação: Envio de Orçamento, Configurações de Empresa e Integração Chatwoot

Este documento detalha a estratégia e os passos para centralizar as configurações da empresa, criar um gerador de PDF nativo focado no cliente (ocultando valores unitários) e construir um integrador transacional com o Chatwoot via WhatsApp.

## 1. Configuração Global (Company & Chatwoot API) ✅ **(CONCLUÍDO)**

Foi criado um modelo exclusivo no painel de administração (`integracoes.SystemConfig`) projetado para funcionar como um Singleton (apenas 1 registro no banco de dados).

**Campos adicionados:**
- **Dados da Empresa (para o PDF):** Razão Social/Nome Fantasia, CNPJ, Endereço, Site, Telefone de Contato e Logo (Upload de Imagem).
- **Configurações do Chatwoot:** Base URL (padrão: `https://app.chatwoot.com`), Account ID, Inbox ID, User API Access Token e Nome do Template de Orçamento.

*Ações realizadas:*
- `Pillow` instalado para suporte a upload de imagens (`ImageField`).
- `reportlab` instalado para criação futura dos PDFs.
- Modelo `SystemConfig` em `integracoes/models.py`.
- Formato de Singleton restrito configurado em `integracoes/admin.py`.
- Migrações do banco aplicadas com sucesso.

## 2. Geração do Orçamento em PDF ⏳ *(Pendente)*

Processo de geração usando a biblioteca `reportlab` (especificamente a engine do Platypus - *SimpleDocTemplate*) para criar PDFs eficientes e nativos sem depender de renderizadores HTML externos.

**Estrutura do Documento:**
1. **Cabeçalho:** Logotipo, Nome da Empresa, CNPJ e Endereço da Empresa capturados do `SystemConfig`.
2. **Dados do Cliente:** Nome do cliente, telefone, e endereço do local do serviço.
3. **Escopo do Orçamento:** Descrição geral do problema.
4. **Tabela de Itens:** Lista focada no cliente com colunas para **Descrição do Item** e **Quantidade** (Os *preços unitários e valores de itens/mão de obra não são detalhados*, conforme solicitação).
5. **Rodapé/Resumo:** Exibição da "Observação para o Cliente" em destaque, seguido pelo **Valor Estimado Total da OS**.

*Ações necessárias:*
- [ ] Criar o utilitário base `services/utils/pdf_generator.py`.
- [ ] Criar a view de visualização/download de PDF (`/orders/<uuid>/pdf/`).
- [ ] Inserir o botão "Baixar/Visualizar PDF" na visualização detalhada da OS (`order_detail.html`).

## 3. Integração Chatwoot ⏳ *(Pendente)*

Módulo de cliente API REST `chatwoot_client.py` que orquestrará a comunicação entre o Gestão de Serviços e a API do Chatwoot.

**Fluxo Funcional:**
1. **Identify:** Buscar o Contato no Chatwoot utilizando o número de telefone (se não existir, invocar endpoint de criação usando nome e telefone).
2. **Conversation:** Garantir a existência de uma conversa transacional associada à meta/inbox selecionada.
3. **Attach PDF:** Gerar o PDF na memória e convertê-lo para formato compatível em anexo via API (`/messages`).
4. **Send Template:** Disparar o Template HSM (Template oficial) aprovado, vinculando o Orçamento para notificar o cliente via WhatsApp de forma ativa.

*Ações necessárias:*
- [ ] Desenvolver `integracoes/chatwoot_client.py` implementando métodos GET/POST de Contatos, Conversas e Mensagens.
- [ ] Criar uma task/view responsável por executar esse fluxo com tratamento de erros (try/except) e timeout.

## 4. Interface da OS (Integração) ⏳ *(Pendente)*

Fazer o binding de todo o backend construído com o Frontend que o operador/vendedor usa no dia a dia.

*Ações necessárias:*
- [ ] Substituir o botão genérico ("Enviar Orçamento") na `order_detail.html` para de fato invocar a rota que gera o PDF e o anexa ao disparo do Chatwoot.
- [ ] Adicionar feedaback assíncrono (Toast/Messages ou modal Loading) garantindo que a tela não precise ser pesadamente recarregada e apresentando notificação amigável de Sucesso/Erro no envio.