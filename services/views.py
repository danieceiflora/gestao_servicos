from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.db.models import Q
from datetime import timedelta, datetime
import django.utils.timezone
from .models import (
    User, Client, Property, ServiceOrder, ServiceMedia, ServiceItem, 
    Professional, ProfessionalRole, ServiceOrderTeam, ProfessionalScheduleBlock,
    ServiceOrderTask
)
from .forms import (
    ClientForm, PhoneFormSet, EmailFormSet, PropertyFormSet, PropertyForm,
    ServiceOrderSchedulingForm, ServiceOrderForm, ServiceInspectionForm,
    ServiceItemFormSet, ProfessionalForm, AvailabilityFormSet,
    ServiceOrderTeamFormSet, TaskScheduleForm, TaskCancelForm
)
from .utils import check_professional_availability

# --- AUXILIARES DE FILTRAGEM ---

def get_orders_queryset(request):
    """Retorna o queryset de OS filtrado pelo papel do usuário"""
    user = request.user
    if user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]:
        return ServiceOrder.objects.all()
    
    # Colaboradores vêem apenas OS onde estão na equipe de alguma task
    try:
        professional = user.professional_profile
        return ServiceOrder.objects.filter(tasks__team_members__professional=professional).distinct()
    except Professional.DoesNotExist:
        return ServiceOrder.objects.none()

class ProfessionalListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Professional
    template_name = 'services/professionals/professional_list.html'
    context_object_name = 'professionals'
    permission_required = 'services.view_professional'

class ProfessionalCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = 'services/professionals/professional_form.html'
    success_url = reverse_lazy('professional_list')
    permission_required = 'services.add_professional'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['availabilities'] = AvailabilityFormSet(self.request.POST)
        else:
            data['availabilities'] = AvailabilityFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        availabilities = context['availabilities']
        if availabilities.is_valid():
            self.object = form.save()
            availabilities.instance = self.object
            availabilities.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

class ProfessionalUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = 'services/professionals/professional_form.html'
    success_url = reverse_lazy('professional_list')
    permission_required = 'services.change_professional'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['availabilities'] = AvailabilityFormSet(self.request.POST, instance=self.object)
        else:
            data['availabilities'] = AvailabilityFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        availabilities = context['availabilities']
        if availabilities.is_valid():
            self.object = form.save()
            availabilities.instance = self.object
            availabilities.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

@login_required
def home(request):
    orders_qs = get_orders_queryset(request)
    active_orders = orders_qs.exclude(status__in=[ServiceOrder.Status.FINISHED, ServiceOrder.Status.CANCELLED]).count()
    pending_approval = orders_qs.filter(status=ServiceOrder.Status.WAITING_APPROVAL).count()
    waiting_execution = orders_qs.filter(status=ServiceOrder.Status.WAITING_EXECUTION).count()
    
    recent_orders = orders_qs.all().order_by('-updated_at')[:5]
    
    return render(request, 'services/home.html', {
        'active_orders': active_orders,
        'pending_approval': pending_approval,
        'waiting_execution': waiting_execution,
        'recent_orders': recent_orders
    })

@login_required
@permission_required('services.view_client', raise_exception=True)
def client_list(request):
    clients = Client.objects.all().order_by('-created_at')
    
    # Filtro de busca
    search = request.GET.get('search')
    if search:
        clients = clients.filter(
            Q(name__icontains=search) |
            Q(cpf__icontains=search) |
            Q(cnpj__icontains=search) |
            Q(phones__phone__icontains=search) |
            Q(properties__address__icontains=search) |
            Q(properties__neighborhood__icontains=search) |
            Q(properties__city__icontains=search)
        ).distinct()
    
    return render(request, 'services/clients/client_list.html', {
        'clients': clients,
        'search': search
    })

@login_required
@permission_required('services.add_client', raise_exception=True)
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        phone_formset = PhoneFormSet(request.POST, prefix='phones')
        email_formset = EmailFormSet(request.POST, prefix='emails')
        property_formset = PropertyFormSet(request.POST, prefix='properties')

        if form.is_valid() and phone_formset.is_valid() and email_formset.is_valid() and property_formset.is_valid():
            client = form.save()
            phone_formset.instance = client
            phone_formset.save()
            email_formset.instance = client
            email_formset.save()
            property_formset.instance = client
            property_formset.save()
            
            if request.GET.get('popup'):
                return render(request, 'services/components/popup_success.html', {
                    'object': client,
                    'model': 'client'
                })

            messages.success(request, 'Cliente e Imóveis cadastrados com sucesso!')
            return redirect('client_list')
    else:
        form = ClientForm()
        phone_formset = PhoneFormSet(prefix='phones')
        email_formset = EmailFormSet(prefix='emails')
        property_formset = PropertyFormSet(prefix='properties')

    return render(request, 'services/clients/client_form.html', {
        'form': form,
        'phone_formset': phone_formset,
        'email_formset': email_formset,
        'property_formset': property_formset,
        'title': 'Novo Cadastro'
    })

@login_required
@permission_required('services.change_client', raise_exception=True)
def client_edit(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        phone_formset = PhoneFormSet(request.POST, instance=client, prefix='phones')
        email_formset = EmailFormSet(request.POST, instance=client, prefix='emails')
        property_formset = PropertyFormSet(request.POST, instance=client, prefix='properties')

        if form.is_valid() and phone_formset.is_valid() and email_formset.is_valid() and property_formset.is_valid():
            form.save()
            phone_formset.save()
            email_formset.save()
            property_formset.save()
            messages.success(request, 'Dados do cliente atualizados!')
            return redirect('client_list')
    else:
        form = ClientForm(instance=client)
        phone_formset = PhoneFormSet(instance=client, prefix='phones')
        email_formset = EmailFormSet(instance=client, prefix='emails')
        property_formset = PropertyFormSet(instance=client, prefix='properties')

    return render(request, 'services/clients/client_form.html', {
        'form': form,
        'phone_formset': phone_formset,
        'email_formset': email_formset,
        'property_formset': property_formset,
        'title': f'Editar: {client.name}'
    })

@login_required
@permission_required('services.add_property', raise_exception=True)
def property_create(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = PropertyForm(request.POST)
        if form.is_valid():
            property_obj = form.save(commit=False)
            property_obj.client = client
            property_obj.save()
            
            if request.GET.get('popup'):
                return render(request, 'services/components/popup_success.html', {
                    'object': property_obj,
                    'model': 'property'
                })

            messages.success(request, 'Imóvel cadastrado com sucesso!')
            return redirect('client_list')
    else:
        form = PropertyForm()

    return render(request, 'services/clients/property_form.html', {
        'form': form,
        'client': client,
        'title': f'Novo Imóvel para {client.name}'
    })

# --- SERVICE ORDER VIEWS ---

@login_required
def service_order_list(request):
    query = request.GET.get('q')
    orders = get_orders_queryset(request).order_by('-created_at')
    
    if query:
        orders = orders.filter(
            Q(client_property__client__name__icontains=query) |
            Q(client_property__address__icontains=query) |
            Q(client_property__number__icontains=query) |
            Q(id__icontains=query)
        ).distinct()
        
    return render(request, 'services/orders/order_list.html', {'orders': orders, 'query': query})

@login_required
@permission_required('services.add_serviceorder', raise_exception=True)
def service_order_scheduling(request):
    team_formset = ServiceOrderTeamFormSet()
    
    # Capturar data/hora da URL se fornecida
    scheduled_at_param = request.GET.get('scheduled_at')
    initial_scheduled_at = None
    if scheduled_at_param:
        try:
            # Parse da data/hora do formato ISO
            initial_scheduled_at = datetime.fromisoformat(scheduled_at_param.replace('Z', '+00:00'))
            if django.utils.timezone.is_naive(initial_scheduled_at):
                initial_scheduled_at = django.utils.timezone.make_aware(initial_scheduled_at)
        except (ValueError, TypeError):
            initial_scheduled_at = None
    
    # Data de origem sempre será hoje
    initial_origin_date = django.utils.timezone.now().date()
    
    if request.method == 'POST':
        form = ServiceOrderSchedulingForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Criar a Ordem de Serviço
            service_order = form.save(commit=False)
            
            # Determinar status inicial baseado nas etapas
            first_task_type = request.POST.get('task_0_type')
            if first_task_type == ServiceOrderTask.TaskType.BUDGET:
                service_order.status = ServiceOrder.Status.BUDGET_SCHEDULED
            else:
                service_order.status = ServiceOrder.Status.WAITING_EXECUTION
            
            service_order.save()
            
            # Processar todas as etapas (tasks)
            task_index = 0
            tasks_created = []
            
            while f'task_{task_index}_type' in request.POST:
                task_type = request.POST.get(f'task_{task_index}_type')
                scheduled_input = request.POST.get(f'task_{task_index}_scheduled')
                start_date = request.POST.get(f'task_{task_index}_start_date')
                end_date = request.POST.get(f'task_{task_index}_end_date')
                value = request.POST.get(f'task_{task_index}_value')
                
                scheduled_datetime = None
                if scheduled_input:
                    scheduled_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(scheduled_input))
                elif task_index == 0:
                    scheduled_datetime = form.cleaned_data.get('scheduled_at')
                    if scheduled_datetime and django.utils.timezone.is_naive(scheduled_datetime):
                        scheduled_datetime = django.utils.timezone.make_aware(scheduled_datetime)
                
                start_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(start_date)) if start_date else None
                end_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(end_date)) if end_date else None
                
                if task_type and scheduled_datetime:
                    # Criar a tarefa
                    task = ServiceOrderTask.objects.create(
                        service_order=service_order,
                        task_type=task_type,
                        scheduled_at=scheduled_datetime,
                        started_at=start_datetime,
                        finished_at=end_datetime,
                        value=float(value) if value else None,
                        status=ServiceOrderTask.TaskStatus.SCHEDULED
                    )
                    
                    # Processar equipe específica desta etapa
                    professionals = request.POST.getlist(f'task_{task_index}_professional[]')
                    roles = request.POST.getlist(f'task_{task_index}_role[]')
                    
                    for prof_id, role_id in zip(professionals, roles):
                        if prof_id and role_id:  # Ignorar campos vazios
                            try:
                                professional = Professional.objects.get(id=prof_id)
                                role = ProfessionalRole.objects.get(id=role_id)
                                ServiceOrderTeam.objects.create(
                                    task=task,
                                    professional=professional,
                                    role=role
                                )
                            except (Professional.DoesNotExist, ProfessionalRole.DoesNotExist):
                                pass
                    
                    # Anexar mídias à etapa
                    media_files = request.FILES.getlist(f'task_{task_index}_media')
                    for media in media_files:
                        ServiceMedia.objects.create(task=task, file=media)
                    
                    tasks_created.append(task)
                
                task_index += 1
            
            messages.success(request, f'Ordem de Serviço criada com sucesso! {len(tasks_created)} etapa(s) adicionada(s).')
            
            # Se for um popup (modal), retornar mensagem de sucesso
            if request.GET.get('popup'):
                return render(request, 'services/components/popup_success.html', {
                    'message': 'Agendamento criado com sucesso!',
                    'type': 'schedulingComplete'
                })
            
            return redirect('service_order_detail', order_id=service_order.id)
        else:
            messages.error(request, 'Por favor, corrija os erros no formulário.')
    else:
        form = ServiceOrderSchedulingForm()
        # Se não tiver data de origem da URL, usar hoje por padrão
        if not initial_origin_date:
            initial_origin_date = django.utils.timezone.now().date()
    
    return render(request, 'services/orders/order_scheduling_form.html', {
        'form': form,
        'formset': team_formset,
        'professionals': Professional.objects.filter(is_active=True),
        'roles': ProfessionalRole.objects.all(),
        'title': 'Novo Agendamento',
        'initial_scheduled_at': initial_scheduled_at.isoformat() if initial_scheduled_at else None,
        'initial_origin_date': initial_origin_date.isoformat() if initial_origin_date else None
    })

def service_order_create(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)
    if request.method == 'POST':
        form = ServiceInspectionForm(request.POST, request.FILES) 
        if form.is_valid():
            service_order = ServiceOrder.objects.create(
                client_property=property_obj,
                status=ServiceOrder.Status.WAITING_BUDGET
            )
            task = form.save(commit=False)
            task.service_order = service_order
            task.task_type = ServiceOrderTask.TaskType.BUDGET
            task.status = ServiceOrderTask.TaskStatus.COMPLETED
            task.scheduled_at = django.utils.timezone.now()
            task.finished_at = django.utils.timezone.now()
            task.save()
            
            files = request.FILES.getlist('files')
            for f in files:
                ServiceMedia.objects.create(task=task, file=f)
            
            messages.success(request, 'Vistoria registrada com sucesso!')
            return redirect('service_order_list')
    else:
        form = ServiceInspectionForm()
    
    return render(request, 'services/orders/service_order_form.html', {
        'form': form,
        'property': property_obj,
        'title': 'Nova Vistoria'
    })

def service_order_budget(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    budget_task = order.tasks.filter(task_type=ServiceOrderTask.TaskType.BUDGET).first()

    if request.method == 'POST':
        form = ServiceOrderForm(request.POST, instance=order)
        formset = ServiceItemFormSet(request.POST, instance=order)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            
            if order.status in [ServiceOrder.Status.WAITING_BUDGET, ServiceOrder.Status.BUDGET_SCHEDULED] and order.items.exists():
                order.status = ServiceOrder.Status.WAITING_APPROVAL
                order.save()
                
            messages.success(request, 'Orçamento atualizado!')
            return redirect('service_order_list')
    else:
        form = ServiceOrderForm(instance=order)
        formset = ServiceItemFormSet(instance=order)
    
    return render(request, 'services/orders/service_budget_form.html', {
        'order': order,
        'form': form,
        'formset': formset,
        'budget_task': budget_task,
        'title': 'Elaborar Orçamento'
    })

@login_required
@permission_required('services.view_serviceorder', raise_exception=True)
def service_order_detail(request, order_id):
    order = get_object_or_404(get_orders_queryset(request), id=order_id)
    tasks = order.tasks.all().prefetch_related('team_members__professional', 'medias')
    return render(request, 'services/orders/order_detail.html', {'order': order, 'tasks': tasks})

@login_required
@permission_required('services.change_serviceorder', raise_exception=True)
def service_order_edit(request, order_id):
    """View completa para editar toda a OS (info, itens, etapas)"""
    order = get_object_or_404(ServiceOrder, id=order_id)
    tasks = order.tasks.all().order_by('scheduled_at')
    items = order.items.all()
    items_total = sum(item.total_price for item in items)
    
    if request.method == 'POST':
        form = ServiceOrderSchedulingForm(request.POST, instance=order)
        
        if form.is_valid():
            # Atualiza a OS
            service_order = form.save()
            
            messages.success(request, 'Ordem de Serviço atualizada com sucesso!')
            return redirect('service_order_detail', order_id=service_order.id)
        else:
            messages.error(request, 'Por favor, corrija os erros no formulário.')
    else:
        form = ServiceOrderSchedulingForm(instance=order)
    
    return render(request, 'services/orders/order_edit.html', {
        'form': form,
        'order': order,
        'tasks': tasks,
        'items': items,
        'items_total': items_total,
        'professionals': Professional.objects.filter(is_active=True),
        'roles': ProfessionalRole.objects.all(),
        'title': f'Editar OS #{order.id.hex[:8]}'
    })

@login_required
def task_execution(request, task_id):
    """
    View principal para execução de uma Task específica.
    Permite iniciar, adicionar mídias e finalizar a etapa.
    """
    # Verifica se a task pertence a uma OS que o usuário pode ver
    orders_qs = get_orders_queryset(request)
    task = get_object_or_404(ServiceOrderTask, id=task_id, service_order__in=orders_qs)
    order = task.service_order
    
    if task.status in [ServiceOrderTask.TaskStatus.COMPLETED, ServiceOrderTask.TaskStatus.CANCELLED]:
        messages.warning(request, "Esta etapa já foi concluída ou cancelada.")
        return redirect('service_order_detail', order_id=order.id)

    if request.method == 'POST':
        if 'start_task' in request.POST:
            task.status = ServiceOrderTask.TaskStatus.IN_PROGRESS
            task.started_at = django.utils.timezone.now()
            task.save()
            messages.success(request, f'{task.get_task_type_display()} iniciado(a)!')
        elif 'finish_task' in request.POST:
            task.status = ServiceOrderTask.TaskStatus.COMPLETED
            task.finished_at = django.utils.timezone.now()
            task.notes = request.POST.get('notes', '')
            task.save()
            
            # Atualizar status da OS apenas se todas as tasks foram concluídas
            pending_tasks = order.tasks.exclude(
                status__in=[ServiceOrderTask.TaskStatus.COMPLETED, ServiceOrderTask.TaskStatus.CANCELLED]
            )
            if not pending_tasks.exists():
                from datetime import timedelta
                order.status = ServiceOrder.Status.FINISHED
                order.finished_at = django.utils.timezone.now()
                # Calcular garantia de 1 ano (365 dias) a partir da data de finalização
                order.warranty_until = order.finished_at.date() + timedelta(days=365)
                order.save()
                messages.success(request, f'Etapa finalizada! Todas as etapas da OS foram concluídas. Garantia válida até {order.warranty_until.strftime("%d/%m/%Y")}.')
            else:
                messages.success(request, 'Etapa finalizada com sucesso!')
            
            return redirect('service_order_detail', order_id=order.id)
            
        # Upload de mídias (fotos/vídeos)
        files = request.FILES.getlist('files')
        for f in files:
            ServiceMedia.objects.create(task=task, file=f)
        if files:
            messages.success(request, f'{len(files)} arquivo(s) adicionado(s) com sucesso!')

    return render(request, 'services/orders/order_execution.html', {
        'order': order,
        'task': task,
        'title': f'Execução - {task.get_task_type_display()}'
    })

@login_required
def service_order_execution(request, order_id):
    """
    View legacy para compatibilidade. Redireciona para a primeira task pendente.
    """
    orders_qs = get_orders_queryset(request)
    order = get_object_or_404(orders_qs, id=order_id)
    task = order.tasks.exclude(
        status__in=[ServiceOrderTask.TaskStatus.COMPLETED, ServiceOrderTask.TaskStatus.CANCELLED]
    ).order_by('scheduled_at').first()
    
    if not task:
        messages.warning(request, "Não há etapas pendentes para esta OS.")
        return redirect('service_order_detail', order_id=order.id)
    
    return redirect('task_execution', task_id=task.id)

# --- TASK MANAGEMENT VIEWS ---

@login_required
@permission_required('services.add_serviceordertask', raise_exception=True)
def task_add(request, order_id):
    """
    View para adicionar uma nova Task (etapa) a uma OS existente.
    """
    order = get_object_or_404(ServiceOrder.objects.all(), id=order_id)
    
    if request.method == 'POST':
        form = TaskScheduleForm(request.POST, request.FILES)
        formset = ServiceOrderTeamFormSet(request.POST, request.FILES)
        
        if form.is_valid() and formset.is_valid():
            task = form.save(commit=False)
            task.service_order = order
            task.status = ServiceOrderTask.TaskStatus.SCHEDULED
            
            # Validar disponibilidade da equipe
            scheduled_at = form.cleaned_data.get('scheduled_at')
            team_data = [f for f in formset.cleaned_data if f and not f.get('DELETE')]
            
            for team_form in team_data:
                professional = team_form.get('professional')
                if professional:
                    available, msg = check_professional_availability(professional, scheduled_at)
                    if not available:
                        messages.error(request, f"Conflito de agenda: {msg}")
                        return render(request, 'services/tasks/task_form.html', {
                            'form': form,
                            'formset': formset,
                            'order': order,
                            'title': 'Adicionar Nova Etapa'
                        })
            
            task.save()
            
            # Salvar equipe
            formset.instance = task
            formset.save()
            
            # Processar arquivos de mídia (fotos/vídeos)
            files = request.FILES.getlist('files')
            for file in files:
                ServiceMedia.objects.create(task=task, file=file)
            
            messages.success(request, f'{task.get_task_type_display()} agendado(a) com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
    else:
        form = TaskScheduleForm()
        formset = ServiceOrderTeamFormSet()
    
    return render(request, 'services/tasks/task_form.html', {
        'form': form,
        'formset': formset,
        'order': order,
        'title': 'Adicionar Nova Etapa'
    })

@login_required
@permission_required('services.change_serviceordertask', raise_exception=True)
def task_edit(request, task_id):
    """
    View para editar uma Task existente (data, hora, equipe).
    """
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order = task.service_order
    existing_medias = task.medias.all()
    
    if task.status == ServiceOrderTask.TaskStatus.COMPLETED:
        messages.warning(request, "Não é possível editar uma etapa já concluída.")
        return redirect('service_order_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = TaskScheduleForm(request.POST, request.FILES, instance=task)
        formset = ServiceOrderTeamFormSet(request.POST, request.FILES, instance=task)
        
        if form.is_valid() and formset.is_valid():
            scheduled_at = form.cleaned_data.get('scheduled_at')
            team_data = [f for f in formset.cleaned_data if f and not f.get('DELETE')]
            
            # Validar disponibilidade da equipe (excluindo a task atual)
            for team_form in team_data:
                professional = team_form.get('professional')
                if professional:
                    available, msg = check_professional_availability(
                        professional, scheduled_at, exclude_task_id=task.id
                    )
                    if not available:
                        messages.error(request, f"Conflito de agenda: {msg}")
                        return render(request, 'services/tasks/task_form.html', {
                            'form': form,
                            'formset': formset,
                            'order': order,
                            'task': task,
                            'existing_medias': existing_medias,
                            'title': 'Editar Etapa'
                        })
            
            form.save()
            formset.save()
            
            # Processar novos arquivos de mídia
            files = request.FILES.getlist('files')
            for file in files:
                ServiceMedia.objects.create(task=task, file=file)
            
            messages.success(request, 'Etapa atualizada com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
    else:
        form = TaskScheduleForm(instance=task)
        formset = ServiceOrderTeamFormSet(instance=task)
    
    return render(request, 'services/tasks/task_form.html', {
        'form': form,
        'formset': formset,
        'order': order,
        'task': task,
        'existing_medias': existing_medias,
        'title': 'Editar Etapa'
    })

@login_required
@permission_required('services.change_serviceordertask', raise_exception=True)
def task_cancel(request, task_id):
    """
    View para cancelar uma Task com justificativa.
    """
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order = task.service_order
    
    if task.status == ServiceOrderTask.TaskStatus.COMPLETED:
        messages.warning(request, "Não é possível cancelar uma etapa já concluída.")
        return redirect('service_order_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = TaskCancelForm(request.POST)
        if form.is_valid():
            cancel_reason = form.cleaned_data.get('cancel_reason')
            task.status = ServiceOrderTask.TaskStatus.CANCELLED
            task.notes = f"[CANCELADO] {cancel_reason}\n\n{task.notes}"
            task.save()
            
            messages.success(request, 'Etapa cancelada com sucesso.')
            return redirect('service_order_detail', order_id=order.id)
    else:
        form = TaskCancelForm()
    
    return render(request, 'services/tasks/task_cancel.html', {
        'form': form,
        'task': task,
        'order': order,
        'title': 'Cancelar Etapa'
    })

from django.http import JsonResponse
from dateutil.parser import parse

@login_required
def api_calendar_events(request):
    events = []
    buffer = timedelta(hours=1, minutes=30)
    user = request.user
    
    # Se for colaborador, ele só vê os próprios eventos, independente do filtro
    if not (user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]):
        try:
            prof_id = user.professional_profile.id
        except Professional.DoesNotExist:
            return JsonResponse([], safe=False)
    else:
        prof_id = request.GET.get('professional_id')
    
    tasks = ServiceOrderTask.objects.select_related('service_order__client_property__client')
    if prof_id:
        tasks = tasks.filter(team_members__professional_id=prof_id)

    for task in tasks:
        colors = {
            'BUDGET': ('#3b82f6', '#2563eb', 'ORÇ'),
            'EXECUTION': ('#10b981', '#059669', 'EXEC'),
            'WARRANTY': ('#f59e0b', '#d97706', 'GAR'),
        }
        bg, border, prefix = colors.get(task.task_type, ('#64748b', '#475569', 'TSK'))
        events.append({
            'id': f"task-{task.id}",
            'title': f"{prefix}: {task.service_order.client_property.client.name}",
            'start': task.scheduled_at.isoformat(),
            'end': (task.scheduled_at + buffer).isoformat(),
            'backgroundColor': bg,
            'borderColor': border,
            'url': reverse_lazy('service_order_detail', kwargs={'order_id': task.service_order.id}),
        })

    blocks = ProfessionalScheduleBlock.objects.all()
    if prof_id:
        blocks = blocks.filter(professional_id=prof_id)
    for block in blocks:
        events.append({
            'id': f"block-{block.id}",
            'title': f"BLOQUEIO: {block.professional.name}",
            'start': block.start_at.isoformat(),
            'end': block.end_at.isoformat(),
            'backgroundColor': '#64748b',
            'allDay': block.is_all_day,
        })
    return JsonResponse(events, safe=False)

@login_required
def service_order_calendar(request):
    return render(request, 'services/orders/calendar.html', {
        'professionals': Professional.objects.filter(is_active=True),
        'professional_roles': ProfessionalRole.objects.all(),
        'status_choices': ServiceOrder.Status.choices,
        'title': 'Agenda'
    })

@login_required
def api_check_availability(request):
    prof_id = request.GET.get('professional_id')
    timestamp_str = request.GET.get('timestamp')
    if not prof_id or not timestamp_str:
        return JsonResponse({'available': True})
    try:
        professional = get_object_or_404(Professional, id=prof_id)
        timestamp = parse(timestamp_str)
        available, message = check_professional_availability(professional, timestamp)
        return JsonResponse({'available': available, 'message': message})
    except:
        return JsonResponse({'available': False})

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

@login_required
@permission_required('services.add_serviceorder', raise_exception=True)
@csrf_exempt
@require_POST
def api_quick_create_order(request):
    try:
        data = json.loads(request.body)
        prop = get_object_or_404(Property, id=data.get('property_id'))
        sched_type = data.get('type', 'BUDGET')
        scheduled_at = parse(data.get('scheduled_at'))
        
        status = ServiceOrder.Status.BUDGET_SCHEDULED if sched_type == 'BUDGET' else ServiceOrder.Status.WAITING_EXECUTION
        order = ServiceOrder.objects.create(client_property=prop, status=status, description=data.get('description', ''))
        
        task = ServiceOrderTask.objects.create(
            service_order=order, task_type=sched_type, 
            scheduled_at=scheduled_at, status=ServiceOrderTask.TaskStatus.SCHEDULED
        )

        for member in data.get('team', []):
            prof = get_object_or_404(Professional, id=member.get('professional_id'))
            role_id = member.get('role_id')
            role = get_object_or_404(ProfessionalRole, id=role_id) if role_id else prof.roles.first()
            ServiceOrderTeam.objects.create(task=task, professional=prof, role=role)

        return JsonResponse({'id': str(order.id), 'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def api_get_properties(request):
    properties = Property.objects.filter(client_id=request.GET.get('client_id'))
    return JsonResponse([{'id': str(p.id), 'address': f"{p.address}, {p.number}"} for p in properties], safe=False)

@login_required
def api_get_clients(request):
    clients = Client.objects.all().order_by('name')
    return JsonResponse([{'id': str(c.id), 'name': c.name} for c in clients], safe=False)


# ============ GERENCIAMENTO DE ITENS DA OS ============

@login_required
@permission_required('services.add_serviceitem', raise_exception=True)
def order_item_add(request, order_id):
    """View para adicionar item ao orçamento geral ou a uma etapa específica"""
    order = get_object_or_404(ServiceOrder, id=order_id)
    tasks = order.tasks.all()
    
    if request.method == 'POST':
        task_id = request.POST.get('task')
        task = get_object_or_404(ServiceOrderTask, id=task_id) if task_id else None
        
        ServiceItem.objects.create(
            service_order=order,
            task=task,
            description=request.POST.get('description'),
            quantity=float(request.POST.get('quantity', 1)),
            unit_price=float(request.POST.get('unit_price', 0))
        )
        
        messages.success(request, 'Item adicionado com sucesso!')
        return redirect('service_order_detail', order_id=order.id)
    
    return render(request, 'services/orders/order_item_form.html', {
        'order': order,
        'tasks': tasks,
        'title': 'Adicionar Item ao Orçamento'
    })

@login_required
@permission_required('services.delete_serviceitem', raise_exception=True)
def order_item_delete(request, item_id):
    """View para remover item"""
    item = get_object_or_404(ServiceItem, id=item_id)
    order_id = item.service_order.id
    
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Item removido com sucesso!')
        return redirect('service_order_detail', order_id=order_id)
    
    return render(request, 'services/orders/order_item_delete.html', {
        'item': item,
        'order': item.service_order
    })

@login_required
@permission_required('services.delete_servicemedia', raise_exception=True)
def task_media_delete(request, media_id):
    """View para remover mídia de uma etapa"""
    media = get_object_or_404(ServiceMedia, id=media_id)
    task = media.task
    order_id = task.service_order.id
    
    if request.method == 'POST':
        # Deletar arquivo físico
        if media.file:
            media.file.delete()
        media.delete()
        messages.success(request, 'Mídia removida com sucesso!')
        return redirect('task_edit', task_id=task.id)
    
    return render(request, 'services/tasks/media_delete.html', {
        'media': media,
        'task': task
    })
