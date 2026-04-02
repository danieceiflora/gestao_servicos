from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import ServiceOrder, ServiceOrderTask, ServiceMedia, Professional

def get_collaborator_tasks(user):
    """Retorna apenas as etapas (tasks) em que o usuário logado está alocado."""
    try:
        professional = user.professional_profile
        return ServiceOrderTask.objects.filter(team_members__professional=professional).distinct()
    except Professional.DoesNotExist:
        return ServiceOrderTask.objects.none()

@login_required
def equipe_task_list(request):
    """
    Lista apenas as etapas alocadas para este colaborador.
    Ordenadas pela Ordem de Serviço mais recente, e então pela data agendada.
    """
    tasks_qs = get_collaborator_tasks(request.user).select_related(
        'service_order',
        'service_order__client_property',
        'service_order__client_property__client'
    ).order_by('-service_order__created_at', 'scheduled_at')
    
    context = {
        'tasks': tasks_qs,
        'title': 'Minhas Tarefas'
    }
    return render(request, 'services/equipe/task_list.html', context)

@login_required
def equipe_task_detail(request, task_id):
    """
    Exibe os detalhes da etapa e da OS para o colaborador, OMITINDO qualquer
    valor financeiro ou formulários de adição de itens.
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    order = task.service_order
    
    context = {
        'task': task,
        'order': order,
        'client': order.client_property.client,
        'property': order.client_property,
        'existing_medias': task.medias.all(),
        # Não enviamos itens com preço ou totais para o contexto
        'title': f'Execução: {task.get_task_type_display()}'
    }
    return render(request, 'services/equipe/task_detail.html', context)


@login_required
def equipe_task_start(request, task_id):
    """
    Registra o instante exato em que o técnico iniciou o trabalho.
    Altera o status automaticamente.
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        if not task.started_at:
            task.started_at = timezone.now()
            # Se você usar o status IN_PROGRESS no seu Model:
            if hasattr(ServiceOrderTask.TaskStatus, 'IN_PROGRESS'):
                task.status = ServiceOrderTask.TaskStatus.IN_PROGRESS
            task.save()
            messages.success(request, 'Execução da etapa iniciada!')
        else:
            messages.warning(request, 'Esta etapa já foi iniciada anteriormente.')
            
    return redirect('equipe_task_detail', task_id=task.id)


@login_required
def equipe_task_finish(request, task_id):
    """
    Registra o fim do trabalho da etapa, alterando o status para 'COMPLETED'.
    Permite adicionar notas finais da execução.
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        
        if notes:
            task.notes = f"{task.notes}\n\n[Notas de Execução]: {notes}" if task.notes else notes
            
        task.finished_at = timezone.now()
        task.status = ServiceOrderTask.TaskStatus.COMPLETED
        task.save()
        
        # Pode chamar o método update_status() da OS caso exista no modelo,
        # para garantir que a OS mude para FINISHED caso todas as etapas sejam concluídas.
        if hasattr(task.service_order, 'update_status'):
            task.service_order.update_status()
            
        messages.success(request, 'Etapa finalizada com sucesso!')
        
    return redirect('equipe_task_detail', task_id=task.id)


@login_required
def equipe_task_add_media(request, task_id):
    """
    Permite que o técnico envie fotos/vídeos da execução (antes/depois).
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if files:
            for file in files:
                ServiceMedia.objects.create(task=task, file=file)
            messages.success(request, f'{len(files)} arquivo(s) anexado(s) com sucesso!')
        else:
            messages.error(request, 'Nenhum arquivo providenciado.')
            
    return redirect('equipe_task_detail', task_id=task.id)
