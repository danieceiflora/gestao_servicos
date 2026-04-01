# 🔔 Push Notifications - Guia de Implementação

Sistema completo de notificações push usando Service Worker e Web Push API.

---

## 🚀 Configuração Inicial

### 1️⃣ Instalar dependências
```bash
pip install -r requirements.txt
```

### 2️⃣ Gerar chaves VAPID
```bash
python generate_vapid_keys.py
```

Copie as chaves geradas e adicione no `core/settings.py`:
```python
VAPID_PUBLIC_KEY = 'sua-chave-publica-aqui'
VAPID_PRIVATE_KEY = 'sua-chave-privada-aqui'
VAPID_ADMIN_EMAIL = 'admin@douradoscalhas.com.br'
```

### 3️⃣ Criar migrations e migrar
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4️⃣ Rebuild e reiniciar containers (se usando Docker)
```bash
docker-compose build web
docker-compose restart web
```

---

## 📱 Como Usar

### Acessar página de teste
1. Acesse: `https://osonline.douradoscalhas.com.br/notifications/test/`
2. Clique em "Ativar Notificações"
3. Permita notificações quando o navegador solicitar
4. Teste com "Enviar Notificação de Teste"

### Enviar para múltiplos usuários
1. Preencha título e mensagem
2. Selecione os usuários destinatários (Ctrl/Cmd + clique para múltiplos)
3. Clique em "Enviar Notificação"

---

## 🔧 Estrutura dos Arquivos

```
gestao_servicos/
├── services/
│   ├── models.py                    # Model PushSubscription
│   ├── notifications.py             # Views de notificações
│   └── urls.py                      # URLs das notificações
├── templates/services/
│   └── notifications_test.html      # Interface de teste
├── static/js/
│   └── serviceworker.js            # Service Worker com push
├── core/
│   └── settings.py                  # Configurações VAPID
└── generate_vapid_keys.py          # Script para gerar chaves
```

---

## 🛠️ Integração no Sistema

### Enviar notificação programaticamente

```python
from services.models import PushSubscription
from pywebpush import webpush
from django.conf import settings
import json

def send_push_to_user(user, title, message, url='/'):
    """Enviar notificação para um usuário específico"""
    subscriptions = PushSubscription.objects.filter(
        user=user,
        is_active=True
    )
    
    notification_data = {
        'title': title,
        'body': message,
        'icon': '/static/dourados-calhas.png',
        'url': url,
    }
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth
                    }
                },
                data=json.dumps(notification_data),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'
                }
            )
        except Exception as e:
            print(f'Erro ao enviar push: {e}')

# Exemplo de uso:
# send_push_to_user(
#     user=request.user,
#     title='Nova OS atribuída',
#     message='Você foi designado para a OS #1234',
#     url='/orders/1234/'
# )
```

### Integrar com signals do Django

```python
# services/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder
from .notifications import send_push_to_user

@receiver(post_save, sender=ServiceOrder)
def notify_on_new_order(sender, instance, created, **kwargs):
    if created and instance.assigned_professional:
        send_push_to_user(
            user=instance.assigned_professional.user,
            title='Nova Ordem de Serviço',
            message=f'OS #{instance.id} foi criada para você',
            url=f'/orders/{instance.id}/'
        )
```

---

## 🎯 Casos de Uso

### 1. Nova OS atribuída
```python
send_push_to_user(
    user=professional.user,
    title='🆕 Nova OS Atribuída',
    message=f'Você foi designado para a OS #{order.id}',
    url=f'/orders/{order.id}/'
)
```

### 2. Mudança de status
```python
send_push_to_user(
    user=manager.user,
    title='✅ OS Finalizada',
    message=f'A OS #{order.id} foi concluída',
    url=f'/orders/{order.id}/'
)
```

### 3. Lembrete de vistoria
```python
send_push_to_user(
    user=professional.user,
    title='⏰ Lembrete de Vistoria',
    message=f'Vistoria agendada para hoje às {task.scheduled_time}',
    url=f'/tasks/{task.id}/'
)
```

### 4. Aprovação de orçamento
```python
send_push_to_user(
    user=manager.user,
    title='💰 Orçamento Aprovado',
    message=f'Cliente aprovou o orçamento da OS #{order.id}',
    url=f'/orders/{order.id}/'
)
```

---

## 🔐 Segurança

- ✅ Chaves VAPID são únicas por projeto
- ✅ Private key nunca é exposta ao cliente
- ✅ Subscriptions são vinculadas ao usuário logado
- ✅ Apenas usuários autenticados podem se inscrever
- ✅ Validação de permissões nas views

### Produção
Use variáveis de ambiente:
```python
import os

VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_ADMIN_EMAIL = os.getenv('VAPID_ADMIN_EMAIL', 'admin@douradoscalhas.com.br')
```

---

## 🐛 Troubleshooting

### Notificações não aparecem
1. Verificar se o Service Worker está registrado (DevTools > Application > Service Workers)
2. Verificar permissões do navegador (ícone de cadeado na barra de endereço)
3. Verificar console para erros
4. Testar em modo anônimo/privado

### Subscription falha
1. Verificar se as chaves VAPID estão corretas no settings.py
2. Verificar se o domínio está em HTTPS (obrigatório para Push API)
3. Verificar se CSRF_TRUSTED_ORIGINS está configurado

### Push não enviado
1. Verificar logs do servidor para erros
2. Verificar se subscription está ativa no banco
3. Testar com a página de teste primeiro

---

## 📚 Recursos Adicionais

- [Web Push API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- [Service Workers - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
- [pywebpush Documentation](https://github.com/web-push-libs/pywebpush)
- [VAPID Protocol](https://datatracker.ietf.org/doc/html/rfc8292)

---

## ✅ Checklist de Implementação

- [x] Service Worker com suporte a push
- [x] Model PushSubscription
- [x] Views para subscribe/unsubscribe
- [x] Interface de teste funcional
- [x] Envio para múltiplos usuários
- [ ] Integração com signals do Django
- [ ] Agendamento de notificações
- [ ] Dashboard de notificações enviadas
- [ ] Histórico de notificações por usuário
- [ ] Templates de notificações predefinidos

---

**Status:** ✅ Implementação básica completa e funcional!
**Próximo passo:** Testar e integrar com o fluxo de Ordens de Serviço
