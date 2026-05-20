# Plano de Ação — Sincronização e Compressão de Mídias (Fotos e Vídeos)

## Objetivo
Implementar uma rota de sincronização que comprima mídias antes do envio ao bucket, reduzindo tamanho sem perda perceptível de qualidade e mantendo o fluxo offline-first do PWA.

## Estado Atual (resumo)
- O PWA armazena blobs no IndexedDB e enfileira `MEDIA_UPLOAD` para sincronização.
- A rota `POST /api/tecnico/etapa/<uuid>/upload-media/` (services/views_offline.py: api_tecnico_upload_media) salva o arquivo diretamente em `ServiceMedia` ou `ChecklistResponseMedia`.

## Estratégia Proposta (alto nível)
1. A rota recebe o arquivo e salva em arquivo temporário.
2. Identifica o tipo (imagem ou vídeo) e aplica compressão.
3. Envia a mídia processada ao bucket da nuvem.
4. Persiste o registro com o arquivo final processado.

## Plano de Ação
### 1) Decisões e Requisitos
- Definir o provedor de bucket (S3/R2/GCS/MinIO) e a biblioteca de upload (ex: django-storages + boto3).
- Definir limites de entrada: tamanho máximo, duração máxima (vídeo), dimensões máximas (foto).
- Definir padrões de qualidade: CRF/preset para vídeo, formato/qualidade para foto.
- Decidir se mantém original ou apenas a versão processada.

### 2) Infraestrutura e Dependências
- Garantir `ffmpeg` disponível no ambiente (Dockerfile/servidor).
- Confirmar biblioteca de imagem (Pillow) e versionamento.
- Validar configurações de storage e credenciais do bucket.

### 3) Pipeline de Processamento no Backend
- Criar helpers (ex: `services/utils_media.py`) para processamento isolado.
- Vídeos: transcodificar para H.264 (libx264) + AAC, com CRF e preset definidos, limitar resolução e habilitar `faststart`.
- Fotos: redimensionar para um máximo de pixels, converter para JPEG ou WebP com qualidade definida e otimização.
- Validar MIME real do arquivo e rejeitar tipos não suportados.
- Limpar arquivos temporários sempre, inclusive em erro.

### 4) Integração com a Rota de Upload
- Alterar `api_tecnico_upload_media` para usar o pipeline de processamento.
- Somente criar o registro no banco após upload do arquivo processado.
- Manter resposta compatível com o frontend (success, media_id, type).
- Retornar erro claro quando o processamento falhar (sem fallback silencioso).

### 5) Ajustes no PWA (opcional, mas recomendado)
- Enviar metadados no FormData (mime, tamanho, duração, dimensões).
- Implementar compressão leve no cliente para fotos (canvas) quando possível, mantendo a compressão final no servidor.

### 6) Observabilidade e Testes
- Logar tempo de processamento, tamanho antes/depois e falhas.
- Testes unitários dos helpers (foto e vídeo) e teste de integração da rota.

### 7) Rollout e Segurança
- Possível feature flag para ativar compressão por tipo de mídia.
- Garantir validação de permissões e origem do arquivo.

## Critérios de Pronto
- Uploads retornam 200 e a mídia final está no bucket com tamanho reduzido.
- Fotos e vídeos mantêm qualidade aceitável segundo as configurações definidas.
- Erros de processamento retornam resposta clara e não gravam registro inválido.
