# Gestão de Serviços PWA

Uma aplicação fullstack desenvolvida em Django para gestão de equipes externas, orçamentos, execução de serviços e integração com a API do WhatsApp. A aplicação é um Progressive Web App (PWA) projetado para rodar em dispositivos móveis como se fosse um app nativo.

## 🚀 Tecnologias Utilizadas

- **Backend:** Django (Python)
- **Frontend:** Django Templates + Tailwind CSS
- **PWA:** `django-pwa` para instalação em dispositivos móveis
- **Banco de Dados:** SQLite (Desenvolvimento) / PostgreSQL (Produção sugerido)
- **Mensageria:** Integração com API do WhatsApp (Cloud API ou similar)
- **Arquivos:** Gestão de fotos e vídeos para evidências

## 🛠️ Principais Módulos e Funcionalidades

### 1. Gestão de Clientes e Imóveis
- Cadastro de clientes.
- Vínculo de múltiplos imóveis por cliente (Localização via GPS/Maps).

### 2. Fluxo de Serviço (Ciclo de Vida)
- **Vistoria:** Colaborador visita o local e coleta evidências (fotos/vídeos).
- **Orçamento:** Adição de serviços e valores.
- **Aprovação via WhatsApp:** O cliente recebe um link/botão para aprovar o orçamento.
- **Execução:** Colaboradores têm acesso a fotos, vídeos e localização (sem ver valores).
- **Finalização:** Coleta de evidências pós-serviço e mudança de status.
- **Garantia:** Possibilidade de reabertura de ordens finalizadas.

### 3. Comunicação Automática
- Notificações de status via WhatsApp.
- Solicitação de pagamento automática após finalização.

## 👥 Papéis de Usuário (Roles)
- **Admin:** Visão total (financeiro, equipes, clientes).
- **Colaborador:** Acesso operacional (vistorias, execuções, localização, evidências).

## 📸 Gestão de Mídias
A aplicação gerencia o upload e exibição de fotos e vídeos como prova técnica do serviço realizado, garantindo transparência tanto para a empresa quanto para o cliente.
