from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
import json
from django.contrib.auth import get_user_model
from django.db.models import Q
from .notifications import send_push_notification
from .models import (
    ServiceOrder, ServiceOrderTask, ServiceMedia, Professional, 
    Occurrence, Property, ServiceChecklistItem, TaskChecklistResponse
)

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
        'title': 'Minhas Tarefas',
        'layout_base': 'base.html' if request.user.is_manager else 'base_equipe.html'
    }
    return render(request, 'services/equipe/task_list.html', context)

@login_required
def equipe_task_detail(request, task_id):
    """
    Exibe os detalhes da etapa e da OS para o colaborador.
    Carrega também o checklist caso existam serviços vinculados.
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    order = task.service_order
    
    # --- LÓGICA DE CHECKLIST ---
    # Busca todos os serviços (catalogo) incluídos nesta OS
    order_services = order.items.filter(service__isnull=False).values_list('service', flat=True).distinct()
    
    # Busca itens de checklist ativos para estes serviços
    checklist_items = ServiceChecklistItem.objects.filter(service_id__in=order_services, is_active=True)
    
    # Inicializa as respostas caso não existam (apenas para etapas de execução ou garantia por padrão)
    if checklist_items.exists() and task.task_type in [ServiceOrderTask.TaskType.EXECUTION, ServiceOrderTask.TaskType.WARRANTY]:
        for item in checklist_items:
            TaskChecklistResponse.objects.get_or_create(task=task, item=item)
            
    checklist_responses = task.checklist_responses.select_related('item', 'item__service').order_by('item__service__name', 'item__order')

    context = {
        'task': task,
        'order': order,
        'client': order.client_property.client,
        'property': order.client_property,
        'existing_medias': task.medias.filter(occurrence__isnull=True),
        'occurrences': task.occurrences.all(),
        'occurrence_types': Occurrence.OccurrenceType.choices,
        'occurrence_categories': Occurrence.OccurrenceCategory.choices,
        'checklist_responses': checklist_responses,
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
    Valida se o checklist obrigatório foi preenchido.
    """
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        # Validar checklist obrigatório
        pending_required = task.checklist_responses.filter(item__is_required=True, completed=False).exists()
        if pending_required:
            messages.error(request, 'Existem itens obrigatórios no check-list que ainda não foram preenchidos.')
            return redirect('equipe_task_detail', task_id=task.id)

        notes = request.POST.get('notes', '').strip()
        
        if notes:
            task.notes = f"{task.notes}\n\n[Notas de Execução]: {notes}" if task.notes else notes
            
        task.finished_at = timezone.now()
        task.status = ServiceOrderTask.TaskStatus.COMPLETED
        task.save()
        
        if hasattr(task.service_order, 'update_status'):
            task.service_order.update_status()
            
        messages.success(request, 'Etapa finalizada com sucesso!')
        return redirect('equipe_task_list')

@login_required
def equipe_task_checklist_update(request, task_id):
    """Atualiza um item específico do checklist via POST/AJAX"""
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        response_id = request.POST.get('response_id')
        response = get_object_or_404(TaskChecklistResponse, id=response_id, task=task)
        item = response.item
        
        completed = request.POST.get('completed') == 'true' or request.POST.get('completed') == 'on'
        
        if item.evidence_type == ServiceChecklistItem.EvidenceType.TEXT:
            response.text_response = request.POST.get('text_response', '')
        elif item.evidence_type == ServiceChecklistItem.EvidenceType.PHOTO:
            if 'photo' in request.FILES:
                response.photo = request.FILES['photo']
        elif item.evidence_type == ServiceChecklistItem.EvidenceType.VIDEO:
            if 'video' in request.FILES:
                response.video = request.FILES['video']
                
        response.completed = completed
        response.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'completed': response.completed})
            
        messages.success(request, 'Check-list atualizado!')
    
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

@login_required
def equipe_media_delete(request, media_id):
    """Permite ao instalador excluir uma mídia (foto/vídeo) que ele enviou antes de finalizar a OS."""
    media = get_object_or_404(ServiceMedia, id=media_id)
    task = media.task

    # Verifica se o usuário logado pertence à equipe designada para esta OS (ou é admin)
    if not request.user.is_superuser:
        user_tasks = get_collaborator_tasks(request.user)
        if task not in user_tasks:
            messages.error(request, 'Você não tem permissão para modificar esta OS.')
            return redirect('equipe_task_list')

    if task.status == 'Concluído':
        messages.error(request, 'Não é possível excluir mídias de uma OS finalizada.')
        return redirect('equipe_task_detail', task_id=task.id)

    if request.method == 'POST':
        media.delete()
        messages.success(request, 'Mídia excluída com sucesso.')
    
    return redirect('equipe_task_detail', task_id=task.id)

@login_required
def equipe_task_add_occurrence(request, task_id):
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    if request.method == 'POST':
        category = request.POST.get('category')
        occurrence_type = request.POST.get('occurrence_type')
        description = request.POST.get('description')
        if category and occurrence_type and description:
            occurrence = Occurrence.objects.create(
                task=task,
                category=category,
                occurrence_type=occurrence_type,
                description=description
            )
            files = request.FILES.getlist('files')
            for file in files:
                ServiceMedia.objects.create(task=task, occurrence=occurrence, file=file)

            try:
                from django.contrib.auth import get_user_model
                from django.db.models import Q
                from .notifications import send_push_notification
                admins = get_user_model().objects.filter(Q(is_superuser=True) | Q(role__in=['ADMIN', 'MANAGER']))
                os_number = task.service_order.number or task.service_order.id
                for admin in admins:
                    send_push_notification(
                        admin, 
                        "Nova Ocorrência", 
                        f"Em {task.get_task_type_display()} na OS #{os_number}: {occurrence.get_occurrence_type_display()}"
                    )
            except Exception as e:
                import traceback
                print(f"Erro no push: {e}")
                traceback.print_exc()

            if category == Occurrence.OccurrenceCategory.BLOCKING:
                task.status = ServiceOrderTask.TaskStatus.NOT_EXECUTED
                task.save()
                messages.warning(request, 'Ocorrência impeditiva registrada. Etapa marcada como não executada e aguardando reagendamento.')
            else:
                messages.success(request, 'Ocorrência registrada com sucesso!')
        else:
            messages.error(request, 'Categoria, Tipo e Descrição são obrigatórios.')
    return redirect('equipe_task_detail', task_id=task.id)


@login_required
def equipe_update_gps(request, property_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = data.get('latitude')
            lng = data.get('longitude')

            if lat and lng:
                property_obj = get_object_or_404(Property, id=property_id)
                property_obj.latitude = lat
                property_obj.longitude = lng
                property_obj.save()
                return JsonResponse({'status': 'success', 'message': 'Coordenadas atualizadas com sucesso.', 'latitude': lat, 'longitude': lng})
            else:
                return JsonResponse({'status': 'error', 'message': 'Latitude e longitude não fornecidas.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método não permitido.'}, status=405)
