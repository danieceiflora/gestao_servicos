# Design system da aplicação

Este projeto usa Django Templates, Tailwind CSS v4 e ícones Lucide. Telas novas devem reutilizar as classes `ui-*` de `static/src/input.css` e os partials de `templates/components/ui/` antes de criar combinações locais.

## Princípios

- Fundo da aplicação em tons claros; superfícies principais brancas.
- Bordas `slate-200`, sombras discretas e raio `rounded-2xl` em cards.
- Texto principal `slate-900`, secundário `slate-500` e rótulos pequenos em caixa alta.
- Verde significa sucesso/aberto, âmbar exige atenção, vermelho representa erro/divergência e azul comunica informação.
- Ações destrutivas precisam de confirmação e nunca devem depender apenas da cor.
- Toda tela deve funcionar em 360 px sem rolagem horizontal do layout principal.

## Componentes

- Cabeçalho: `ui-page-header`, `ui-page-title-group`, `ui-page-icon`, `ui-page-title`, `ui-page-subtitle`.
- Cards: `ui-card`, `ui-card-header`, `ui-card-title`, `ui-card-subtitle`.
- Botões: `ui-button` combinado com `ui-button-primary`, `ui-button-secondary`, `ui-button-success` ou `ui-button-danger`.
- Formulários: `ui-label` e `ui-input`.
- Status: `ui-badge` mais uma cor semântica.
- Tabelas: `ui-table`, sempre dentro de um contêiner com `overflow-x-auto`.
- Estado vazio: partial `components/ui/empty_state.html`.

## Partials DTL

```django
{% include 'components/ui/page_header.html' with title='Título' subtitle='Descrição' icon='landmark' back_url=back_url back_label='Voltar' %}
{% include 'components/ui/session_status_badge.html' with status=session.status label=session.get_status_display %}
{% include 'components/ui/metric_card.html' with label='Caixas abertos' value=stats.open icon='door-open' tone='emerald' %}
```

Partials devem receber apenas dados de apresentação. Regras de permissão, totais e estados pertencem às views/models.

## Responsividade

- Cabeçalhos empilham ações no mobile.
- Tabelas administrativas importantes devem possuir uma representação em cards no mobile.
- Campos interativos mantêm altura mínima de 40 px; ações principais, preferencialmente 44 px.
- Diálogos usam `fixed inset-0 m-auto`, largura limitada pela viewport e rolagem interna.

## Checklist para telas novas

1. Há cabeçalho, estado vazio e feedback das ações?
2. Status possuem texto e cor semântica?
3. A tela é operável por teclado e em 360 px?
4. Botões destrutivos pedem confirmação?
5. O padrão já existe como classe `ui-*` ou partial reutilizável?
