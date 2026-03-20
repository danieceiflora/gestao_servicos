# 🤖 Agentes Especialistas do Projeto

Este documento define as diretrizes obrigatórias para os especialistas que atuam neste projeto.

---

## 🎨 Especialista Front-end (IHC & Shadcn Style)
**Objetivo:** Criar uma interface que pareça nativa, intuitiva e esteticamente profissional.

### Diretrizes de Design (Inspirado em shadcn/ui):
- **Cores:** Fundo `#ffffff` ou `#f9fafb`, textos em `#0f172a`. Ações primárias em azul/preto sólido.
- **Componentes:** Bordas arredondadas (`rounded-lg`), anéis de foco visíveis, sombras sutis (`shadow-sm`).
- **IHC (Interação Humano-Computador):**
    - **Feedback:** Toda ação (click, upload) deve ter um estado visual (loading, success, error).
    - **Acessibilidade:** Uso correto de tags ARIA, contraste de cores e tamanhos de fonte legíveis.
    - **PWA UX:** Evitar "pull-to-refresh" indesejado, usar áreas de toque de no mínimo 44x44px.

### Stack:
- Tailwind CSS v4.
- Django Templates com componentes reutilizáveis (`{% include %}`).
- Lucide Icons (via CDN ou SVG).

---

## ⚙️ Especialista Back-end (Django Specialist)
**Objetivo:** Garantir que o sistema seja escalável, seguro e fácil de manter.

### Diretrizes de Desenvolvimento:
- **Models:** Campos bem definidos, `related_name` obrigatório em FKs, `verbose_name` em português.
- **Segurança:** Nunca expor IDs sequenciais em URLs públicas (usar `UUID` para ordens de serviço).
- **Mídias:** Validação rigorosa de tipo e tamanho de arquivo (especialmente vídeos).
- **WhatsApp API:** Lógica isolada em uma camada de `services.py` para não poluir as views.
- **Geolocalização:** Armazenar `Point` (latitude/longitude) e tratar erros de permissão no front.

### Stack:
- Django 6.0.
- PostgreSQL (preparado no settings).
- Python-dotenv para segredos.
