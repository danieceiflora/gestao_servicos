# CLAUDE.md — Instruções do Projeto

## Autonomia de Execução

Quando uma implementação for planejada e acordada com o usuário (via conversa ou documento `.md` de estratégia), prossiga com todas as fases **sem pedir confirmação a cada etapa**. Execute o plano completo e informe o progresso ao longo do caminho. Só interrompa para confirmar se encontrar uma decisão genuinamente ambígua ou destrutiva (ex: apagar dados, força em branch protegida).

## Stack do Projeto

- **Backend:** Django (Python)
- **Frontend:** Django Template Language + Tailwind CSS + shadcn/ui patterns + HTMX
- **Banco:** SQLite (desenvolvimento) / PostgreSQL (produção)
- **Tarefas assíncronas:** Management commands agendados via cron (ou Celery Beat se disponível)

## Convenções do Projeto

- Modelos financeiros ficam em `services/models.py` na seção `# --- CONTAS A PAGAR ---`
- Views financeiras ficam em `services/views_finance.py`
- Templates financeiros ficam em `templates/services/finance/`
- Partials HTMX ficam em `templates/services/partials/`
- URLs registradas em `services/urls.py`
