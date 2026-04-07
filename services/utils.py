from datetime import timedelta
from django.db.models import Q
from .models import ServiceOrder, ServiceOrderTeam, WorkScheduleDay, ProfessionalScheduleBlock, ServiceOrderTask

def check_professional_availability(professional, timestamp, scheduled_end_at=None, exclude_task_id=None, ignore_working_hours=False):
    """
    Retorna (bool, message, conflict_type) indicando se o profissional está disponível no timestamp.

    Args:
        professional: Instância do Professional
        timestamp: datetime do agendamento (início)
        scheduled_end_at: datetime do fim do agendamento (opcional)
        exclude_task_id: UUID da task a excluir da verificação (útil ao editar)
        ignore_working_hours: bool indicando se deve ignorar a checagem de horário de trabalho (para confirmação forçada)
    """
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
        status__in=[ServiceOrderTask.TaskStatus.SCHEDULED, ServiceOrderTask.TaskStatus.IN_PROGRESS],
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
