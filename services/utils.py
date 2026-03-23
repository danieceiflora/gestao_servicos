from datetime import timedelta
from django.db.models import Q
from .models import ServiceOrder, ServiceOrderTeam, ProfessionalAvailability, ProfessionalScheduleBlock

def check_professional_availability(professional, timestamp):
    """
    Retorna (bool, message) indicando se o profissional está disponível no timestamp.
    """
    if not timestamp:
        return True, ""

    # 1. Verificar Grade de Horário Base (ProfessionalAvailability)
    day_of_week = timestamp.weekday()
    time_only = timestamp.time()
    
    availability = ProfessionalAvailability.objects.filter(
        professional=professional,
        day_of_week=day_of_week,
        start_time__lte=time_only,
        end_time__gte=time_only
    ).exists()
    
    if not availability:
        return False, f"O profissional {professional.name} não trabalha neste horário/dia."

    # 2. Verificar Bloqueios de Agenda (ProfessionalScheduleBlock)
    blocks = ProfessionalScheduleBlock.objects.filter(
        professional=professional,
        start_at__lte=timestamp,
        end_at__gte=timestamp
    ).exists()
    
    if blocks:
        return False, f"O profissional {professional.name} possui um bloqueio de agenda neste período."

    # 3. Verificar Conflitos de 1h30min (Buffer)
    buffer = timedelta(hours=1, minutes=30)
    start_buffer = timestamp - buffer
    end_buffer = timestamp + buffer

    # Procurar por OS onde o profissional está alocado (Orçamento ou Execução)
    # que comecem dentro da janela de conflito
    conflicts = ServiceOrderTeam.objects.filter(
        professional=professional
    ).filter(
        # Orçamentos agendados no intervalo
        Q(service_order__budget_scheduled_at__gt=start_buffer, 
          service_order__budget_scheduled_at__lt=end_buffer,
          assignment_type='BUDGET') |
        # Execuções agendadas no intervalo
        Q(service_order__execution_scheduled_at__gt=start_buffer, 
          service_order__execution_scheduled_at__lt=end_buffer,
          assignment_type='EXECUTION')
    ).select_related('service_order')

    if conflicts.exists():
        conflict = conflicts.first()
        tipo = "Orçamento" if conflict.assignment_type == 'BUDGET' else "Execução"
        return False, f"{professional.name} já tem um(a) {tipo} agendado(a) próximo a este horário (Intervalo < 1:30h)."

    return True, "Disponível"
