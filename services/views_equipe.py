from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.core.paginator import Paginator
import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import Q
from .notifications import send_push_notification
from .models import (
    Service, ServiceOrder, ServiceOrderTask, ServiceMedia, Professional, 
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
    ).exclude(status=ServiceOrderTask.TaskStatus.CANCELLED).order_by('scheduled_at')
    
    paginator = Paginator(tasks_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'tasks': page_obj,  # Antigamente era 'tasks': tasks_qs
        'page_obj': page_obj,
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
    
    # --- LÓGICA DE CHECKLIST REFORMULADA ---
    # 1. Identifica todos os serviços incluídos nesta OS
    order_services = Service.objects.filter(service_items__service_order=order).distinct()
    
    # 2. Coleta itens específicos de cada serviço E itens de seus templates
    checklist_items = []
    
    for service in order_services:
        # Itens diretos do serviço
        checklist_items.extend(list(service.checklist_items.filter(is_active=True)))
        
        # Itens do template vinculado ao serviço
        if service.checklist_template:
            checklist_items.extend(list(service.checklist_template.items.filter(is_active=True)))
    
    # Remove duplicados baseados em ID
    seen_ids = set()
    unique_items = []
    for item in checklist_items:
        if item.id not in seen_ids:
            unique_items.append(item)
            seen_ids.add(item.id)
    
    # 3. Inicializa as respostas caso não existam
    if unique_items and task.task_type in [ServiceOrderTask.TaskType.EXECUTION, ServiceOrderTask.TaskType.WARRANTY]:
        for item in unique_items:
            TaskChecklistResponse.objects.get_or_create(task=task, item=item)
            
    checklist_responses = task.checklist_responses.select_related(
        'item', 'item__service', 'item__template'
    ).prefetch_related('medias').order_by('item__order', 'id')

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
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'success': False, 'error': 'Existem itens obrigatórios no check-list que ainda não foram preenchidos.'}, status=400)
            messages.error(request, 'Existem itens obrigatórios no check-list que ainda não foram preenchidos.')
            return redirect('equipe_task_detail', task_id=task.id)

        notes = request.POST.get('notes', '').strip()
        customer_name = request.POST.get('customer_name', '').strip()
        signature_base64 = request.POST.get('signature_data', '')

        if notes:
            task.notes = f"{task.notes}\n\n[Notas de Execução]: {notes}" if task.notes else notes
            
        if customer_name:
            task.customer_name = customer_name

        if signature_base64 and ',' in signature_base64:
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage
            import base64
            import uuid

            try:
                format, imgstr = signature_base64.split(';base64,')
                ext = format.split('/')[-1]
                filename = f"sig_{task.id}_{uuid.uuid4().hex[:8]}.{ext}"
                
                now = timezone.now()
                # Usa "/" explicitamente para ser compatível com S3/R2 independente do SO (evitando o os.path.join do Windows)
                relative_path = f"signatures/{now.strftime('%Y')}/{now.strftime('%m')}/{filename}"
                
                data = ContentFile(base64.b64decode(imgstr))
                
                # Salva o arquivo fisicamente
                actual_path = default_storage.save(relative_path, data)
                task.customer_signature = actual_path
            except Exception as e:
                import logging
                logging.error(f"Erro ao salvar assinatura offline/online: {e}")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
                pass

        task.finished_at = timezone.now()
        task.status = ServiceOrderTask.TaskStatus.COMPLETED
        task.save()
        
        if hasattr(task.service_order, 'update_status'):
            task.service_order.update_status()
            
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': 'Etapa finalizada com sucesso!'})
            
        messages.success(request, 'Etapa finalizada com sucesso!')
        return redirect('equipe_task_list')

@login_required
def equipe_task_checklist_update(request, task_id):
    """Atualiza um item específico do checklist via POST/AJAX. Agora suporta múltiplas mídias."""
    from .models import ChecklistResponseMedia
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    
    if request.method == 'POST':
        response_id = request.POST.get('response_id')
        response = get_object_or_404(TaskChecklistResponse, id=response_id, task=task)
        item = response.item
        
        completed = request.POST.get('completed') == 'true' or request.POST.get('completed') == 'on'
        
        # Atualiza texto se houver
        if item.evidence_type == ServiceChecklistItem.EvidenceType.TEXT:
            response.text_response = request.POST.get('text_response', '')
            
        # Adiciona nova mídia se houver (suporta upload um por um via AJAX)
        if item.evidence_type in [ServiceChecklistItem.EvidenceType.PHOTO, ServiceChecklistItem.EvidenceType.VIDEO]:
            file_key = 'photo' if item.evidence_type == ServiceChecklistItem.EvidenceType.PHOTO else 'video'
            if file_key in request.FILES:
                try:
                    ChecklistResponseMedia.objects.create(
                        response=response,
                        file=request.FILES[file_key]
                    )
                except Exception as e:
                    import logging
                    logging.error(f"Erro ao salvar midia do checklist no Cloud/R2: {e}")
                    # Retorna 500 para acionar o modo fallback no JS caso esteja online mas sem cloud
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
                
        response.completed = completed
        response.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'completed': response.completed})
            
        messages.success(request, 'Check-list atualizado!')
    
    return redirect('equipe_task_detail', task_id=task.id)
@login_required
def equipe_checklist_media_delete(request, media_id):
    """Permite ao instalador excluir uma mídia específica de um item do check-list."""
    from .models import ChecklistResponseMedia
    media = get_object_or_404(ChecklistResponseMedia, id=media_id)
    task = media.response.task

    if not request.user.is_superuser:
        user_tasks = get_collaborator_tasks(request.user)
        if task not in user_tasks:
            messages.error(request, 'Permissão negada.')
            return redirect('equipe_task_list')

    if task.status == ServiceOrderTask.TaskStatus.COMPLETED:
        messages.error(request, 'Etapa já finalizada.')
    else:
        media.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        messages.success(request, 'Mídia removida.')
    
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
            try:
                for file in files:
                    ServiceMedia.objects.create(task=task, file=file)
                messages.success(request, f'{len(files)} arquivo(s) anexado(s) com sucesso!')
            except Exception as e:
                import logging
                logging.error(f"Erro ao salvar midia no Cloud/R2: {e}")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
                messages.error(request, 'Falha ao salvar mídia na nuvem. Tente novamente mais tarde.')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'success': False, 'error': 'Nenhum arquivo providenciado.'}, status=400)
            messages.error(request, 'Nenhum arquivo providenciado.')
            
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'success': True})
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
            try:
                occurrence = Occurrence.objects.create(
                    task=task,
                    category=category,
                    occurrence_type=occurrence_type,
                    description=description
                )
                files = request.FILES.getlist('files')
                if files:
                    for file in files:
                        ServiceMedia.objects.create(task=task, occurrence=occurrence, file=file)
            except Exception as e:
                import logging
                logging.error(f"Erro ao salvar ocorrencia ou midia no Cloud/R2: {e}")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
                messages.error(request, 'Falha ao salvar a ocorrência. Tente novamente.')
                return redirect('equipe_task_detail', task_id=task.id)

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
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': True, 'message': 'Ocorrência impeditiva registrada.'})
                    
                messages.warning(request, 'Ocorrência impeditiva registrada. Etapa marcada como não executada e aguardando reagendamento.')
            else:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': True, 'message': 'Ocorrência registrada com sucesso!'})
                    
                messages.success(request, 'Ocorrência registrada com sucesso!')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'success': False, 'error': 'Campos obrigatórios.'}, status=400)
            messages.error(request, 'Categoria, Tipo e Descrição são obrigatórios.')
            
    return redirect('equipe_task_detail', task_id=task.id)


@login_required
def equipe_task_add_payment(request, task_id):
    """
    Permite que o técnico registre um pagamento recebido no campo.
    Apenas Dinheiro ou Cartão de Crédito.
    """
    from .models import ServicePayment
    tasks_qs = get_collaborator_tasks(request.user)
    task = get_object_or_404(tasks_qs, id=task_id)
    order = task.service_order
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0').replace(',', '.'))
            method = request.POST.get('payment_method')
            notes = request.POST.get('notes', '').strip()
            
            if amount <= 0:
                messages.error(request, 'O valor do pagamento deve ser maior que zero.')
                return redirect('equipe_task_detail', task_id=task.id)
                
            if method not in ['CASH', 'CREDIT_CARD']:
                messages.error(request, 'Método de pagamento inválido para registro em campo.')
                return redirect('equipe_task_detail', task_id=task.id)
            
            # Tenta pegar o perfil profissional do usuário logado
            try:
                professional = request.user.professional_profile
            except Professional.DoesNotExist:
                professional = None
                
            ServicePayment.objects.create(
                order=order,
                amount=amount,
                payment_method=method,
                paid_at=timezone.now(),
                received_by=professional,
                status=ServicePayment.PaymentStatus.PENDING,
                notes=f"[Registrado pelo Técnico]: {notes}" if notes else "Registrado pelo técnico"
            )
            
            messages.success(request, f'Pagamento de R$ {amount} registrado com sucesso! Aguarde a baixa pelo financeiro.')
            
        except Exception as e:
            messages.error(request, f'Erro ao registrar pagamento: {str(e)}')
            
    return redirect('equipe_task_detail', task_id=task.id)

@login_required
def equipe_payment_delete(request, payment_id):
    """Permite ao técnico excluir um pagamento que ele registrou, enquanto estiver PENDENTE."""
    from .models import ServicePayment
    payment = get_object_or_404(ServicePayment, id=payment_id)
    
    # Segurança: Apenas se estiver pendente e for o próprio técnico (ou admin)
    if payment.status != ServicePayment.PaymentStatus.PENDING:
        messages.error(request, "Este pagamento já foi processado e não pode ser excluído.")
        return redirect('equipe_task_detail', task_id=request.GET.get('task_id', payment.order.tasks.first().id))

    try:
        professional = request.user.professional_profile
        if not request.user.is_manager and payment.received_by != professional:
            messages.error(request, "Você não tem permissão para excluir este pagamento.")
            return redirect('equipe_task_detail', task_id=request.GET.get('task_id', payment.order.tasks.first().id))
    except Professional.DoesNotExist:
        if not request.user.is_manager:
            messages.error(request, "Perfil profissional não encontrado.")
            return redirect('home')

    if request.method == 'POST':
        payment.delete()
        messages.success(request, "Registro de pagamento excluído.")
        
    task_id = request.GET.get('task_id')
    if task_id:
        return redirect('equipe_task_detail', task_id=task_id)
    return redirect('home')

@login_required
def equipe_payment_edit(request, payment_id):
    """Permite ao técnico editar um pagamento pendente."""
    from .models import ServicePayment
    payment = get_object_or_404(ServicePayment, id=payment_id)
    task_id = request.GET.get('task_id')
    
    if payment.status != ServicePayment.PaymentStatus.PENDING:
        messages.error(request, "Este pagamento já foi processado e não pode ser editado.")
        return redirect('equipe_task_detail', task_id=task_id) if task_id else redirect('home')

    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0').replace(',', '.'))
            method = request.POST.get('payment_method')
            notes = request.POST.get('notes', '').strip()
            
            if amount <= 0:
                messages.error(request, 'O valor deve ser maior que zero.')
            elif method not in ['CASH', 'CREDIT_CARD']:
                messages.error(request, 'Método inválido.')
            else:
                payment.amount = amount
                payment.payment_method = method
                # Preserva o prefixo se existir, ou adiciona
                clean_notes = notes.replace('[Registrado pelo Técnico]: ', '')
                payment.notes = f"[Registrado pelo Técnico]: {clean_notes}" if clean_notes else "Registrado pelo técnico"
                payment.save()
                messages.success(request, "Pagamento atualizado com sucesso.")
                if task_id:
                    return redirect('equipe_task_detail', task_id=task_id)
                return redirect('home')
        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")

    context = {
        'payment': payment,
        'clean_notes': payment.notes.replace('[Registrado pelo Técnico]: ', '') if payment.notes else '',
        'task_id': task_id,
        'title': 'Editar Pagamento',
        'layout_base': 'base.html' if request.user.is_manager else 'base_equipe.html'
    }
    return render(request, 'services/equipe/payment_edit.html', context)

@login_required
def api_equipe_agenda_do_dia(request):
    """
    Endpoint que retorna todos os dados necessários para o funcionamento offline
    das tarefas do técnico no dia atual.
    """
    try:
        professional = request.user.professional_profile
    except Professional.DoesNotExist:
        return JsonResponse({'error': 'Usuário não vinculado a um perfil profissional.'}, status=400)

    # Filtra as tarefas do dia atual (ou próximas 24h)
    today = timezone.now().date()
    tasks_qs = ServiceOrderTask.objects.filter(
        team_members__professional=professional,
        scheduled_at__date=today
    ).select_related(
        'service_order',
        'service_order__client_property',
        'service_order__client_property__client'
    ).exclude(status=ServiceOrderTask.TaskStatus.CANCELLED).distinct()

    data = {
        'date': today.isoformat(),
        'technician': professional.name,
        'tasks': []
    }

    for task in tasks_qs:
        order = task.service_order
        prop = order.client_property
        client = prop.client

        # --- Coleta Itens do Checklist ---
        # 1. Identifica todos os serviços incluídos nesta OS
        order_services = Service.objects.filter(service_items__service_order=order).distinct()
        
        checklist_items_data = []
        seen_ids = set()

        # Coletar itens dos serviços e templates
        for service in order_services:
            items = list(service.checklist_items.filter(is_active=True))
            if service.checklist_template:
                items.extend(list(service.checklist_template.items.filter(is_active=True)))
            
            for item in items:
                if item.id not in seen_ids:
                    # Tenta pegar resposta existente
                    resp, _ = TaskChecklistResponse.objects.get_or_create(task=task, item=item)
                    checklist_items_data.append({
                        'response_id': resp.id,
                        'item_id': item.id,
                        'name': item.name,
                        'description': item.description,
                        'evidence_type': item.evidence_type,
                        'is_required': item.is_required,
                        'completed': resp.completed,
                        'text_response': resp.text_response or ''
                    })
                    seen_ids.add(item.id)

        task_data = {
            'id': str(task.id),
            'type': task.get_task_type_display(),
            'task_type': task.task_type,
            'status': task.status,
            'scheduled_at': task.scheduled_at.isoformat(),
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'finished_at': task.finished_at.isoformat() if task.finished_at else None,
            'notes': task.notes,
            'order_details': {
                'id': str(order.id),
                'number': order.number,
                'status_display': order.get_status_display(),
                'client_name': client.display_name,
                'client_phone': client.phones.filter(is_primary=True).first().phone if client.phones.filter(is_primary=True).exists() else '',
                'address': prop.full_address,
                'gps': {
                    'lat': float(prop.latitude) if prop.latitude else None,
                    'lng': float(prop.longitude) if prop.longitude else None
                }
            },
            'checklist': checklist_items_data
        }
        data['tasks'].append(task_data)

    return JsonResponse(data)

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
