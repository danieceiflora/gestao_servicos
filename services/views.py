from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.urls import reverse_lazy
from django.db.models import Q
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import django.utils.timezone
from .notifications import send_push_notification
from .models import (
    User, Client, Property, ServiceOrder, ServiceMedia, ServiceItem,
    Professional, ProfessionalRole, ServiceOrderTeam, ProfessionalScheduleBlock,
    ServiceOrderTask, ServicePayment, Occurrence, Product
)
from .forms import (
    ClientForm, PhoneFormSet, EmailFormSet, PropertyFormSet, PropertyForm,
    ServiceOrderSchedulingForm, ServiceOrderForm, ServiceInspectionForm,
    ServiceItemFormSet, ProfessionalForm, ProfessionalScheduleBlockForm,
    ServiceOrderTeamFormSet, TaskScheduleForm, TaskCancelForm,
    ServicePaymentForm, ServiceOrderDiscountForm
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


class ProfessionalUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = 'services/professionals/professional_form.html'
    success_url = reverse_lazy('professional_list')
    permission_required = 'services.change_professional'


class ProfessionalScheduleBlockListView(LoginRequiredMixin, ListView):
    model = ProfessionalScheduleBlock
    template_name = 'services/professionals/schedule_block_list.html'
    context_object_name = 'blocks'
    permission_required = 'services.view_scheduleblock'

    def get_queryset(self):
        queryset = super().get_queryset()
        professional_id = self.kwargs.get('professional_id')
        if professional_id:
            queryset = queryset.filter(professional_id=professional_id)
        return queryset

@login_required
def home(request):
    if not request.user.is_manager:
        return redirect('equipe_task_list')

    orders_qs = get_orders_queryset(request)
    active_orders = orders_qs.exclude(status__in=[ServiceOrder.Status.FINISHED, ServiceOrder.Status.CANCELLED]).count()
    pending_approval = orders_qs.filter(status=ServiceOrder.Status.WAITING_APPROVAL).count()
    waiting_execution = orders_qs.filter(status=ServiceOrder.Status.WAITING_EXECUTION).count()
    
    needs_scheduling = orders_qs.filter(
        Q(status=ServiceOrder.Status.APPROVED_WAITING_SCHEDULE) | 
        Q(tasks__status=ServiceOrderTask.TaskStatus.NOT_EXECUTED)
    ).distinct().count()

    recent_orders = orders_qs.all().order_by('-updated_at')[:5]

    layout_base = 'base.html' if request.user.is_manager else 'base_equipe.html'

    return render(request, 'services/home.html', {
        'active_orders': active_orders,
        'pending_approval': pending_approval,
        'waiting_execution': waiting_execution,
        'needs_scheduling': needs_scheduling,
        'recent_orders': recent_orders,
        'layout_base': layout_base,
    })

# --- CLIENT VIEWS ---

@login_required
@permission_required('services.view_client', raise_exception=True)
def client_list(request):
    clients = Client.objects.all().order_by('name')
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
            messages.error(request, 'Erro ao cadastrar cliente. Verifique os campos abaixo.')
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
            messages.success(request, 'Dados do cliente atualizados com sucesso!')
            return redirect('client_list')
        else:
            messages.error(request, 'Erro ao atualizar cliente. Verifique os campos abaixo.')
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
@user_passes_test(lambda u: u.is_superuser or u.role in [User.Roles.ADMIN, User.Roles.MANAGER])
def service_order_list(request):
    query = request.GET.get('q')
    status_filter = request.GET.get('status')
    custom_filter = request.GET.get('filter')
    orders = get_orders_queryset(request).order_by('-created_at')

    if query:
        orders = orders.filter(
            Q(client_property__client__name__icontains=query) |
            Q(client_property__address__icontains=query) |
            Q(client_property__number__icontains=query) |
            Q(id__icontains=query)
        ).distinct()

    if status_filter:
        orders = orders.filter(status=status_filter)

    if custom_filter == 'needs_scheduling':
        orders = orders.filter(
            Q(status=ServiceOrder.Status.APPROVED_WAITING_SCHEDULE) | 
            Q(tasks__status=ServiceOrderTask.TaskStatus.NOT_EXECUTED)
        ).distinct()

    return render(request, 'services/orders/order_list.html', {
        'orders': orders,
        'query': query,
        'status_filter': status_filter,
        'custom_filter': custom_filter,
        'status_choices': ServiceOrder.Status.choices,
    })
@permission_required('services.add_serviceorder', raise_exception=True)
def service_order_scheduling(request):
    team_formset = ServiceOrderTeamFormSet()
    
    # Capturar data/hora da URL se fornecida
    scheduled_at_param = request.GET.get('scheduled_at')
    scheduled_end_at_param = request.GET.get('scheduled_end_at')
    
    # DEBUG: Log dos parâmetros recebidos
    print('=' * 80)
    print('🔍 DEBUG service_order_scheduling - GET params:')
    print(f'   scheduled_at: {scheduled_at_param}')
    print(f'   scheduled_end_at: {scheduled_end_at_param}')
    print('=' * 80)
    
    initial_scheduled_at = None
    if scheduled_at_param:
        try:
            # Parse da data/hora do formato ISO
            initial_scheduled_at = datetime.fromisoformat(scheduled_at_param.replace('Z', '+00:00'))
            if django.utils.timezone.is_naive(initial_scheduled_at):
                initial_scheduled_at = django.utils.timezone.make_aware(initial_scheduled_at)
        except (ValueError, TypeError):
            initial_scheduled_at = None

    initial_scheduled_end_at = None
    if scheduled_end_at_param:
        try:
            initial_scheduled_end_at = datetime.fromisoformat(scheduled_end_at_param.replace('Z', '+00:00'))
            if django.utils.timezone.is_naive(initial_scheduled_end_at):
                initial_scheduled_end_at = django.utils.timezone.make_aware(initial_scheduled_end_at)
        except (ValueError, TypeError):
            initial_scheduled_end_at = None
    
    # DEBUG: Log dos valores finais
    print(f'   initial_scheduled_at final: {initial_scheduled_at}')
    print(f'   initial_scheduled_end_at final: {initial_scheduled_end_at}')
    print('=' * 80)

    # Data de origem sempre será hoje
    initial_origin_date = django.utils.timezone.now().date()
    
    if request.method == 'POST':
        form = ServiceOrderSchedulingForm(request.POST, request.FILES)

        # Coletar tarefas submetidas para manter o estado no form em caso de erro
        submitted_tasks = []
        _idx = 0
        while f'task_{_idx}_type' in request.POST:
            # Para task 0, os campos têm nomes diferentes
            if _idx == 0:
                sched_val = request.POST.get('scheduled_at', '')
                sched_end_val = request.POST.get('scheduled_end_at', '')
            else:
                sched_val = request.POST.get(f'task_{_idx}_scheduled', '')
                sched_end_val = request.POST.get(f'task_{_idx}_scheduled_end', '')
            
            task_data = {
                'index': _idx,
                'type': request.POST.get(f'task_{_idx}_type', ''),
                'scheduled': sched_val,
                'scheduled_end': sched_end_val,
                'start_date': request.POST.get(f'task_{_idx}_start_date', ''),
                'end_date': request.POST.get(f'task_{_idx}_end_date', ''),
                'value': request.POST.get(f'task_{_idx}_value', ''),
                'team': []
            }
            professionals = request.POST.getlist(f'task_{_idx}_professional[]')
            roles = request.POST.getlist(f'task_{_idx}_role[]')
            for prof_id, role_id in zip(professionals, roles):
                if prof_id or role_id:
                    task_data['team'].append({
                        'professional_id': str(prof_id),
                        'role_id': str(role_id)
                    })
            submitted_tasks.append(task_data)
            _idx += 1

        if form.is_valid():
            ignore_working_hours = request.POST.get('ignore_working_hours') == 'true'
            has_conflict = False
            conflict_message = ""
            is_out_of_hours = False

            # PRE-VALIDATE EVERYTHING FIRST BEFORE CREATING DB RECORDS
            task_index = 0
            while f'task_{task_index}_type' in request.POST:
                task_type = request.POST.get(f'task_{task_index}_type')
                
                # Para task 0, o campo se chama 'scheduled_at', não 'task_0_scheduled'
                if task_index == 0:
                    scheduled_input = request.POST.get('scheduled_at')
                else:
                    scheduled_input = request.POST.get(f'task_{task_index}_scheduled')
                
                scheduled_datetime = None
                if scheduled_input:
                    try:
                        scheduled_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(scheduled_input))
                    except (ValueError, TypeError):
                        pass
                elif task_index == 0:
                    scheduled_datetime = form.cleaned_data.get('scheduled_at')
                    if scheduled_datetime and django.utils.timezone.is_naive(scheduled_datetime):
                        scheduled_datetime = django.utils.timezone.make_aware(scheduled_datetime)

                if task_type and scheduled_datetime:
                    # Tentar obter scheduled_end_at para validação
                    if task_index == 0:
                        scheduled_end_input = request.POST.get('scheduled_end_at')
                    else:
                        scheduled_end_input = request.POST.get(f'task_{task_index}_scheduled_end')
                    
                    scheduled_end_datetime = None
                    if scheduled_end_input:
                        try:
                            scheduled_end_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(scheduled_end_input))
                        except (ValueError, TypeError):
                            pass

                    professionals = request.POST.getlist(f'task_{task_index}_professional[]')
                    for prof_id in professionals:
                        if prof_id:
                            try:
                                professional = Professional.objects.get(id=prof_id)
                                available, msg, c_type = check_professional_availability(
                                    professional, scheduled_datetime, 
                                    scheduled_end_at=scheduled_end_datetime,
                                    ignore_working_hours=ignore_working_hours
                                )
                                if not available:
                                    has_conflict = True
                                    conflict_message = msg
                                    if c_type == "OUT_OF_HOURS":
                                        is_out_of_hours = True
                                    break
                            except Professional.DoesNotExist:
                                pass
                if has_conflict:
                    break
                task_index += 1

            if has_conflict:
                if is_out_of_hours:
                    messages.warning(request, f"Aviso de Agenda: {conflict_message} (Confirme para forçar o agendamento).")
                    return render(request, 'services/orders/order_scheduling_form.html', {
                        'form': form,
                        'team_formset': team_formset,
                        'professionals': Professional.objects.filter(is_active=True),
                        'roles': ProfessionalRole.objects.all(),
                        'title': 'Nova OS / Agendamento',
                        'show_force_schedule_modal': True,
                        'force_message': conflict_message,
                        'initial_scheduled_at': initial_scheduled_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_at else None,
                        'initial_scheduled_end_at': initial_scheduled_end_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_end_at else None,
                        'initial_origin_date': initial_origin_date.strftime('%Y-%m-%d') if initial_origin_date else None,
                        'submitted_tasks': submitted_tasks,
                    })
                else:
                    messages.error(request, f"Conflito de agenda: {conflict_message}")
                    return render(request, 'services/orders/order_scheduling_form.html', {
                        'form': form,
                        'team_formset': team_formset,
                        'professionals': Professional.objects.filter(is_active=True),
                        'roles': ProfessionalRole.objects.all(),
                        'title': 'Nova OS / Agendamento',
                        'initial_scheduled_at': initial_scheduled_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_at else None,
                        'initial_scheduled_end_at': initial_scheduled_end_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_end_at else None,
                        'initial_origin_date': initial_origin_date.strftime('%Y-%m-%d') if initial_origin_date else None,
                        'submitted_tasks': submitted_tasks,
                    })

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
                
                # Para task 0, os campos têm nomes diferentes (scheduled_at/scheduled_end_at)
                # Para demais tasks, os campos seguem o padrão task_{index}_scheduled/task_{index}_scheduled_end
                if task_index == 0:
                    scheduled_input = request.POST.get('scheduled_at')
                    scheduled_end_input = request.POST.get('scheduled_end_at')
                else:
                    scheduled_input = request.POST.get(f'task_{task_index}_scheduled')
                    scheduled_end_input = request.POST.get(f'task_{task_index}_scheduled_end')
                
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

                scheduled_end_datetime = None
                if scheduled_end_input:
                    scheduled_end_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(scheduled_end_input))
                elif task_index == 0:
                    scheduled_end_datetime = form.cleaned_data.get('scheduled_end_at')
                    if scheduled_end_datetime and django.utils.timezone.is_naive(scheduled_end_datetime):
                        scheduled_end_datetime = django.utils.timezone.make_aware(scheduled_end_datetime)

                start_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(start_date)) if start_date else None
                end_datetime = django.utils.timezone.make_aware(datetime.fromisoformat(end_date)) if end_date else None

                if task_type and scheduled_datetime:
                    # Criar a tarefa
                    task = ServiceOrderTask.objects.create(
                        service_order=service_order,
                        task_type=task_type,
                        scheduled_at=scheduled_datetime,
                        scheduled_end_at=scheduled_end_datetime,
                    )
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
                                
                                # Notificar o profissional
                                if professional.user:
                                    title = "Nova O.S. Agendada 🛠️"
                                    body = f"Você foi escalado para {task.get_task_type_display()} na O.S. #{service_order.number}\nInício: {task.scheduled_at.strftime('%d/%m/%Y às %H:%M') if task.scheduled_at else 'A definir'}"
                                    send_push_notification(professional.user, title, body, url=f"/equipe/etapa/{task.id}/")

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
            messages.error(request, "Por favor, corrija os erros no formulário.")
            return render(request, 'services/orders/order_scheduling_form.html', {
                'form': form,
                'team_formset': team_formset,
                'professionals': Professional.objects.filter(is_active=True),
                'roles': ProfessionalRole.objects.all(),
                'title': 'Nova OS / Agendamento',
                'initial_scheduled_at': initial_scheduled_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_at else None,
                        'initial_scheduled_end_at': initial_scheduled_end_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_end_at else None,
                'initial_origin_date': initial_origin_date.strftime('%Y-%m-%d') if initial_origin_date else None,
                'submitted_tasks': submitted_tasks,
            })
    else:
        # Pre-selecionar o originador como o profissional logado, se existir
        initial_data = {}
        if hasattr(request.user, 'professional_profile'):
            initial_data['originator'] = request.user.professional_profile

        # Pre-selecionar cliente e imóvel se passados na URL (ex: a partir da lista de clientes)
        property_id = request.GET.get('property_id')
        if property_id:
            try:
                prop = Property.objects.get(id=property_id)
                initial_data['client'] = prop.client
                initial_data['client_property'] = prop
            except Property.DoesNotExist:
                pass
                
        form = ServiceOrderSchedulingForm(initial=initial_data)

        if not initial_origin_date:
            initial_origin_date = django.utils.timezone.now().date()

    return render(request, 'services/orders/order_scheduling_form.html', {
        'form': form,
        'formset': team_formset,
        'professionals': Professional.objects.filter(is_active=True),
        'roles': ProfessionalRole.objects.all(),
        'title': 'Novo Agendamento',
        'initial_scheduled_at': initial_scheduled_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_at else None,
                        'initial_scheduled_end_at': initial_scheduled_end_at.astimezone().strftime('%Y-%m-%dT%H:%M') if initial_scheduled_end_at else None,
        'initial_origin_date': initial_origin_date.strftime('%Y-%m-%d') if initial_origin_date else None
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
    occurrences = Occurrence.objects.filter(task__service_order=order).order_by('-created_at')
    return render(request, 'services/orders/order_detail.html', {'order': order, 'tasks': tasks, 'occurrences': occurrences})

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
        'occurrences': Occurrence.objects.filter(task__service_order=order).order_by('-created_at'),
        'items': items,
        'items_total': items_total,
        'professionals': Professional.objects.filter(is_active=True),
        'roles': ProfessionalRole.objects.all(),
        'title': f'Editar OS #{order.number}'
    })

@login_required
def task_execution(request, task_id):
    """
    View legacy para compatibilidade. Redireciona para task_edit.
    """
    return redirect('task_edit', task_id=task_id)

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
    
    return redirect('task_edit', task_id=task.id)

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
            scheduled_end_at = form.cleaned_data.get('scheduled_end_at')
            team_data = [f for f in formset.cleaned_data if f and not f.get('DELETE')]
            ignore_working_hours = request.POST.get('ignore_working_hours') == 'true'

            for team_form in team_data:
                professional = team_form.get('professional')
                if professional:
                    available, msg, conflict_type = check_professional_availability(
                        professional, scheduled_at, 
                        scheduled_end_at=scheduled_end_at,
                        ignore_working_hours=ignore_working_hours
                    )
                    if not available:
                        # Se for apenas fora do horário de trabalho e não estiver ignorando, avise
                        if conflict_type == "OUT_OF_HOURS":
                            messages.warning(request, f"Aviso de Agenda: {msg} (Confirme para forçar o agendamento).")
                            return render(request, 'services/tasks/task_form.html', {
                                'form': form,
                                'formset': formset,
                                'order': order,
                                'title': 'Adicionar Nova Etapa',
                                'show_force_schedule_modal': True,
                                'force_message': msg
                            })
                        else:
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

            # Notificar os profissionais do novo agendamento
            for team_member in task.team_members.all():
                professional = team_member.professional
                if professional and professional.user:
                    title = "Novo Agendamento 🛠️"
                    body = f"Você foi alocado em: {task.get_task_type_display()} para a OS #{order.number}\nAgendamento: {task.scheduled_at.strftime('%d/%m/%Y às %H:%M') if task.scheduled_at else 'A definir'}"
                    send_push_notification(professional.user, title, body, url=f"/equipe/etapa/{task.id}/")

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
def task_edit(request, task_id):
    """
    View para editar uma Task existente (data, hora, equipe).
    Também serve como view de execução.
    """
    # Verifica se a task pertence a uma OS que o usuário pode ver
    orders_qs = get_orders_queryset(request)
    task = get_object_or_404(ServiceOrderTask, id=task_id, service_order__in=orders_qs)
    order = task.service_order
    existing_medias = task.medias.all()
    
    # Se for colaborador, verificar se ele faz parte da equipe desta task
    user = request.user
    is_manager = user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]
    
    if not is_manager:
        is_assigned = task.team_members.filter(professional__user=user).exists()
        if not is_assigned:
            messages.error(request, "Você não tem permissão para editar esta etapa.")
            return redirect('service_order_detail', order_id=order.id)

    if task.status == ServiceOrderTask.TaskStatus.COMPLETED and not is_manager:
        messages.warning(request, "Não é possível editar uma etapa já concluída.")
        return redirect('service_order_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = TaskScheduleForm(request.POST, request.FILES, instance=task)
        formset = ServiceOrderTeamFormSet(request.POST, request.FILES, instance=task)

        if form.is_valid() and formset.is_valid():
            # ... (rest of logic stays same)
            scheduled_at = form.cleaned_data.get('scheduled_at')
            scheduled_end_at = form.cleaned_data.get('scheduled_end_at')
            team_data = [f for f in formset.cleaned_data if f and not f.get('DELETE')]
            ignore_working_hours = request.POST.get('ignore_working_hours') == 'true'

            # Validar disponibilidade da equipe (excluindo a task atual)
            for team_form in team_data:
                professional = team_form.get('professional')
                if professional:
                    available, msg, conflict_type = check_professional_availability(
                        professional, scheduled_at, 
                        scheduled_end_at=scheduled_end_at,
                        exclude_task_id=task.id, 
                        ignore_working_hours=ignore_working_hours
                    )
                    if not available:
                        if conflict_type == "OUT_OF_HOURS":
                            messages.warning(request, f"Aviso de Agenda: {msg} (Confirme para forçar o agendamento).")
                            return render(request, 'services/tasks/task_form.html', {
                                'form': form,
                                'formset': formset,
                                'order': order,
                                'task': task,
                                'existing_medias': existing_medias,
                                'title': 'Editar Etapa',
                                'show_force_schedule_modal': True,
                                'force_message': msg
                            })
                        else:
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
    default_duration = timedelta(hours=1)  # Duração padrão quando não especificada (alterado de 1h30 para 1h)
    user = request.user
    
    # Se for colaborador, ele só vê os próprios eventos, independente do filtro
    if not (user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]):
        try:
            prof_id = str(user.professional_profile.id)  # Garante string para comparação
        except Professional.DoesNotExist:
            return JsonResponse([], safe=False)
    else:
        prof_id = request.GET.get('professional_id')
        if prof_id:
            prof_id = str(prof_id)  # Padroniza como string
    
    tasks = ServiceOrderTask.objects.select_related('service_order__client_property__client')
    if prof_id:
        tasks = tasks.filter(team_members__professional_id=prof_id).distinct()
    
    is_manager = user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]

    for task in tasks:
        colors = {
            'BUDGET': ('#3b82f6', '#2563eb', 'ORÇ'),
            'EXECUTION': ('#10b981', '#059669', 'EXEC'),
            'WARRANTY': ('#f59e0b', '#d97706', 'GAR'),
        }
        bg, border, prefix = colors.get(task.task_type, ('#64748b', '#475569', 'TSK'))

        team_names = ', '.join([tm.professional.name + '-' + (tm.role.name if tm.role else 'Geral') for tm in task.team_members.all()])
        neighborhood = task.service_order.client_property.neighborhood
        title = f"{prefix}: {task.service_order.client_property.client.name} | {team_names} | {neighborhood}"

        # Usar scheduled_end_at se existir, senão usar duração padrão
        end_time = task.scheduled_end_at if task.scheduled_end_at else (task.scheduled_at + default_duration)

        url = reverse_lazy('service_order_detail', kwargs={'order_id': task.service_order.id})
        if not is_manager:
            url = reverse_lazy('equipe_task_detail', kwargs={'task_id': task.id})

        events.append({
            'id': f"task-{task.id}",
            'title': title,
            'start': task.scheduled_at.isoformat(),
            'end': end_time.isoformat(),
            'backgroundColor': bg,
            'borderColor': border,
            'url': url,
            'client': task.service_order.client_property.client.name,
            'address': f"{task.service_order.client_property.address}, {task.service_order.client_property.number}",
            'neighborhood': neighborhood,
            'status': task.service_order.get_status_display(),
            'description': task.service_order.description,
            'team': [tm.professional.name for tm in task.team_members.all()],
            'type': task.task_type.lower()
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
    user = request.user
    context = {
        'professionals': Professional.objects.filter(is_active=True),
        'professional_roles': ProfessionalRole.objects.all(),
        'status_choices': ServiceOrder.Status.choices,
        'title': 'Agenda'
    }
    
    # Se for colaborador, passa apenas seu próprio perfil
    layout_base = 'base.html' if user.is_manager else 'base_equipe.html'
    context['layout_base'] = layout_base

    if not user.is_manager:
        try:
            context['current_professional'] = user.professional_profile
            context['is_collaborator'] = True
        except Professional.DoesNotExist:
            context['is_collaborator'] = True
    else:
        context['is_collaborator'] = False
    
    return render(request, 'services/orders/calendar.html', context)

@login_required
def api_check_availability(request):
    prof_id = request.GET.get('professional_id')
    timestamp_str = request.GET.get('timestamp')
    end_timestamp_str = request.GET.get('scheduled_end_at')
    
    if not prof_id or not timestamp_str:
        return JsonResponse({'available': True})
    try:
        professional = get_object_or_404(Professional, id=prof_id)
        timestamp = parse(timestamp_str)
        
        scheduled_end_at = None
        if end_timestamp_str:
            try:
                scheduled_end_at = parse(end_timestamp_str)
            except:
                pass
                
        available, message, conflict_type = check_professional_availability(
            professional, timestamp, scheduled_end_at=scheduled_end_at
        )
        return JsonResponse({'available': available, 'message': message, 'conflict_type': conflict_type})
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
        scheduled_end_at = None
        if data.get('scheduled_end_at'):
            try:
                scheduled_end_at = parse(data.get('scheduled_end_at'))
            except:
                pass

        ignore_working_hours = data.get('ignore_working_hours', False)

        # Pré-validar disponibilidade da equipe antes de criar os registros
        for member in data.get('team', []):
            prof_id = member.get('professional_id')
            if prof_id:
                prof = get_object_or_404(Professional, id=prof_id)
                available, msg, c_type = check_professional_availability(
                    prof, scheduled_at, 
                    scheduled_end_at=scheduled_end_at,
                    ignore_working_hours=ignore_working_hours
                )
                if not available:
                    return JsonResponse({
                        'error': msg, 
                        'conflict_type': c_type,
                        'needs_confirmation': c_type == "OUT_OF_HOURS"
                    }, status=400)

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
            
            # Notificar o profissional
            if prof.user:
                title = "Nova O.S. Rápida 🛠️"
                body = f"Você foi alocado em: {task.get_task_type_display()} (OS #{order.number})\nAgendamento: {task.scheduled_at.strftime('%d/%m/%Y às %H:%M')}"
                send_push_notification(prof.user, title, body, url=f"/equipe/etapa/{task.id}/")

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
    products = Product.objects.filter(is_active=True).order_by('name')
    products_data = [
        {
            'id': str(product.id),
            'name': product.name,
            'code': product.code or '',
            'unit': product.unit_type,
            'unitDisplay': product.get_unit_type_display(),
            'price': str(product.default_unit_price),
        }
        for product in products
    ]
    
    if request.method == 'POST':
        task_id = request.POST.get('task')
        task = get_object_or_404(ServiceOrderTask, id=task_id) if task_id else None
        product_id = request.POST.get('product')
        if not product_id:
            messages.error(request, 'Selecione um produto cadastrado para adicionar o item.')
            return render(request, 'services/orders/order_item_form.html', {
                'order': order,
                'tasks': tasks,
                'products': products,
                'products_data': products_data,
                'title': 'Adicionar Item ao Orçamento'
            })

        product = get_object_or_404(Product, id=product_id, is_active=True)

        quantity_raw = (request.POST.get('quantity') or '1').strip().replace(',', '.')
        try:
            quantity_value = Decimal(quantity_raw)
        except (InvalidOperation, TypeError):
            messages.error(request, 'Informe uma quantidade válida.')
            return render(request, 'services/orders/order_item_form.html', {
                'order': order,
                'tasks': tasks,
                'products': products,
                'products_data': products_data,
                'title': 'Adicionar Item ao Orçamento'
            })

        if quantity_value <= 0:
            messages.error(request, 'A quantidade deve ser maior que zero.')
            return render(request, 'services/orders/order_item_form.html', {
                'order': order,
                'tasks': tasks,
                'products': products,
                'products_data': products_data,
                'title': 'Adicionar Item ao Orçamento'
            })
        
        ServiceItem.objects.create(
            service_order=order,
            task=task,
            product=product,
            description=product.name,
            quantity=quantity_value,
            unit_price=product.default_unit_price
        )
        
        messages.success(request, 'Item adicionado com sucesso!')
        return redirect('service_order_detail', order_id=order.id)
    
    return render(request, 'services/orders/order_item_form.html', {
        'order': order,
        'tasks': tasks,
        'products': products,
        'products_data': products_data,
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

# ============ PAGAMENTOS E DESCONTOS ============

@login_required
@permission_required('services.add_servicepayment', raise_exception=True)
def order_payment_add(request, order_id):
    from .forms import ServicePaymentForm
    order = get_object_or_404(ServiceOrder, id=order_id)
    
    if request.method == 'POST':
        form = ServicePaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.order = order
            payment.save()
            amount_display = f'{payment.amount:.2f}'.replace('.', ',')
            messages.success(request, f'Pagamento de R$ {amount_display} registrado com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
    else:
        default_amount = (order.balance_due or Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        form = ServicePaymentForm(initial={'amount': f'{default_amount:.2f}'})
    
    return render(request, 'services/orders/order_payment_form.html', {
        'order': order,
        'form': form,
        'title': 'Registrar Pagamento'
    })

from django.http import JsonResponse
import urllib.request

@login_required
def resolve_maps_url(request):
    """Resolve URLs encurtadas do Google Maps para extrair as coordenadas reais"""
    short_url = request.GET.get('url', '')
    if not short_url:
        return JsonResponse({'error': 'No URL provided'}, status=400)
    
    try:
        req = urllib.request.Request(short_url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=5)
        return JsonResponse({'resolved_url': response.url})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@permission_required('services.change_serviceorder', raise_exception=True)
def order_discount_update(request, order_id):
    from .forms import ServiceOrderDiscountForm
    order = get_object_or_404(ServiceOrder, id=order_id)
    
    if request.method == 'POST':
        form = ServiceOrderDiscountForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            order.update_status()
            messages.success(request, 'Desconto atualizado com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
    else:
        form = ServiceOrderDiscountForm(instance=order)
    
    return render(request, 'services/orders/order_discount_form.html', {
        'order': order,
        'form': form,
        'title': 'Aplicar Desconto'
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

# --- OCORRÊNCIAS ---

@login_required
def occurrence_list(request):
    "Visão geral das ocorrências"
    if request.user.role not in [User.Roles.ADMIN, User.Roles.MANAGER] and not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect('home')

    occurrences = Occurrence.objects.all().order_by('-created_at')
    
    status_filter = request.GET.get('status', Occurrence.OccurrenceStatus.REGISTERED)
    if status_filter and status_filter != 'ALL':
        occurrences = occurrences.filter(status=status_filter)
        
    return render(request, 'services/occurrences/list.html', {
        'occurrences': occurrences,
        'current_status': status_filter,
        'status_choices': Occurrence.OccurrenceStatus.choices,
        'resolved_count': Occurrence.objects.filter(status=Occurrence.OccurrenceStatus.RESOLVED).count(),
        'registered_count': Occurrence.objects.filter(status=Occurrence.OccurrenceStatus.REGISTERED).count(),
    })

@login_required
def occurrence_resolve(request, occurrence_id):
    "Resolve uma ocorrência"
    if request.method == 'POST':
        if request.user.role not in [User.Roles.ADMIN, User.Roles.MANAGER] and not request.user.is_superuser:
            messages.error(request, "Acesso negado.")
            return redirect('home')
            
        occurrence = get_object_or_404(Occurrence, id=occurrence_id)
        observation = request.POST.get('observation', '')
        
        occurrence.observation = observation
        occurrence.status = Occurrence.OccurrenceStatus.RESOLVED
        occurrence.save()
        
        messages.success(request, f"Ocorrência marcada como resolvida.")
        
    return redirect('occurrence_list')
