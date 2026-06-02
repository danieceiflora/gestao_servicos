from datetime import timedelta
from django.db.models import Q
def check_professional_availability(professional, timestamp, scheduled_end_at=None, exclude_task_id=None, ignore_working_hours=False):
    """
    Retorna (bool, message, conflict_type) indicando se o profissional está disponível no timestamp.
    """
    from ..models import ServiceOrderTask, ProfessionalScheduleBlock
    
    if not timestamp:
        return True, "", "OK"

    # 1. Verificar Grade de Horário Base (WorkSchedule/WorkScheduleDay)
    if not ignore_working_hours:
        day_of_week = timestamp.weekday()
        time_only = timestamp.time()

        if not professional.work_schedule:
            return False, f"O profissional {professional.name} não possui uma escala de horários definida.", "OUT_OF_HOURS"

        availability = professional.work_schedule.days.filter(
            day_of_week=day_of_week,
            start_time__lte=time_only,
            end_time__gte=time_only
        ).exists()

        if not availability:
            return False, f"O profissional {professional.name} não trabalha neste horário/dia.", "OUT_OF_HOURS"

    # 2. Verificar Bloqueios de Agenda (ProfessionalScheduleBlock)
    blocks = ProfessionalScheduleBlock.objects.filter(
        professional=professional,
        start_at__lte=timestamp,
        end_at__gte=timestamp
    ).exists()

    if blocks:
        return False, f"O profissional {professional.name} possui um bloqueio de agenda neste período.", "BLOCK"

    # 3. Verificar Conflitos com outras Tasks
    # Usar o intervalo real do agendamento (start -> end)
    # Se não houver fim definido, assume-se 1h de duração para fins de checagem de conflito
    start_check = timestamp
    end_check = scheduled_end_at if scheduled_end_at else (timestamp + timedelta(hours=1))

    # Buscar tasks agendadas onde o profissional está alocado que podem conflitar
    conflicts = ServiceOrderTask.objects.filter(
        team_members__professional=professional,
        status__in=[ServiceOrderTask.TaskStatus.AGENDADO, ServiceOrderTask.TaskStatus.EM_ANDAMENTO],
    ).select_related('service_order__client_property__client')
    
    # Excluir a task atual se estiver editando
    if exclude_task_id:
        conflicts = conflicts.exclude(id=exclude_task_id)
    
    # Verificar sobreposição de intervalos
    for conflict in conflicts:
        conflict_start = conflict.scheduled_at
        # Se a task de conflito não tiver fim, assume-se 1h de duração
        conflict_end = conflict.scheduled_end_at if conflict.scheduled_end_at else (conflict.scheduled_at + timedelta(hours=1))
        
        # Verifica se há sobreposição: novo intervalo começa antes do fim do conflito E termina depois do início do conflito
        if start_check < conflict_end and end_check > conflict_start:
            tipo = conflict.get_task_type_display()
            cliente = conflict.service_order.client_property.client.name
            return False, f"{professional.name} já tem um(a) {tipo} agendado(a) para {cliente} neste horário.", "CONFLICT"

    return True, "Disponível", "OK"

def format_phone_e164(phone):
    """
    Formata telefone para padrão E.164 (Brasil) com normalização do 9º dígito.
    Ex: 1188887777 -> +5511988887777
    """
    if not phone:
        return ""
    
    # Remove tudo que não é dígito
    digits = "".join(filter(str.isdigit, phone))
    
    # Remove zero à esquerda se existir (ex: 011...)
    if digits.startswith("0") and len(digits) > 10:
        digits = digits[1:]

    # Se já começa com 55 e tem tamanho de DDI+DDD+NUM (12 ou 13 dígitos), remove o 55 para normalizar
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]

    # Normalização do 9º dígito para celulares (DDD + 8 dígitos -> DDD + 9 + 8 dígitos)
    # No Brasil, celulares começam com 6, 7, 8 ou 9.
    if len(digits) == 10:
        ddd = digits[:2]
        prefix = digits[2]
        if prefix in "6789":
            digits = f"{ddd}9{digits[2:]}"
            
    # Retorna sempre no formato +55DDXXXXXXXXX
    return f"+55{digits}"
