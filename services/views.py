from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.urls import reverse_lazy
from django.db.models import Q
from django.core.paginator import Paginator
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import django.utils.timezone
import logging
from .notifications import send_push_notification
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .utils.pdf_generator import BudgetPDFGenerator, CompletionPDFGenerator
from integracoes.chatwoot_client import ChatwootClient
from .models import (
    User, Client, Property, ServiceOrder, ServiceMedia, ServiceItem,
    Professional, ProfessionalRole, ServiceOrderTeam, ProfessionalScheduleBlock,
    ServiceOrderTask, ServicePayment, Occurrence, Product, Service, ServiceCategory,
    TaskChecklistResponse, StockMovement
)
from .forms import (
    ClientForm, PhoneFormSet, EmailFormSet, PropertyFormSet, PropertyForm,
    ServiceOrderSchedulingForm, ServiceOrderForm, ServiceInspectionForm,
    ServiceItemFormSet, ProfessionalForm, ProfessionalScheduleBlockForm,
    ServiceOrderTeamFormSet, TaskScheduleForm, TaskCancelForm,
    ServicePaymentForm, ServiceOrderDiscountForm,
)
from .utils import check_professional_availability, format_phone_e164
from .workflow import trigger_payment_workflow

logger = logging.getLogger(__name__)

def _format_schedule_datetime(value):
    if not value:
        return "a definir"
    return django.utils.timezone.localtime(value).strftime('%d/%m/%Y às %H:%M')

def _format_schedule_window(start_at, end_at):
    if not start_at or not end_at:
        return "a definir"
    start_display = _format_schedule_datetime(start_at)
    end_display = _format_schedule_datetime(end_at)
    return f"{start_display} até {end_display}"

def _build_visit_confirmation_template_vars(task):
    order = task.service_order
    order_number = order.number or "S/N"
    description = order.description or "Sem descrição"
    scheduled_display = _format_schedule_datetime(task.scheduled_at)
    window_display = _format_schedule_window(task.scheduled_at, task.scheduled_end_at)

    team_members = task.team_members.select_related('professional', 'role').all()
    team_display = ""
    if team_members:
        team_display = ", ".join(
            f"{member.professional.name}{f' ({member.role.name})' if member.role else ''}"
            for member in team_members
            if member.professional
        )
    if not team_display:
        team_display = "Equipe a definir"

    return [
        str(order_number),
        description,
        scheduled_display,
        window_display,
        team_display,
    ]

def _send_visit_confirmation_if_needed(task):
    if not task.send_whatsapp_confirmation or task.whatsapp_notification_sent_at:
        return False

    order = task.service_order
    client = order.client_property.client if order and order.client_property else None
    if not client:
        logger.warning("Confirmação WhatsApp ignorada: OS sem cliente vinculada. task=%s", task.id)
        return False

    phone_record = client.phones.filter(is_primary=True).first() or client.phones.first()
    if not phone_record or not phone_record.phone:
        logger.warning("Confirmação WhatsApp ignorada: cliente sem telefone. os=%s", order.number)
        return False

    phone_e164 = format_phone_e164(phone_record.phone)
    if not phone_e164:
        logger.warning("Confirmação WhatsApp ignorada: telefone inválido. os=%s", order.number)
        return False

    cw = ChatwootClient()
    if not all([cw.config.chatwoot_api_token, cw.config.chatwoot_account_id, cw.config.chatwoot_inbox_id]):
        logger.warning("Confirmação WhatsApp ignorada: integração Chatwoot incompleta. os=%s", order.number)
        return False

    contact = cw.search_contact(phone_e164)
    if not contact:
        contact = cw.create_contact(client.name, phone_e164)
    if not contact:
        logger.warning("Falha ao localizar/criar contato no Chatwoot. os=%s", order.number)
        return False

    conversation = cw.get_or_create_conversation(contact['id'])
    conversation_id = conversation.get('id') if isinstance(conversation, dict) else None
    if not conversation_id:
        logger.warning("Falha ao criar conversa no Chatwoot. os=%s", order.number)
        return False

    template_name = "confirmacao_agendamento"
    template_vars = _build_visit_confirmation_template_vars(task)
    response = cw.send_template(
        conversation_id=conversation_id,
        template_name=template_name,
        variables=template_vars,
        content=None
    )
    if not response:
        logger.warning("Falha ao enviar confirmação WhatsApp. os=%s", order.number)
        return False

    message_id, response_conversation_id = cw.extract_message_tracking(response)
    if response_conversation_id:
        conversation_id = response_conversation_id

    cw.assign_label_to_conversation(conversation_id, "aguardando-confirmacao")
    task.whatsapp_notification_sent_at = django.utils.timezone.now()
    update_fields = ['whatsapp_notification_sent_at']
    if not task.whatsapp_confirmation_status:
        task.whatsapp_confirmation_status = ServiceOrderTask.WhatsAppConfirmationStatus.WAITING
        update_fields.append('whatsapp_confirmation_status')
    if conversation_id:
        task.chatwoot_confirmation_conversation_id = str(conversation_id)
        update_fields.append('chatwoot_confirmation_conversation_id')
    if message_id:
        task.chatwoot_confirmation_message_id = str(message_id)
        update_fields.append('chatwoot_confirmation_message_id')
    if contact and contact.get('id'):
        task.chatwoot_confirmation_contact_id = str(contact.get('id'))
        update_fields.append('chatwoot_confirmation_contact_id')
    task.save(update_fields=update_fields)
    return True


def privacy_policy(request):
    return render(request, 'services/policies/privacy_policy.html')


def data_deletion_policy(request):
    return render(request, 'services/policies/data_deletion_policy.html')


def terms_of_service(request):
    return render(request, 'services/policies/terms_of_service.html')

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
    paginate_by = 10

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
    permission_required = 'services.view_professionalscheduleblock'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        professional_id = self.request.GET.get('professional')
        if professional_id:
            queryset = queryset.filter(professional_id=professional_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['professionals'] = Professional.objects.filter(is_active=True)
        context['selected_professional'] = self.request.GET.get('professional')
        context['title'] = 'Bloqueios de Agenda'
        return context

class ProfessionalScheduleBlockCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ProfessionalScheduleBlock
    form_class = ProfessionalScheduleBlockForm
    template_name = 'services/professionals/schedule_block_form.html'
    success_url = reverse_lazy('schedule_block_list')
    permission_required = 'services.add_professionalscheduleblock'

    def get_initial(self):
        initial = super().get_initial()
        prof_id = self.request.GET.get('professional')
        if prof_id:
            initial['professional'] = prof_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Novo Bloqueio de Agenda'
        return context

class ProfessionalScheduleBlockUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ProfessionalScheduleBlock
    form_class = ProfessionalScheduleBlockForm
    template_name = 'services/professionals/schedule_block_form.html'
    success_url = reverse_lazy('schedule_block_list')
    permission_required = 'services.change_professionalscheduleblock'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Editar Bloqueio de Agenda'
        return context

class ProfessionalScheduleBlockDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ProfessionalScheduleBlock
    success_url = reverse_lazy('schedule_block_list')
    permission_required = 'services.delete_professionalscheduleblock'
    
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Bloqueio de agenda removido com sucesso.')
        return super().delete(request, *args, **kwargs)

@login_required
def home(request):
    if not request.user.is_manager:
        return redirect('equipe_dashboard')

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
    clients_qs = Client.objects.all().order_by('name')
    search = request.GET.get('search')
    if search:
        clients_qs = clients_qs.filter(
            Q(name__icontains=search) |
            Q(cpf__icontains=search) |
            Q(cnpj__icontains=search) |
            Q(phones__phone__icontains=search) |
            Q(properties__address__icontains=search) |
            Q(properties__neighborhood__icontains=search) |
            Q(properties__city__icontains=search)
        ).distinct()
    
    paginator = Paginator(clients_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'services/clients/client_list.html', {
        'clients': page_obj,  # Antigamente era 'clients': clients
        'page_obj': page_obj,
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

    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'services/orders/order_list.html', {
        'orders': page_obj,  # Antigamente era 'orders': orders
        'page_obj': page_obj,
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
                send_whatsapp_raw = request.POST.get('send_whatsapp_confirmation')
            else:
                sched_val = request.POST.get(f'task_{_idx}_scheduled', '')
                sched_end_val = request.POST.get(f'task_{_idx}_scheduled_end', '')
                send_whatsapp_raw = request.POST.get(f'task_{_idx}_send_whatsapp_confirmation')
             
            task_data = {
                'index': _idx,
                'type': request.POST.get(f'task_{_idx}_type', ''),
                'scheduled': sched_val,
                'scheduled_end': sched_end_val,
                'start_date': request.POST.get(f'task_{_idx}_start_date', ''),
                'end_date': request.POST.get(f'task_{_idx}_end_date', ''),
                'send_whatsapp_confirmation': bool(send_whatsapp_raw),
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
                    return render(request, 'services/orders/order_edit.html', {
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
                    return render(request, 'services/orders/order_edit.html', {
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
                    task_kwargs = {
                        'service_order': service_order,
                        'task_type': task_type,
                        'scheduled_at': scheduled_datetime,
                        'scheduled_end_at': scheduled_end_datetime,
                    }
                    
                    # Se for a primeira task, usar os dados do formulário principal
                    if task_index == 0:
                        task_kwargs.update({
                            'is_approved': form.cleaned_data.get('is_approved', False),
                            'payment_method': form.cleaned_data.get('payment_method'),
                            'send_whatsapp_confirmation': form.cleaned_data.get('send_whatsapp_confirmation', False),   
                            'whatsapp_confirmation_status': form.cleaned_data.get('whatsapp_confirmation_status'),      
                            'whatsapp_notification_sent_at': form.cleaned_data.get('whatsapp_notification_sent_at'),    
                            'whatsapp_confirmation_received_at': form.cleaned_data.get('whatsapp_confirmation_received_at'),
                            'whatsapp_response_content': form.cleaned_data.get('whatsapp_response_content'),
                        })
                    else:
                        task_kwargs['send_whatsapp_confirmation'] = request.POST.get(
                            f'task_{task_index}_send_whatsapp_confirmation'
                        ) == 'on'

                    task = ServiceOrderTask.objects.create(**task_kwargs)
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
                    _send_visit_confirmation_if_needed(task)
                
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
            return render(request, 'services/orders/order_edit.html', {
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

    return render(request, 'services/orders/order_edit.html', {
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
                status=ServiceOrder.Status.WAITING_VISIT,
                description=form.cleaned_data.get('description', ''),
                client_observation=form.cleaned_data.get('client_observation', ''),
                technical_notes=form.cleaned_data.get('technical_notes', '')
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
            
            if order.status in [ServiceOrder.Status.BUDGET_SCHEDULED, ServiceOrder.Status.BUDGET_DONE_WAITING_SEND] and order.items.exists():
                order.status = ServiceOrder.Status.BUDGET_DONE_WAITING_SEND
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
    tasks = order.tasks.all().prefetch_related(
        'team_members__professional', 
        'medias',
        'checklist_responses__item',
        'checklist_responses__medias'
    )
    occurrences = Occurrence.objects.filter(task__service_order=order).order_by('-created_at')
    
    # Verifica se existe algum checklist preenchido em qualquer etapa
    any_task_has_checklist = TaskChecklistResponse.objects.filter(task__service_order=order).exists()

    tasks_with_signature = [t for t in tasks if t.customer_signature]

    products = Product.objects.filter(is_active=True).order_by('name')
    products_data = [
        {
            'id': str(product.id),
            'name': product.name,
            'code': product.code or '',
            'unit': product.unit_type,
            'unitDisplay': product.get_unit_type_display(),
            'price': str(product.default_unit_price),
            'type': 'PRODUCT'
        }
        for product in products
    ]
    
    services = Service.objects.filter(is_active=True).order_by('name')
    services_data = [
        {
            'id': str(service.id),
            'name': service.name,
            'code': '',
            'unit': service.unit_of_measure,
            'unitDisplay': service.unit_of_measure,
            'price': str(service.base_price),
            'type': 'SERVICE'
        }
        for service in services
    ]
    
    return render(request, 'services/orders/order_detail.html', {
        'order': order,
        'tasks': tasks,
        'occurrences': occurrences,
        'products_data': products_data,
        'services_data': services_data,
        'any_task_has_checklist': any_task_has_checklist,
        'tasks_with_signature': tasks_with_signature,
    })

@login_required
@permission_required('services.change_serviceorder', raise_exception=True)
def resend_billing(request, pk):
    """
    View para re-enviar manualmente a cobrança (Pix + PDF) de uma OS.
    """
    order = get_object_or_404(ServiceOrder, id=pk)
    
    # Forçar limpeza do campo para permitir reenvio pelo workflow
    order.pix_sent_at = None
    order.save(update_fields=['pix_sent_at'])
    
    trigger_payment_workflow(order)
    
    messages.success(request, f"Workflow de cobrança reiniciado para a OS #{order.number}. A mensagem será enviada em instantes.")
    return redirect('service_order_detail', order_id=order.id)

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
            
            # Atualiza os campos da primeira task (Etapa)
            first_task = service_order.tasks.order_by('scheduled_at').first()
            if first_task:
                first_task.task_type = form.cleaned_data.get('task_type')
                first_task.is_approved = form.cleaned_data.get('is_approved', False)
                first_task.payment_method = form.cleaned_data.get('payment_method')
                first_task.scheduled_at = form.cleaned_data.get('scheduled_at')
                first_task.scheduled_end_at = form.cleaned_data.get('scheduled_end_at')
                first_task.save()
            
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
            
            _send_visit_confirmation_if_needed(task)

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
            url = f"{reverse_lazy('equipe_offline_app')}#task/{task.id}"

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

def _get_order_items_total(order):
    return sum((item.total_price for item in order.items.all()), Decimal('0'))

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
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        def error_response(message):
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=400)
            messages.error(request, message)
            return render(request, 'services/orders/order_item_form.html', {
                'order': order,
                'tasks': tasks,
                'products': products,
                'products_data': products_data,
                'title': 'Adicionar Item ao Orçamento'
            })

        try:
            task_id = request.POST.get('task')
            task = get_object_or_404(ServiceOrderTask, id=task_id) if task_id else None
            
            product_id = request.POST.get('product')
            service_id = request.POST.get('service')
            
            if not product_id and not service_id:
                return error_response('Selecione um produto ou serviço cadastrado para adicionar o item.')

            item_data = {
                'service_order': order,
                'task': task,
                'product': None,
                'service': None,
                'description': '',
                'unit_price': Decimal('0')
            }

            if product_id:
                product = get_object_or_404(Product, id=product_id, is_active=True)
                item_data['product'] = product
                item_data['description'] = product.name
                item_data['unit_price'] = product.default_unit_price
            else:
                service = get_object_or_404(Service, id=service_id, is_active=True)
                item_data['service'] = service
                item_data['description'] = service.name
                item_data['unit_price'] = service.base_price

            # Tenta usar o valor unitário enviado pelo formulário (caso tenha sido editado)
            unit_price_raw = request.POST.get('unit_price')
            if unit_price_raw:
                try:
                    item_data['unit_price'] = Decimal(unit_price_raw.replace(',', '.'))
                except (InvalidOperation, TypeError):
                    pass # Mantém o preço padrão do catálogo se o valor for inválido

            quantity_raw = (request.POST.get('quantity') or '1').strip().replace(',', '.')
            try:
                quantity_value = Decimal(quantity_raw)
            except (InvalidOperation, TypeError):
                return error_response('Informe uma quantidade válida.')

            if quantity_value <= 0:
                return error_response('A quantidade deve ser maior que zero.')
            
            item = ServiceItem.objects.create(
                service_order=item_data['service_order'],
                task=item_data['task'],
                product=item_data['product'],
                service=item_data['service'],
                description=item_data['description'],
                quantity=quantity_value,
                unit_price=item_data['unit_price']
            )

            # --- ATUALIZAÇÃO DE ESTOQUE ---
            if item.product:
                product = item.product
                product.current_stock -= item.quantity
                product.save()
                
                # Registrar movimentação
                StockMovement.objects.create(
                    product=product,
                    quantity=item.quantity,
                    movement_type=StockMovement.MovementType.OUT,
                    reason=StockMovement.Reason.SALE_OS,
                    service_order=order,
                    user=request.user
                )

            if is_ajax:
                try:
                    item_total = item.total_price
                    item_unit = '-'
                    if item.product:
                        item_unit = item.product.get_unit_type_display()
                    elif item.service:
                        item_unit = item.service.unit_of_measure

                    if item.product and item.product.unit_type == Product.UnitType.METER:
                        quantity_display = f'{item.quantity:.2f}'
                    else:
                        quantity_display = f'{item.quantity:.0f}'

                    # Calcular o total da order
                    try:
                        order_total = order.total_value
                        balance_due = order.balance_due
                        order_total_display = f'{order_total:.2f}'.replace('.', ',')
                        estimated_value_display = f'{order.estimated_value:.2f}'.replace('.', ',')
                        balance_due_display = f'{balance_due:.2f}'.replace('.', ',')
                    except Exception as e:
                        print(f"Erro ao calcular total da order: {e}")
                        order_total_display = "0,00"
                        estimated_value_display = "0,00"
                        balance_due_display = "0,00"

                    return JsonResponse({
                        'success': True,
                        'message': 'Item adicionado com sucesso!',
                        'item': {
                            'id': item.id,
                            'description': item.description,
                            'product_code': item.product.code if item.product else '',
                            'product_name': item.product.name if item.product else (item.service.name if item.service else ''),
                            'unit_display': item_unit,
                            'type_display': 'Produto' if item.product else ('Serviço' if item.service else '-'),
                            'type_class': 'bg-blue-50 text-blue-600' if item.product else ('bg-purple-50 text-purple-600' if item.service else ''),
                            'origin_display': item.task.get_task_type_display() if item.task else 'Orçamento',
                            'origin_is_task': bool(item.task),
                            'quantity_display': str(quantity_display).replace('.', ','),
                            'unit_price_display': f'{item.unit_price:.2f}'.replace('.', ','),
                            'total_price_display': f'{item_total:.2f}'.replace('.', ','),
                        },
                        'order_total_display': order_total_display,
                        'estimated_value_display': estimated_value_display,
                        'balance_due_display': balance_due_display,
                        'balance_due_positive': bool(order.balance_due > 0),
                    })
                except Exception as e:
                    print(f"Erro ao preparar resposta JSON: {e}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Item adicionado com sucesso!',
                        'item': {
                            'id': item.id,
                            'description': item.description,
                            'product_code': item.product.code if item.product else '',
                            'product_name': item.product.name if item.product else (item.service.name if item.service else ''),
                            'unit_display': item.product.get_unit_type_display() if item.product else '-',
                            'type_display': 'Produto' if item.product else ('Serviço' if item.service else '-'),
                            'type_class': 'bg-blue-50 text-blue-600' if item.product else ('bg-purple-50 text-purple-600' if item.service else ''),
                            'origin_display': item.task.get_task_type_display() if item.task else 'Orçamento',
                            'origin_is_task': bool(item.task),
                            'quantity_display': '1',
                            'unit_price_display': '0,00',
                            'total_price_display': '0,00',
                        },
                        'order_total_display': '0,00',
                        'estimated_value_display': '0,00',
                        'balance_due_display': '0,00',
                        'balance_due_positive': False,
                    })
                    
            
            messages.success(request, 'Item adicionado com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
        
        except Exception as e:
            print(f"Erro inesperado ao adicionar item: {e}")
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': f'Erro inesperado: {str(e)}'
                }, status=500)
            messages.error(request, f'Erro inesperado: {str(e)}')
            return render(request, 'services/orders/order_item_form.html', {
                'order': order,
                'tasks': tasks,
                'products': products,
                'products_data': products_data,
                'title': 'Adicionar Item ao Orçamento'
            })
    
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
    order = item.service_order
    order_id = order.id
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        # --- ATUALIZAÇÃO DE ESTOQUE ---
        if item.product:
            product = item.product
            product.current_stock += item.quantity
            product.save()
            
            # Registrar movimentação (estorno)
            StockMovement.objects.create(
                product=product,
                quantity=item.quantity,
                movement_type=StockMovement.MovementType.IN,
                reason=StockMovement.Reason.RETURN,
                service_order=order,
                user=request.user
            )

        item.delete()
        
        if is_ajax:
            try:
                order_total_display = f'{order.total_value:.2f}'.replace('.', ',')
                estimated_value_display = f'{order.estimated_value:.2f}'.replace('.', ',')
                balance_due_display = f'{order.balance_due:.2f}'.replace('.', ',')
            except Exception as e:
                print(f"Erro ao calcular total da order: {e}")
                order_total_display = "0,00"
                estimated_value_display = "0,00"
                balance_due_display = "0,00"
            
            return JsonResponse({
                'success': True,
                'message': 'Item removido com sucesso!',
                'order_total_display': order_total_display,
                'estimated_value_display': estimated_value_display,
                'balance_due_display': balance_due_display,
                'balance_due_positive': bool(order.balance_due > 0),
            })
        
        messages.success(request, 'Item removido com sucesso!')
        return redirect('service_order_detail', order_id=order_id)
    
    return render(request, 'services/orders/order_item_delete.html', {
        'item': item,
        'order': order
    })

@permission_required('services.change_serviceitem', raise_exception=True)
def order_item_update(request, item_id):
    """View para atualizar quantidade e preço unitário de um item via AJAX"""
    item = get_object_or_404(ServiceItem, id=item_id)
    order = item.service_order
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST' and is_ajax:
        try:
            quantity_raw = request.POST.get('quantity', '').replace(',', '.')
            unit_price_raw = request.POST.get('unit_price', '').replace(',', '.')
            
            new_quantity = Decimal(quantity_raw)
            new_unit_price = Decimal(unit_price_raw)

            if new_quantity <= 0:
                return JsonResponse({'success': False, 'message': 'A quantidade deve ser maior que zero.'}, status=400)

            # --- ATUALIZAÇÃO DE ESTOQUE ---
            if item.product:
                product = item.product
                diff = new_quantity - item.quantity
                
                # Ajusta o estoque
                product.current_stock -= diff
                product.save()
                
                # Registrar movimentação se houve mudança
                if diff != 0:
                    movement_type = StockMovement.MovementType.OUT if diff > 0 else StockMovement.MovementType.IN
                    reason = StockMovement.Reason.SALE_OS if diff > 0 else StockMovement.Reason.RETURN
                    
                    StockMovement.objects.create(
                        product=product,
                        quantity=abs(diff),
                        movement_type=movement_type,
                        reason=reason,
                        service_order=order,
                        user=request.user
                    )

            # Atualiza o item
            item.quantity = new_quantity
            item.unit_price = new_unit_price
            item.save()

            return JsonResponse({
                'success': True,
                'item': {
                    'id': item.id,
                    'quantity_display': f'{item.quantity:.2f}'.replace('.', ','),
                    'unit_price_display': f'{item.unit_price:.2f}'.replace('.', ','),
                    'total_price_display': f'{item.total_price:.2f}'.replace('.', ','),
                },
                'order_total_display': f'{order.total_value:.2f}'.replace('.', ','),
                'estimated_value_display': f'{order.estimated_value:.2f}'.replace('.', ','),
                'balance_due_display': f'{order.balance_due:.2f}'.replace('.', ','),
                'balance_due_positive': bool(order.balance_due > 0)
            })
        except (InvalidOperation, TypeError, ValueError) as e:
            return JsonResponse({'success': False, 'message': 'Valores inválidos.'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    return JsonResponse({'success': False, 'message': 'Método não permitido.'}, status=405)

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
            order = form.save()
            
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
    
    if request.method == 'POST':
        # Deletar arquivo físico
        if media.file:
            media.file.delete()
        media.delete()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == 'true':
            return JsonResponse({'success': True, 'message': 'Mídia removida com sucesso!'})
            
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
        
    paginator = Paginator(occurrences, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'services/occurrences/list.html', {
        'occurrences': page_obj,  # Antigamente era 'occurrences': occurrences
        'page_obj': page_obj,
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

@login_required
@permission_required("services.change_serviceorder", raise_exception=True)
@require_POST
def order_observation_update(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    observation = request.POST.get("client_observation", "")
    order.client_observation = observation
    order.save(update_fields=["client_observation"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "observation": observation})
    messages.success(request, "Observação do cliente atualizada com sucesso.")
    return redirect("service_order_detail", order_id=order.id)


@login_required
def service_order_pdf(request, order_id):
    service_order = get_object_or_404(ServiceOrder, id=order_id)
    generator = BudgetPDFGenerator(service_order)
    pdf_content = generator.generate()
    
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"Orcamento_OS_{service_order.number}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def service_order_report_pdf(request, order_id):
    service_order = get_object_or_404(ServiceOrder, id=order_id)
    generator = CompletionPDFGenerator(service_order)
    pdf_content = generator.generate()
    
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"Relatorio_Execucao_OS_{service_order.number}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
@permission_required('services.change_serviceorder', raise_exception=True)
def service_order_send_budget(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    client_name = order.client_property.client.name
    client_phone = order.client_property.client.phones.first()
    
    if not client_phone:
        messages.error(request, "Cliente não possui telefone cadastrado.")
        return redirect('service_order_detail', order_id=order.id)
    
    phone_e164 = format_phone_e164(client_phone.phone)
    
    try:
        # 1. Gerar PDF
        generator = BudgetPDFGenerator(order)
        pdf_content = generator.generate()
        filename = f"Orcamento_OS_{order.number}.pdf"
        
        # 2. Integração Chatwoot
        cw = ChatwootClient()
        
        # Buscar ou criar contato
        contact = cw.search_contact(phone_e164)
        if not contact:
            contact = cw.create_contact(client_name, phone_e164)
            
        if not contact:
            raise Exception("Não foi possível localizar ou criar o contato no Chatwoot.")
            
        # Buscar ou criar conversa
        conversation = cw.get_or_create_conversation(contact['id'])
        if not conversation:
            raise Exception("Não foi possível criar a conversa no Chatwoot.")
            
        conversation_id = conversation['id']
        
        # 3. Enviar PDF e Template
        attachment = (filename, pdf_content, 'application/pdf')
        
        response = None
        if cw.config.chatwoot_budget_template:
            # Preparar variáveis para o corpo do template:
            # Variável 1: Número da OS, Variável 2: Valor (apenas o número, pois R$ já está no template)
            if order.estimated_value:
                # Formata como 1.580,00
                value_display = f"{order.estimated_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            else:
                value_display = "0,00"
            
            variables = [str(order.number), value_display]
            
            # Deixamos o content como None para o ChatwootClient buscar o texto real do template
            response = cw.send_template(
                conversation_id=conversation_id,
                template_name=cw.config.chatwoot_budget_template,
                variables=variables,
                attachment=attachment,
                content=None 
            )
            success_msg = f"Orçamento enviado com sucesso para {client_name} via WhatsApp (Template)!"
        else:
            # Fallback para mensagem simples com anexo
            response = cw.send_message(conversation_id, "Segue o orçamento solicitado em anexo.", attachments=[attachment])
            success_msg = f"Orçamento enviado com sucesso para {client_name} via WhatsApp!"
            
        if response:
            message_id, tracked_conversation_id = cw.extract_message_tracking(response)
            order.chatwoot_budget_message_id = message_id
            order.chatwoot_budget_conversation_id = tracked_conversation_id or str(conversation_id)
            order.status = ServiceOrder.Status.WAITING_APPROVAL
            order.client_budget_response = None
            order.client_budget_responded_at = None
            order.client_budget_approved_at = None
            order.save(update_fields=[
                'chatwoot_budget_message_id',
                'chatwoot_budget_conversation_id',
                'status',
                'client_budget_response',
                'client_budget_responded_at',
                'client_budget_approved_at',
                'updated_at',
            ])

            budget_sent_label = cw.get_label_by_title("Orçamento-Enviado") or cw.create_label("Orçamento-Enviado")
            if budget_sent_label:
                conversation_ids = []
                for cid in (
                    tracked_conversation_id,
                    response.get('conversation_id') if isinstance(response, dict) else None,
                    order.chatwoot_budget_conversation_id,
                    str(conversation_id),
                ):
                    normalized_cid = str(cid).strip() if cid not in (None, '') else ''
                    if normalized_cid and normalized_cid not in conversation_ids:
                        conversation_ids.append(normalized_cid)

                assigned_labels = None
                for cid in conversation_ids:
                    assigned_labels = cw.assign_label_to_conversation(
                        cid,
                        budget_sent_label.get("title", "Orçamento-Enviado")
                    )
                    if assigned_labels:
                        break

                if not assigned_labels:
                    logger.warning(
                        "Orçamento enviado, mas falhou ao atribuir etiqueta no Chatwoot. os=%s conversation_ids=%s",
                        order.number,
                        conversation_ids
                    )
            else:
                logger.warning("Orçamento enviado, mas não foi possível criar/localizar etiqueta Orçamento-Enviado. os=%s", order.number)

            messages.success(request, success_msg)
        else:
            raise Exception("A API do Chatwoot não retornou uma confirmação de sucesso. Verifique as configurações e os logs do sistema.")
        
    except Exception as e:
        logger.exception("Erro ao enviar orçamento via Chatwoot")
        messages.error(request, f"Erro ao enviar orçamento: {str(e)}")
        
    return redirect('service_order_detail', order_id=order.id)


# --- UPPY TEST VIEWS ---

@login_required
def uppy_test_page(request):
    return render(request, 'services/uppy_test.html')

@csrf_exempt
@login_required
def uppy_upload(request):
    if request.method == 'POST' and request.FILES:
        import os
        from django.conf import settings
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        file = request.FILES.get('file') or request.FILES.get('files[]')
        if not file:
            file = next(iter(request.FILES.values()))
            
        # Define um caminho temporário para teste
        path = os.path.join('temp_uppy', file.name)
        actual_path = default_storage.save(path, ContentFile(file.read()))
        full_url = os.path.join(settings.MEDIA_URL, actual_path)

        logger.info(f"Uppy upload salvo: {actual_path} ({file.size} bytes)")
        
        return JsonResponse({
            'status': 'success', 
            'url': full_url,
            'filename': file.name,
            'size': file.size
        })
    return JsonResponse({'status': 'error', 'message': 'No files received'}, status=400)
