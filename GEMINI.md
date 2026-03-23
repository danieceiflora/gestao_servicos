# ♊ GEMINI.md - Gestão de Serviços PWA

Este arquivo serve como o guia de contexto central para o Gemini CLI (agente de IA) atuar de forma eficiente e alinhada às diretrizes deste projeto.

## 🚀 Visão Geral do Projeto

A **Gestão de Serviços PWA** é uma plataforma fullstack desenvolvida em Django, focada na gestão operacional de equipes externas. Ela permite o acompanhamento completo do ciclo de vida de um serviço, desde a vistoria inicial até a finalização com coleta de evidências (fotos/vídeos), incluindo aprovação de orçamentos via integração com WhatsApp.

### 🛠️ Core Tech Stack
- **Backend:** Django 6.0 (Python)
- **Frontend:** Django Templates + Tailwind CSS v4
- **PWA:** `django-pwa` (instalável como app nativo)
- **Banco de Dados:** SQLite (Desenvolvimento: `db_v2.sqlite3`) / PostgreSQL (Produção)
- **Design System:** Inspirado em `shadcn/ui` (minimalista, funcional, profissional)

---

## 📂 Estrutura e Arquitetura

- **`core/`**: Configurações centrais do projeto Django (`settings.py`, `urls.py`).
- **`services/`**: App principal contendo toda a lógica de negócio.
    - `models.py`: Definições de Usuários (Custom User), Clientes, Imóveis, Profissionais e Ordens de Serviço (OS).
    - `views.py`: Lógica de controle e renderização.
    - `forms.py`: Formulários para entrada de dados.
    - `utils.py`: Funções auxiliares.
- **`templates/`**: Estrutura de HTML organizada por módulos (`clients`, `orders`, `professionals`).
- **`static/`**:
    - `src/input.css`: Fonte do Tailwind.
    - `dist/output.css`: Arquivo gerado para produção.
    - `js/serviceworker.js`: Lógica de PWA e Cache.
- **`media/`**: Armazenamento de evidências de serviço (fotos/vídeos).

---

## 🛠️ Comandos Comuns

### Backend (Django)
```bash
# Iniciar o servidor de desenvolvimento
python manage.py runserver

# Criar migrações
python manage.py makemigrations

# Aplicar migrações
python manage.py migrate

# Criar superusuário
python manage.py createsuperuser

# Executar testes
python manage.py test
```

### Frontend (Tailwind CSS v4)
```bash
# Build do CSS (Executar após alterações no HTML/CSS)
npm run build

# Watch mode para desenvolvimento
npm run watch
```

---

## 📏 Convenções de Desenvolvimento

### ⚙️ Backend (Django Specialist)
1.  **Models:** Sempre use `UUIDField` para IDs de modelos que serão expostos publicamente (ex: `ServiceOrder`).
2.  **Naming:** Campos `ForeignKey` devem ter `related_name` explícito. Use `verbose_name` em Português (pt-BR).
3.  **Lógica:** Isole integrações externas (como WhatsApp) em camadas de serviço ou utilitários para manter as views limpas.
4.  **Localização:** O projeto está configurado para `America/Sao_Paulo` e `pt-br`.

### 🎨 Front-end (UI/UX)
1.  **Estilo:** Siga o padrão `shadcn`: fundo limpo (`#f9fafb`), bordas `rounded-lg`, sombras `shadow-sm`, tipografia legível.
2.  **Responsividade:** O foco é Mobile-First (PWA). Garanta que botões tenham áreas de toque de no mínimo 44x44px.
3.  **Feedback:** Use estados de carregamento e feedback visual para todas as ações do usuário.
4.  **Componentização:** Utilize `{% include %}` para componentes reutilizáveis em `templates/services/components/`.

---

## 🤖 Contexto para o Agente Gemini
Ao atuar neste projeto, comporte-se como um **Especialista em Django e IHC**. Priorize a segurança dos dados, a experiência do usuário em dispositivos móveis e a manutenibilidade do código. Sempre que modificar o frontend, lembre-se de que o Tailwind CSS v4 requer um build para refletir mudanças no `output.css`.
