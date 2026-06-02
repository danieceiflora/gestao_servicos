from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from services.models import ServiceOrder, ServiceOrderTask, Sale
from .utils import dispatch_dynamic_notification
import logging

logger = logging.getLogger(__name__)

# Lista de modelos que suportam notificações dinâmicas
DYNAMIC_NOTIFICATION_MODELS = [ServiceOrder, ServiceOrderTask, Sale]

@receiver(pre_save)
def capture_old_status(sender, instance, **kwargs):
    """
    Captura o status anterior antes de salvar para detectar mudanças no post_save.
    """
    if sender not in DYNAMIC_NOTIFICATION_MODELS:
        return
        
    if instance.pk:
        try:
            # Busca o registro original no banco (sem usar cache do objeto atual)
            old_instance = sender.objects.get(pk=instance.pk)
            # Salva o status anterior em um atributo temporário do objeto
            instance._old_status = getattr(old_instance, 'status', None)
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save)
def handle_dynamic_notifications(sender, instance, created, **kwargs):
    """
    Dispara as notificações configuradas dinamicamente.
    """
    if sender not in DYNAMIC_NOTIFICATION_MODELS:
        return

    try:
        if created:
            # Gatilho de Criação
            dispatch_dynamic_notification(instance, 'CRIAR')
        else:
            # Gatilho de Alteração de Status
            old_status = getattr(instance, '_old_status', None)
            new_status = getattr(instance, 'status', None)
            
            # Se o status mudou, ou se não tínhamos o status antigo (ex: primeiro save após migração)
            if new_status and old_status != new_status:
                dispatch_dynamic_notification(
                    instance, 
                    'MUDANCA_STATUS', 
                    old_status=old_status
                )
    except Exception as e:
        # Falhas no envio não devem travar o salvamento do registro principal
        logger.error(f"Erro ao processar notificações dinâmicas para {sender.__name__}: {e}")
