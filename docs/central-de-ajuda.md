# Central de Ajuda — desenvolvimento e operação

## Regra de entrega

A pedido do responsável pelo sistema, toda implementação que alterar o uso pelo cliente deve revisar e atualizar a Central de Ajuda na mesma entrega. Isso inclui novos módulos, mudanças de botões, permissões, regras de negócio e correções que mudem procedimentos. Mudanças exclusivamente internas podem dispensar novo texto, desde que a ausência de impacto no uso seja registrada na entrega.

A orientação deve ser visual: passos curtos acompanhados de prints reais anotados, com dados de demonstração. Não basta criar campos de upload e deixar todos os guias apenas em texto. Quando uma tela mudar, revisar também a captura, a marcação de onde clicar e a descrição acessível.

## Estrutura

- `ajuda/models.py`: categorias, artigos, passos com imagens e telas relacionadas.
- `ajuda/access.py`: filtro único de publicação, público e módulo.
- `ajuda/initial_content.py`: guias oficiais versionados junto do código.
- `ajuda/management/commands/sync_help_content.py`: sincronização conservadora.
- `templates/ajuda/`: central, categorias, leitura e ajuda contextual.
- `ajuda/templatetags/ajuda_tags.py`: ajuda da tela por `resolver_match.view_name`.
- `/ajuda/contexto/?screen=<view_name>` e `static/js/help-context.js`: consulta contextual autenticada, online e sem cache. O HTML operacional contém apenas um controle genérico, nunca títulos ou resumos editoriais.

## Publicação

1. Aplicar migrações: `python manage.py migrate`.
2. Sincronizar os guias: `python manage.py sync_help_content`.
3. Conferir o estado: `python manage.py sync_help_content --check`.
4. Revisar os artigos na interface `/ajuda/` com os perfis afetados.

O `entrypoint.sh` do Docker executa a sincronização depois das migrações e antes do collectstatic. Edições locais continuam preservadas; conflitos são registrados no log, sem impedir a leitura dos demais guias. Em desenvolvimento fora do Docker, execute o comando manualmente.

O sincronizador não é um editor irrestrito: preserva conteúdo alterado manualmente e sinaliza conflitos. Resolva cada conflito revisando o artigo e a fonte versionada. Não apague edições locais nem use atualizações em massa para contornar a proteção. Vídeos e imagens reais devem ser adicionados por um editor autorizado; nunca invente gravações ou capturas.

## Checklist por mudança

- Conferir nomes e ações diretamente nos templates, views e regras atuais.
- Atualizar objetivo, pré-requisitos, passos, resultado esperado e cuidados do guia.
- Ajustar vínculos das telas usando nomes exatos de rotas, com namespace quando existir.
- Conferir público e módulo. O acesso é validado no servidor, não apenas no menu.
- Usar dados fictícios nas imagens. Não expor clientes, credenciais ou dados de cobrança reais.
- Rodar `DEBUG=True python manage.py test ajuda --settings=core.test_settings --noinput`.
- Rodar `DEBUG=True python manage.py makemigrations --check --dry-run --settings=core.test_settings` e `npm run build`.
- Em banco de validação populado, executar `sync_help_content --check`.

`core.test_settings` usa SQLite em memória e armazenamento de arquivos em memória. Os testes não devem consultar nem modificar o banco do cliente ou integrar com serviços externos.

Para o smoke de navegador reproduzível: `HELP_BROWSER_TESTS=1 DEBUG=True python manage.py test ajuda --settings=core.test_settings --noinput`. Ele inicia servidor e sessões de teste isolados, usa Chromium via Playwright do Node e cobre desktop/mobile, busca, paginação, bloqueio de links diretos e expansão contextual por teclado. CDNs são isolados nesse smoke; reprodução de vídeo externo não é exercitada. O bloqueio de cache da ajuda é exercitado separadamente no manipulador real do service worker com Node.

## Administração e segurança

Gerenciar documentação exige usuário com acesso ao Django Admin e permissões de `ajuda`, separadas das permissões dos módulos operacionais. A permissão de alterar artigos também permite editar seus passos e vínculos no mesmo formulário. Criar categorias exige a permissão correspondente.

Artigos começam em rascunho. Só artigos publicados e autorizados aparecem na busca, nas sugestões e nos links diretos. Edição no Admin não concede acesso de leitura a módulos de negócio aos quais o editor não tem acesso.

O conteúdo é texto simples com escape automático, não HTML livre. Vídeos aceitam links HTTPS de YouTube ou Vimeo, convertidos em endereços de incorporação confiáveis. O controle de acesso do provedor externo continua sendo necessário se o vídeo for restrito. Imagens em armazenamento público também não são arquivos confidenciais.

Os prints oficiais são distribuídos em `static/help/screenshots/`, sem upload para serviços externos. `ArticleStep.screenshot` permite apenas caminhos WebP desse diretório. A imagem enviada pelo editor continua tendo prioridade; sua presença impede o sincronizador de sobrescrever o artigo. A migração do hash anterior só é aceita quando todos os campos editoriais antigos ainda correspondem ao hash instalado, preservando alterações locais.

A Central de Ajuda nesta versão exige conexão. Suas rotas não são guardadas pelo service worker nem pelo cache HTTP. Isso evita que um perfil consulte guias de outro perfil pelo cache do aplicativo. Não alterar o funcionamento das filas offline do técnico para adicionar ajuda.

O bypass abrange `/ajuda` e `/ajuda/`. Respostas redirecionadas, destinadas à ajuda ou com `Cache-Control: no-store` também não entram no cache. A versão v9 limpa os shells antigos do CacheStorage sem apagar IndexedDB ou filas pendentes. Os títulos contextuais só chegam por fetch autenticado quando o painel é aberto; fechar, sair da página ou ficar offline limpa o painel. Não voltar a renderizar títulos de guias dentro de páginas operacionais cacheáveis.

## Escala e próximos passos

A busca normaliza acentos e pesquisa artigos e passos autorizados, em lotes, sem dependência externa. Para catálogos muito grandes, substituir `ajuda/search.py` por um índice full-text mantendo o filtro de acesso.

Avaliações de utilidade, métricas de buscas sem resultado, trilhas com progresso e conteúdo offline selecionado são evoluções futuras; não fazem parte desta primeira versão.
