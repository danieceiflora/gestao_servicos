from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import (
    Professional, ServiceOrderTask, ServiceOrder, Client, Property,
    Service, Product, ChecklistTemplate, ServiceChecklistItem,
    TaskChecklistResponse, ServiceItem, ServicePayment, Occurrence,
    MediaProcessingJob
)
from .utils_media import (
    MediaProcessingBusyError,
    save_upload_for_processing,
)
from integracoes.models import SystemConfig
import uuid
import json
from decimal import Decimal

@login_required
def equipe_offline_app(request):
    """
    Renderiza o App Shell do Painel do Técnico Offline-First.
    """
    return render(request, 'services/equipe/offline_app.html', {
        'title': 'Painel do Técnico (Offline)',
        'layout_base': 'base_equipe.html'
    })

@login_required
def api_tecnico_bootstrap(request):
    """
    Retorna a carga inicial de dados para o funcionamento offline do app do técnico.
    """
    try:
        try:
            professional = request.user.professional_profile
        except (Professional.DoesNotExist, AttributeError):
            return JsonResponse({'error': 'Usuário não vinculado a um perfil profissional.'}, status=400)

        now = timezone.now()
        # Pega tarefas dos últimos 7 dias e próximas
        # para garantir que o técnico veja o histórico recente e agendamentos futuros.
        tasks_qs = ServiceOrderTask.objects.filter(
            team_members__professional=professional,
            scheduled_at__date__gte=now.date() - timezone.timedelta(days=7)
        ).select_related(
            'service_order',
            'service_order__client_property',
            'service_order__client_property__client'
        ).distinct()

        # Coletar IDs relacionados para buscar outras entidades
        order_ids = tasks_qs.values_list('service_order_id', flat=True)
        property_ids = tasks_qs.values_list('service_order__client_property_id', flat=True)
        client_ids = tasks_qs.values_list('service_order__client_property__client_id', flat=True)

        # Entidades relacionadas
        orders = ServiceOrder.objects.filter(id__in=order_ids)
        properties = Property.objects.filter(id__in=property_ids)
        clients = Client.objects.filter(id__in=client_ids)
        
        # Serviços e Produtos para permitir adicionar itens offline
        services = Service.objects.filter(is_active=True)
        products = Product.objects.filter(is_active=True)
        
        # Checklists
        checklist_templates = ChecklistTemplate.objects.filter(is_active=True)
        # Coletar itens de checklist vinculados aos serviços das OSs ou templates ativos
        checklist_items = ServiceChecklistItem.objects.filter(is_active=True)

        # Respostas de Check-list (Estava faltando!)
        responses = TaskChecklistResponse.objects.filter(task__in=tasks_qs)

        # Ocorrências
        occurrences = Occurrence.objects.filter(task__in=tasks_qs)

        # Configurações do Sistema
        sys_config = SystemConfig.load()

        data = {
            'sync_token': now.isoformat(),
            'technician': {
                'id': str(professional.id),
                'name': professional.name,
                'role': request.user.role,
            },
            'tasks': [
                {
                    'id': str(t.id),
                    'service_order_id': str(t.service_order_id),
                    'task_type': t.task_type,
                    'status': t.status,
                    'scheduled_at': t.scheduled_at.isoformat(),
                    'scheduled_end_at': t.scheduled_end_at.isoformat() if t.scheduled_end_at else None,
                    'started_at': t.started_at.isoformat() if t.started_at else None,
                    'finished_at': t.finished_at.isoformat() if t.finished_at else None,
                    'notes': t.notes,
                    'value': str(t.value) if t.value else None,
                    'customer_name': t.customer_name,
                    'customer_signature': t.customer_signature,
                } for t in tasks_qs
            ],
            'orders': [
                {
                    'id': str(o.id),
                    'number': o.number,
                    'status': o.status,
                    'client_property_id': str(o.client_property_id),
                    'description': o.description,
                    'technical_notes': o.technical_notes,
                    'total_value': str(o.total_value),
                    'total_paid': str(o.total_paid),
                    'balance_due': str(o.balance_due),
                } for o in orders
            ],
            'properties': [
                {
                    'id': str(p.id),
                    'client_id': str(p.client_id),
                    'address': p.address,
                    'number': p.number,
                    'neighborhood': p.neighborhood,
                    'city': p.city,
                    'state': p.state,
                    'full_address': p.full_address,
                    'latitude': str(p.latitude) if p.latitude else None,
                    'longitude': str(p.longitude) if p.longitude else None,
                } for p in properties
            ],
            'clients': [
                {
                    'id': str(c.id),
                    'name': c.display_name,
                    'phones': [p.phone for p in c.phones.all()],
                } for c in clients
            ],
            'checklist_items': [
                {
                    'id': item.id,
                    'service_id': item.service_id,
                    'template_id': item.template_id,
                    'name': item.name,
                    'description': item.description,
                    'evidence_type': item.evidence_type,
                    'is_required': item.is_required,
                    'order': item.order,
                } for item in checklist_items
            ],
            'checklist_responses': [
                {
                    'id': r.id,
                    'task_id': str(r.task_id),
                    'item_id': r.item_id,
                    'completed': r.completed,
                    'text_response': r.text_response,
                } for r in responses
            ],
            'occurrences': [
                {
                    'id': occ.id,
                    'task_id': str(occ.task_id),
                    'category': occ.category,
                    'occurrence_type': occ.occurrence_type,
                    'description': occ.description,
                    'status': occ.status,
                } for occ in occurrences
            ],
            'services': [
                {
                    'id': s.id,
                    'name': s.name,
                    'base_price': str(s.base_price),
                    'unit': s.unit_of_measure,
                } for s in services
            ],
            'products': [
                {
                    'id': prod.id,
                    'name': prod.name,
                    'price': str(prod.default_unit_price),
                    'unit': prod.unit_type,
                } for prod in products
            ],
            'config': {
                'company_name': sys_config.company_name,
                'pix_key': sys_config.pix_key,
                'pix_bank': sys_config.pix_bank,
            }
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': f'Erro interno no bootstrap: {str(e)}'}, status=400)


@login_required
def api_tecnico_sync_pull(request):
    """
    Retorna apenas o que mudou desde o último token de sincronização.
    """
    since = request.GET.get('since')
    if not since:
        return api_tecnico_bootstrap(request)
    
    # Por enquanto, implementaremos uma versão simplificada que retorna bootstrap
    # Futuramente podemos filtrar por updated_at > since
    return api_tecnico_bootstrap(request)

@login_required
def api_tecnico_sync_push(request):
    """
    Recebe as alterações feitas offline e persiste no banco de dados.
    Suporta JSON com lista de 'changes'.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        data = json.loads(request.body)
        changes = data.get('changes', [])
        processed_count = 0
        errors = []
        
        for index, change in enumerate(changes):
            try:
                change_type = change.get('type')
                payload = change.get('payload', {})
                task_id = payload.get('task_id')
                
                if not task_id:
                    continue
                    
                task = get_object_or_404(ServiceOrderTask, id=task_id)
                
                # 1. Início de Tarefa
                if change_type == 'TASK_START':
                    task.status = ServiceOrderTask.TaskStatus.IN_PROGRESS
                    if payload.get('started_at'):
                        task.started_at = payload.get('started_at')
                    task.save()
                    processed_count += 1
                    
                # 2. Finalização de Tarefa
                elif change_type == 'TASK_FINISH':
                    finish_data = payload.get('data', {})
                    task.status = ServiceOrderTask.TaskStatus.COMPLETED
                    task.finished_at = payload.get('finished_at') or timezone.now()
                    task.customer_name = finish_data.get('customer_name')
                    
                    # Trata Assinatura Base64
                    signature_data = finish_data.get('customer_signature')
                    if signature_data and signature_data.startswith('data:image'):
                        from django.core.files.base import ContentFile
                        from django.core.files.storage import default_storage
                        import base64
                        
                        try:
                            format, imgstr = signature_data.split(';base64,')
                            ext = format.split('/')[-1]
                            filename = f"signatures/signature_{task.id}.{ext}"
                            
                            # Verifica se o campo é um FileField/ImageField ou CharField
                            if hasattr(task.customer_signature, 'save'):
                                task.customer_signature.save(
                                    filename,
                                    ContentFile(base64.b64decode(imgstr)),
                                    save=False
                                )
                            else:
                                # Se for CharField, salva manualmente e guarda o caminho
                                path = default_storage.save(filename, ContentFile(base64.b64decode(imgstr)))
                                task.customer_signature = path
                        except Exception as sig_err:
                            print(f"Erro ao salvar assinatura: {sig_err}")
                    
                    if finish_data.get('notes'):
                        task.notes = (task.notes or "") + "\n\nNotas Offline:\n" + finish_data.get('notes')
                    
                    # Processa Pagamento Opcional
                    payment_data = finish_data.get('payment')
                    if payment_data:
                        try:
                            amount = Decimal(str(payment_data.get('amount', 0)))
                            method = payment_data.get('method')
                            if amount > 0 and method:
                                # Tenta pegar o perfil profissional do usuário logado
                                try:
                                    professional = request.user.professional_profile
                                except (Professional.DoesNotExist, AttributeError):
                                    professional = None
                                    
                                ServicePayment.objects.create(
                                    order=task.service_order,
                                    amount=amount,
                                    payment_method=method,
                                    paid_at=task.finished_at or timezone.now(),
                                    received_by=professional,
                                    status=ServicePayment.PaymentStatus.PENDING,
                                    notes="[Sincronizado Offline]: Recebido na finalização da OS"
                                )
                        except Exception as pay_err:
                            print(f"Erro ao salvar pagamento offline: {pay_err}")

                    task.save()
                    processed_count += 1
                    
                # 3. Atualização de Checklist
                elif change_type == 'CHECKLIST_UPDATE':
                    item_data = payload.get('data', {})
                    response_id = item_data.get('response_id')
                    if response_id:
                        response = get_object_or_404(TaskChecklistResponse, id=response_id)
                        if 'completed' in item_data:
                            response.completed = item_data['completed']
                        if 'text_response' in item_data:
                            response.text_response = item_data['text_response']
                        response.save()
                        processed_count += 1
                
                # 4. Criação de Ocorrência
                elif change_type == 'OCCURRENCE_CREATE':
                    occ_data = payload.get('data', {})
                    occ = Occurrence.objects.create(
                        task=task,
                        category=occ_data.get('category', Occurrence.OccurrenceCategory.GENERAL),
                        occurrence_type=occ_data.get('occurrence_type', Occurrence.OccurrenceType.OTHER),
                        description=occ_data.get('description', ''),
                        status=Occurrence.OccurrenceStatus.REGISTERED
                    )
                    # Se houver um ID temporário local, podemos retornar para o cliente se necessário
                    # Mas o importante é que mídias vinculadas a esta ocorrência usem o ID real depois.
                    # Para simplificar, o upload de mídia de ocorrência pode ser tratado separadamente.
                    processed_count += 1
                
                # 5. Outros tipos podem ser adicionados aqui
                
            except Exception as item_err:
                error_msg = f"Erro no item {index} ({change.get('type')}): {str(item_err)}"
                print(error_msg)
                errors.append(error_msg)

        return JsonResponse({
            'success': len(errors) == 0, 
            'processed_count': processed_count,
            'errors': errors
        }, status=400 if errors else 200)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def api_tecnico_upload_media(request, task_id):
    """
    Endpoint dedicado para upload de mídias capturadas offline.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        task = get_object_or_404(ServiceOrderTask, id=task_id)
        response_id = request.POST.get('response_id')
        file = request.FILES.get('file')
        
        if not file:
            return JsonResponse({'error': 'Nenhum arquivo enviado'}, status=400)

        response = None
        if response_id and response_id != 'null':
            response = get_object_or_404(TaskChecklistResponse, id=response_id)

        occurrence_id = request.POST.get('occurrence_id')
        occurrence = None
        if occurrence_id and occurrence_id != 'null':
            occurrence = get_object_or_404(Occurrence, id=occurrence_id)

        raw_path, file_info = save_upload_for_processing(file)

        job = MediaProcessingJob.objects.create(
            task=task,
            response=response,
            occurrence=occurrence,
            raw_path=raw_path,
            original_name=file_info.name,
            content_type=file_info.content_type,
            status=MediaProcessingJob.Status.PENDING,
        )

        return JsonResponse(
            {'success': True, 'job_id': job.id, 'queued': True},
            status=202
        )
    except MediaProcessingBusyError as e:
        return JsonResponse({'error': str(e)}, status=429)
    except (ValueError, RuntimeError) as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=400)
