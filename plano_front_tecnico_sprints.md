# Plano de Implementação --- Frontend do Painel Técnico Offline-First

## 🎯 Objetivo

Implementar o frontend do painel do técnico com foco em:

-   uso em campo
-   mobile-first
-   offline-first
-   baixa carga cognitiva
-   workflow guiado
-   sincronização posterior
-   captura eficiente de mídia

O técnico deve enxergar o sistema como um app operacional.

------------------------------------------------------------------------

# 🧭 Fluxo de UX Definido

## Estado 1 --- Não iniciada

Exibir apenas:

-   dados da OS
-   cliente
-   endereço
-   observações
-   contato
-   mapa (quando disponível)

CTA principal:

INICIAR SERVIÇO

Sem exibir:

-   checklist
-   assinatura
-   pagamento
-   conclusão

------------------------------------------------------------------------

## Estado 2 --- Em execução

Após iniciar:

-   registrar início
-   liberar workflow

Fluxo:

1 Dados\
2 Checklist\
3 Ocorrências\
4 Evidências\
5 Conclusão\
6 Assinatura\
7 Pagamento\
8 Finalização

Baseado em:

-   cards
-   accordion
-   workflow progressivo

Evitar:

-   múltiplos modais
-   menus profundos

------------------------------------------------------------------------

# 🏗️ Arquitetura do Front

## App Shell

Template:

templates/services/equipe/offline_app.html

Funcionamento:

-   Django entrega shell
-   JS controla fluxo
-   IndexedDB fornece dados

Mini SPA:

App Shell + Client Driven UI

------------------------------------------------------------------------

# Sprint 1 --- Estrutura Visual Base

## Objetivo

Criar shell e navegação básica.

## Implementar

-   offline_app.html
-   lista OS
-   workspace
-   header
-   cards

Navegação:

Lista ↔ Workspace

Sem reload.

UI:

-   mobile-first
-   Tailwind/shadcn
-   safe-area mobile

------------------------------------------------------------------------

# Sprint 2 --- IndexedDB + Renderização

## Objetivo

Renderizar via IndexedDB.

Implementar:

-   offline-app.js
-   store manager
-   render local

Fluxo:

Bootstrap → IndexedDB → Render

Adicionar:

-   online/offline
-   pendências sync

------------------------------------------------------------------------

# Sprint 3 --- Workflow da OS

## Não iniciada

Mostrar:

-   dados
-   observações
-   mapa

Botão:

INICIAR SERVIÇO

Salvar:

-   local
-   queue

------------------------------------------------------------------------

## Em execução

Liberar:

-   cards
-   progresso

Checklist:

-   OK
-   N/A
-   Problema

Salvar:

local + queue.

------------------------------------------------------------------------

# Sprint 4 --- Ocorrências + Evidências

## Ocorrências

Card dedicado.

Fluxo:

Ocorrência → descrição → mídias → salvar

Usar:

-   bottom sheet
-   página leve

Evitar modal clássico.

------------------------------------------------------------------------

# Sprint 5 --- Captura de Fotos (Camera Live)

## Objetivo

Captura rápida e contínua.

Usar:

getUserMedia()

Fluxo:

Abrir câmera\
↓\
Preview ao vivo\
↓\
Tirar várias fotos\
↓\
Preview grid\
↓\
Salvar lote

Sem fechar câmera.

Implementar:

-   câmera traseira
-   preview
-   múltiplas fotos
-   remover
-   confirmar lote

Salvar:

Blob no IndexedDB.

------------------------------------------------------------------------

# Sprint 6 --- Vídeos

## Objetivo

Vídeos leves.

Decisão:

usar câmera do celular.

HTML:

input type=file accept=video/\* capture

Fluxo:

Abrir câmera sistema\
↓\
Gravar vídeo\
↓\
Retorna app\
↓\
Salvar local

Um vídeo por vez.

Store:

media

Separada da OS.

------------------------------------------------------------------------

# Sprint 7 --- Conclusão + Assinatura + Pagamento

## Conclusão

Campos:

-   resumo
-   pendências
-   observações

------------------------------------------------------------------------

## Assinatura

Tela dedicada.

Canvas grande.

Fluxo:

Assinar → Preview → Confirmar

Salvar:

PNG Blob.

------------------------------------------------------------------------

## Pagamento

Mostrar apenas:

quando OS permitir.

Métodos:

-   dinheiro
-   cartão
-   pix

Campos condicionais.

------------------------------------------------------------------------

# Sprint 8 --- Finalização

Validar:

-   checklist
-   assinatura
-   obrigatórios
-   pendências

Resumo:

-   início
-   fim
-   mídias
-   pagamento

Botão:

FINALIZAR OS

Salvar:

local + queue.

------------------------------------------------------------------------

# Sprint 9 --- UX Final

Implementar:

-   skeleton loading
-   feedback sync
-   retry visual
-   badges
-   empty states

Indicadores:

-   online
-   offline
-   sincronizando
-   erro

------------------------------------------------------------------------

# ✅ Resultado Esperado

App capaz de:

-   operar offline
-   tirar várias fotos sem fechar câmera
-   anexar vídeos leves
-   registrar ocorrências
-   coletar assinatura
-   registrar pagamento
-   finalizar OS
-   sincronizar depois
