# AGENTS.md

Guia compacto de operação. O modelo de OS por etapas, financeiro, app offline do técnico e integrações estão detalhados em `CLAUDE.md` — leia-o antes de mexer nesses domínios.

## Comandos

- Dev server: `python manage.py runserver` — **requer `DEBUG=True` no `.env`**. `core/settings.py:20` usa `DEBUG=False` por padrão; sem isso tenta Postgres via `DATABASE_URL` e o servidor não sobe.
- Migrações: `python manage.py makemigrations` + `python manage.py migrate`. Rodar `python manage.py check` após mudanças em models.
- Tailwind: `npm run watch` (dev) / `npm run build` → gera `static/dist/output.css` via Tailwind CLI v4. Editar o fonte em `static/src/input.css`.
- Management commands: `run_scheduler` (scheduler APScheduler, `integracoes`), `process_media_queue` (processamento de mídia), `send_collection_reminders`, `send_scheduled_reminders`, `generate_recurring_expenses`.

## Stack e estrutura

- Settings em `core/settings.py` (`DJANGO_SETTINGS_MODULE=core.settings`). `AUTH_USER_MODEL = services.User`.
- Apps instalados: `services` (app principal — models centralizados; views divididas por domínio: `views_equipe`, `views_finance`, `views_offline`, `views_stock`, `views_bi`, `views_maintenance`), `integracoes` (`SystemConfig`, Chatwoot, scheduler), `pagamentos` (Asaas), `fiscal` (NFSe Asaas/Base ERP).
- `tenants/` existe no repo mas **não** é app instalado nem referenciado em settings — é resquício; ignore (idem a dependência `django-tenants`).
- Dev usa SQLite `db_v2.sqlite3` (só quando `DEBUG=True`); prod usa Postgres via `DATABASE_URL` (ver `docker-compose.yml`). `USE_TZ = DEBUG` → UTC em dev, `America/Sao_Paulo` em prod.
- Produção (docker-compose): `web` (porta 8001), `media_worker` (`process_media_queue`), `scheduler` (`run_scheduler`), `nginx`, `certbot`.

## Testes

- Não há testes Django unitários/de integração ativos. Só E2E Playwright em `tests/e2e/*.spec.js`.
- Os specs usam `@playwright/test`, que **não está** em `package.json`/`node_modules` — instalar (`npm i -D @playwright/test`) antes de rodar `npx playwright test`.
- `playwright.config.js` inicia `python manage.py runserver` na porta 8000 automaticamente; exige DB populado com credenciais de teste (ver `tests/pages/LoginPage.js`). Rodar o servidor em outra máquina/container não funciona — os testes são locais.

## Pitfalls críticos (detalhes no CLAUDE.md)

- Ocorrência: usar `OccurrenceCategory.GERAL` e `OccurrenceType.OUTRO` — **nunca** `GENERAL`/`OTHER`.
- `ServiceOrderTask.save(update_fields=[...])` já dispara `update_status()` — não chamar manualmente em seguida (double-trigger).
- `ServiceOrder.total_value` e a baixa de estoque excluem itens de ORCAMENTO quando existem etapas EXECUCAO/GARANTIA (anti-soma-dupla). Sempre verificar `stock_lowered` antes de qualquer lógica de estoque manual.
- Chatwoot botão CTA: usar o formato próprio `{"type":"url","parameter":"<sufixo>"}` em `integracoes/chatwoot_client.py` (`send_template`) — a estrutura da Meta API nativa (`index`/`sub_type`/`parameters[]`) não funciona.
- Upload de mídia: sempre anexar filename com extensão (`formData.append('file', blob, 'upload.jpg')`); o upload cria `MediaProcessingJob` (PENDENTE) processado assíncrono por `process_media_queue`.
- `Http404` dentro de `try/except Exception` vira 400 — preferir `.filter().first()` com checagem explícita.

## Ambiente

- `.env` carrega segredos: `ASAAS_API_KEY`/`ASAAS_CLIENT_API_KEY`, `BASEERP_API_KEY`, credenciais R2 (`R2_*`, media no Cloudflare R2 quando preenchidas), `VAPID_*` (push), `WEBHOOK_SHARED_SECRET` (Chatwoot). Não commitar `.env`.