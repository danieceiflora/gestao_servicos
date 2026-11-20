# Validação da Central de Ajuda

## Resultado

- 51 testes do módulo passaram, incluindo o smoke Chromium habilitado.
- Chromium exercitou 18 combinações de página/perfil/largura, com gestor e colaborador, em 320, 390 e 1440 px. Nenhum overflow horizontal nas páginas verificadas.
- Busca por texto sem acentos, retenção do filtro, limpeza, estado vazio de vídeos, paginação, links restritos e abertura contextual por teclado passaram.
- Troca de sessão no mesmo shell do aplicativo e remoção dos títulos contextuais ao ficar offline passaram em Chromium. Testes do service worker real em Node verificaram bypass com/sem barra, recusa de redirecionamentos/no-store, ausência de replay da ajuda por alias e limpeza de caches antigos sem acesso destrutivo ao IndexedDB.
- Django `check`: sem problemas. Migrações: nenhuma alteração pendente nos modelos.
- `npm run build`, `node --check tests/help_smoke.cjs`, `bash -n entrypoint.sh` e `git diff --check`: passaram.
- Sincronização local: 21 guias oficiais verificados por `sync_help_content --check`, sem conflito nem atualização pendente.
- Revisão independente das correções de isolamento do cache aprovada, sem problemas de segurança ou lógica no escopo revisado. Foram conferidos bypass de ajuda, recusa de respostas sensíveis, shell genérico, autorização contextual e limpeza de conteúdo temporário.

## Regressão geral

A execução dos apps `services integracoes pagamentos fiscal producao ajuda`, com banco isolado e Chromium habilitado, executou 489 testes e encontrou duas falhas:

1. `services.tests.PublicPolicyPagesTests.test_terms_identify_configured_integrator`: nome da integradora não aparece como esperado nos termos.
2. `services.tests_billing_list.BillingListTests.test_discount_deadline_is_shown_on_desktop_and_mobile`: uma ocorrência do vencimento com desconto, enquanto o teste espera duas.

As duas falhas foram reproduzidas em uma extração isolada do código de `HEAD`, anterior às alterações da Central de Ajuda, usando as mesmas configurações de teste. Nenhuma delas foi corrigida neste escopo.

## Limites da validação

- Testes usam SQLite em memória, armazenamento em memória e usuários de teste. O banco do cliente não é usado para testes.
- O banco SQLite local de desenvolvimento recebeu somente as migrações e os guias da ajuda; não houve implantação em produção.
- O smoke de navegação isola CDNs e substitui apenas a inicialização dos ícones; não testa a disponibilidade de fontes, ícones externos ou provedores de vídeo. O navegador representa um ambiente sem service worker; a lógica real de bypass de cache é exercitada separadamente por Node.
- Não há vídeos nem capturas de procedimentos inventados. Gravações e imagens de treinamento precisam ser produzidas e adicionadas por editor autorizado.
- A ajuda contextual do técnico foi verificada sem executar atendimento real nem filas offline. O aplicativo operacional não faz parte deste smoke.
- Guias foram revisados contra código e interface disponível; a homologação dos procedimentos por quem opera o negócio continua recomendada.

## Reprodução

`HELP_BROWSER_TESTS=1 DEBUG=True python manage.py test ajuda --settings=core.test_settings --noinput`

`HELP_BROWSER_TESTS=1 DEBUG=True python manage.py test services integracoes pagamentos fiscal producao ajuda --settings=core.test_settings --noinput`

`python manage.py sync_help_content --check`

O interpretador deve ter as dependências do projeto. Chromium e Playwright do Node devem estar instalados para o smoke. Não use pip vinculado a outra versão de Python.
