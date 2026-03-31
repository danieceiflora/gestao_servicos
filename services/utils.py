from datetime import timedelta
from django.db.models import Q
from .models import ServiceOrder, ServiceOrderTeam, WorkScheduleDay, ProfessionalScheduleBlock, ServiceOrderTask

def check_professional_availability(professional, timestamp, exclude_task_id=None, ignore_working_hours=False):
    """
    Retorna (bool, message, conflict_type) indicando se o profissional está disponível no timestamp.

    Args:
        professional: Instância do Professional
        timestamp: datetime do agendamento
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

    # 3. Verificar Conflitos de 1h30min (Buffer) com outras Tasks
    buffer = timedelta(hours=1, minutes=30)
    start_buffer = timestamp - buffer
    end_buffer = timestamp + buffer

    # Buscar tasks agendadas onde o profissional está alocado
    conflicts = ServiceOrderTask.objects.filter(
        team_members__professional=professional,
        status__in=[ServiceOrderTask.TaskStatus.SCHEDULED, ServiceOrderTask.TaskStatus.IN_PROGRESS],
        scheduled_at__gt=start_buffer,
        scheduled_at__lt=end_buffer
    ).select_related('service_order__client_property__client')
    
    # Excluir a task atual se estiver editando
    if exclude_task_id:
        conflicts = conflicts.exclude(id=exclude_task_id)

    if conflicts.exists():
        conflict = conflicts.first()
        tipo = conflict.get_task_type_display()
        cliente = conflict.service_order.client_property.client.name
        return False, f"{professional.name} já tem um(a) {tipo} agendado(a) para {cliente} próximo a este horário (Intervalo < 1:30h).", "CONFLICT"

    return True, "Disponível", "OK"
