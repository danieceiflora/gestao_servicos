from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import (
    Professional, ServiceOrderTask, ServiceOrder, Client, Property,
    Service, Product, ChecklistTemplate, ServiceChecklistItem,
    TaskChecklistResponse, ServiceItem, ServicePayment, Occurrence,
    MediaProcessingJob, Billing, Installment, PaymentMethod,
    MaintenanceVisit, MaintenanceVisitMedia, MaintenanceContract,
)
from .utils_media import (
    MediaProcessingBusyError,
    save_upload_for_processing,
)
from .utils.finance import create_billing_for_os
from integracoes.models import SystemConfig
import uuid
import json
from decimal import Decimal
from django.db.models import Q, Sum

import calendar as _cal
from datetime import date as _date


def _auto_generate_visits_for_contract(contract, month, year):
    """Cria registros MaintenanceVisit faltantes para o mês/ano dado."""
    month_start = _date(year, month, 1)
    month_end = _date(year, month, _cal.monthrange(year, month)[1])

    if contract.start_date > month_end:
        return
    if contract.end_date and contract.end_date < month_start:
        return

    existing_dates = set(
        MaintenanceVisit.objects.filter(
            contract=contract,
            scheduled_date__year=year,
            scheduled_date__month=month,
        ).values_list('scheduled_date', flat=True)
    )

    dates_to_create = []
    freq = contract.frequency

    if freq == 'SEMANAL':
        days = contract.visit_days or [0]  # padrão: segunda
        cal = _cal.monthcalendar(year, month)
        for week in cal:
            for day_idx in days:
                day_num = week[int(day_idx)]
                if day_num != 0:
                    d = _date(year, month, day_num)
                    if d >= contract.start_date and (not contract.end_date or d <= contract.end_date):
                        dates_to_create.append(d)

    elif freq == 'QUINZENAL':
        days = contract.visit_days or [0]
        cal = _cal.monthcalendar(year, month)
        for day_idx in days:
            occurrences = [
                _date(year, month, week[int(day_idx)])
                for week in cal if week[int(day_idx)] != 0
            ]
            for d in occurrences[:2]:
                if d >= contract.start_date and (not contract.end_date or d <= contract.end_date):
                    dates_to_create.append(d)

    else:  # MENSAL, BIMESTRAL, TRIMESTRAL, SEMESTRAL, ANUAL
        interval = {'MENSAL': 1, 'BIMESTRAL': 2, 'TRIMESTRAL': 3, 'SEMESTRAL': 6, 'ANUAL': 12}.get(freq, 1)
        months_since_start = (year - contract.start_date.year) * 12 + (month - contract.start_date.month)
        if months_since_start >= 0 and months_since_start % interval == 0:
            day = min(contract.start_date.day, _cal.monthrange(year, month)[1])
            d = _date(year, month, day)
            if d >= contract.start_date and (not contract.end_date or d <= contract.end_date):
                dates_to_create.append(d)

    for d in dates_to_create:
        if d not in existing_dates:
            MaintenanceVisit.objects.create(
                contract=contract,
                scheduled_date=d,
                executed_by=contract.primary_technician,
                status=MaintenanceVisit.Status.AGENDADA,
            )


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

        # Métodos de Pagamento reais
        payment_methods = PaymentMethod.objects.filter(ativo=True)

        # Cobranças e Parcelas (Apenas as vinculadas às OSs baixadas)
        billings = Billing.objects.filter(service_order_id__in=order_ids)
        installments = Installment.objects.filter(billing__in=billings)

        # Auto-gera visitas do mês atual para contratos ativos do técnico
        from django.db.models import Q as MQ
        active_contracts = MaintenanceContract.objects.filter(
            primary_technician=professional,
            status='ATIVO',
            start_date__lte=now.date(),
        ).select_related('asset')
        for _contract in active_contracts:
            if not _contract.end_date or _contract.end_date >= now.date():
                _auto_generate_visits_for_contract(_contract, now.month, now.year)

        # Visitas de manutenção do técnico (últimos 7 dias + futuras)
        maintenance_visits_qs = MaintenanceVisit.objects.filter(
            MQ(executed_by=professional) | MQ(contract__primary_technician=professional),
            scheduled_date__gte=now.date() - timezone.timedelta(days=7),
        ).exclude(
            status=MaintenanceVisit.Status.CANCELADA
        ).select_related(
            'contract__asset__client_property__client',
            'contract__asset__category',
            'contract__primary_technician',
        ).distinct()

        def _maint_status_to_app(s):
            return {'AGENDADA': 'AGENDADO', 'EM_ANDAMENTO': 'EM_ANDAMENTO', 'CONCLUIDA': 'CONCLUIDO'}.get(s, 'AGENDADO')

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
                    'CONCLUIDO': r.completed,
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
            'payment_methods': [
                {
                    'id': pm.id,
                    'descricao': pm.descricao,
                } for pm in payment_methods
            ],
            'billings': [
                {
                    'id': str(b.id),
                    'service_order_id': str(b.service_order_id),
                    'number': b.number,
                    'status': b.status,
                    'total_amount': str(b.total_amount),
                    'discount': str(b.discount),
                } for b in billings
            ],
            'installments': [
                {
                    'id': inst.id,
                    'billing_id': str(inst.billing_id),
                    'installment_number': inst.installment_number,
                    'due_date': inst.due_date.isoformat(),
                    'amount': str(inst.amount),
                    'status': inst.status,
                } for inst in installments
            ],
            'config': {
                'company_name': sys_config.company_name,
                'pix_key': sys_config.pix_key,
                'pix_bank': sys_config.pix_bank,
            },
            'maintenance_visits': [
                {
                    'id': str(v.id),
                    'contract_id': str(v.contract_id),
                    'status': _maint_status_to_app(v.status),
                    'scheduled_at': f"{v.scheduled_date.isoformat()}T08:00:00",
                    'check_in_at': v.check_in_at.isoformat() if v.check_in_at else None,
                    'check_out_at': v.check_out_at.isoformat() if v.check_out_at else None,
                    'notes': v.notes or '',
                    'asset_name': v.contract.asset.name,
                    'asset_category': v.contract.asset.category.name if v.contract.asset.category_id else '',
                    'client_name': v.contract.asset.client_property.client.display_name,
                    'property_address': v.contract.asset.client_property.full_address,
                    'client_phone': '',
                    'property_lat': float(v.contract.asset.client_property.latitude) if v.contract.asset.client_property.latitude else None,
                    'property_lng': float(v.contract.asset.client_property.longitude) if v.contract.asset.client_property.longitude else None,
                } for v in maintenance_visits_qs
            ],
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

                # --- Visitas de Manutenção ---
                if change_type == 'MAINTENANCE_VISIT_START':
                    visit_id = payload.get('visit_id')
                    if not visit_id:
                        continue
                    visit = get_object_or_404(MaintenanceVisit, id=visit_id)
                    visit.status = MaintenanceVisit.Status.EM_ANDAMENTO
                    visit.check_in_at = payload.get('started_at') or timezone.now()
                    visit.save(update_fields=['status', 'check_in_at', 'updated_at'])
                    processed_count += 1
                    continue

                elif change_type == 'MAINTENANCE_VISIT_FINISH':
                    visit_id = payload.get('visit_id')
                    if not visit_id:
                        continue
                    visit = get_object_or_404(MaintenanceVisit, id=visit_id)
                    visit.status = MaintenanceVisit.Status.CONCLUIDA
                    visit.check_out_at = payload.get('finished_at') or timezone.now()
                    if payload.get('notes'):
                        visit.notes = payload.get('notes')
                    visit.save(update_fields=['status', 'check_out_at', 'notes', 'updated_at'])
                    processed_count += 1
                    continue

                # --- OS Tasks ---
                task_id = payload.get('task_id')

                if not task_id:
                    continue

                task = get_object_or_404(ServiceOrderTask, id=task_id)
                
                # 1. Início de Tarefa
                if change_type == 'TASK_START':
                    task.status = ServiceOrderTask.TaskStatus.EM_ANDAMENTO
                    if payload.get('started_at'):
                        task.started_at = payload.get('started_at')
                    task.save()
                    processed_count += 1
                    
                # 2. Finalização de Tarefa
                elif change_type == 'TASK_FINISH':
                    finish_data = payload.get('data', {})
                    task.status = ServiceOrderTask.TaskStatus.CONCLUIDO
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
                    
                    # Processa Pagamento Centralizado
                    payment_data = finish_data.get('payment')
                    if payment_data:
                        try:
                            amount = Decimal(str(payment_data.get('amount', 0)))
                            method_code = payment_data.get('method')
                            
                            if amount > 0:
                                # Garante a existência da cobrança centralizada
                                billing = create_billing_for_os(task.service_order)
                                
                                # Tenta mapear o método de pagamento (CASH, PIX, etc. vindo do mobile)
                                payment_method = PaymentMethod.objects.filter(
                                    Q(descricao__iexact=method_code) | Q(ativo=True)
                                ).first()

                                # Registra o pagamento sem sobrescrever o valor da parcela
                                installment = billing.installments.filter(
                                    status__in=[Installment.Status.PENDENTE, Installment.Status.PARCIAL]
                                ).first()
                                if installment and payment_method:
                                    from .models import SalePayment
                                    SalePayment.objects.create(
                                        os=task.service_order,
                                        installment=installment,
                                        metodo_pagamento=payment_method,
                                        valor_bruto=amount,
                                        valor_tarifa=Decimal('0.00'),
                                        valor_liquido=amount,
                                        data_pagamento=task.finished_at or timezone.now(),
                                        data_previsao=(task.finished_at or timezone.now()).date(),
                                    )
                                    total_paid_inst = installment.get_total_paid()
                                    if total_paid_inst >= installment.amount:
                                        installment.status = Installment.Status.PAGO
                                        installment.paid_at = task.finished_at or timezone.now()
                                    elif total_paid_inst > 0:
                                        installment.status = Installment.Status.PARCIAL
                                    installment.save()

                                    remaining = billing.get_remaining_balance()
                                    billing.status = Billing.Status.PAGO if remaining <= 0 else Billing.Status.PARCIAL
                                    billing.save()

                                # Mantém compatibilidade com ServicePayment legado para relatórios antigos se necessário
                                try:
                                    professional = request.user.professional_profile
                                except: professional = None
                                
                                ServicePayment.objects.create(
                                    order=task.service_order,
                                    amount=amount,
                                    payment_method=method_code,
                                    paid_at=task.finished_at or timezone.now(),
                                    received_by=professional,
                                    status=ServicePayment.PaymentStatus.CONFIRMADO, # Técnico recebeu na mão
                                    notes=f"[Sinc Centralizado]: Vinculado à Cobrança #{billing.number}"
                                )
                        except Exception as pay_err:
                            print(f"Erro ao salvar faturamento centralizado offline: {pay_err}")

                    task.save()
                    if hasattr(task.service_order, 'update_status'):
                        task.service_order.update_status()
                    processed_count += 1
                    
                # 3. Atualização de Checklist
                elif change_type == 'CHECKLIST_UPDATE':
                    item_data = payload.get('data', {})
                    response_id = item_data.get('response_id')
                    if response_id:
                        response = get_object_or_404(TaskChecklistResponse, id=response_id)
                        if 'CONCLUIDO' in item_data:
                            response.completed = item_data['CONCLUIDO']
                        if 'text_response' in item_data:
                            response.text_response = item_data['text_response']
                        response.save()
                        processed_count += 1
                
                # 4. Criação de Ocorrência
                elif change_type == 'OCCURRENCE_CREATE':
                    occ_data = payload.get('data', {})
                    occ = Occurrence.objects.create(
                        task=task,
                        category=occ_data.get('category') or Occurrence.OccurrenceCategory.GERAL,
                        occurrence_type=occ_data.get('occurrence_type') or Occurrence.OccurrenceType.OUTRO,
                        description=occ_data.get('description', ''),
                        status=Occurrence.OccurrenceStatus.REGISTRADA
                    )
                    # Se houver um ID temporário local, podemos retornar para o cliente se necessário
                    # Mas o importante é que mídias vinculadas a esta ocorrência usem o ID real depois.
                    # Para simplificar, o upload de mídia de ocorrência pode ser tratado separadamente.
                    processed_count += 1
                
                # 5. Serviço registrado como incompleto pelo técnico
                elif change_type == 'TASK_INCOMPLETE':
                    incomplete_data = payload.get('data', {})
                    task.status = ServiceOrderTask.TaskStatus.PARCIALMENTE_EXECUTADO
                    if incomplete_data.get('notes'):
                        task.notes = (task.notes or '') + '\n\n[Parcial]: ' + incomplete_data['notes']
                    task.save(update_fields=['status', 'notes'])
                    processed_count += 1

                # 6. Outros tipos podem ser adicionados aqui
                
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
        if occurrence_id and occurrence_id not in ('null', '', 'undefined'):
            try:
                occurrence = Occurrence.objects.filter(id=occurrence_id).first()
            except (ValueError, TypeError):
                # ID local do Dexie (inteiro) não corresponde a um UUID do servidor — ignora sem erro
                occurrence = None

        raw_path, file_info = save_upload_for_processing(file)

        job = MediaProcessingJob.objects.create(
            task=task,
            response=response,
            occurrence=occurrence,
            raw_path=raw_path,
            original_name=file_info.name,
            content_type=file_info.content_type,
            status=MediaProcessingJob.Status.PENDENTE,
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


@login_required
def api_tecnico_upload_maintenance_media(request, visit_id):
    """Upload de mídia (foto/vídeo) para uma visita de manutenção."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)

    try:
        visit = get_object_or_404(MaintenanceVisit, id=visit_id)
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'error': 'Nenhum arquivo enviado'}, status=400)

        media = MaintenanceVisitMedia(visit=visit, file_type=file.content_type)
        media.file.save(file.name, file, save=True)
        return JsonResponse({'success': True, 'media_id': str(media.id)}, status=201)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=400)
