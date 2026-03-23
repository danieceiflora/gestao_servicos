from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.db.models import Q
from datetime import timedelta, datetime
from .models import Client, Property, ServiceOrder, ServiceMedia, ServiceItem, Professional, ProfessionalRole, ServiceOrderTeam, ProfessionalScheduleBlock
from .forms import (
    ClientForm, PhoneFormSet, EmailFormSet, PropertyFormSet, 
    PropertyForm, ServiceInspectionForm, ServiceItemFormSet,
    ServiceOrderForm, ProfessionalForm, AvailabilityFormSet,
    ServiceOrderTeamFormSet, ServiceOrderSchedulingForm
)

class ProfessionalListView(ListView):
    model = Professional
    template_name = 'services/professionals/professional_list.html'
    context_object_name = 'professionals'

class ProfessionalCreateView(CreateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = 'services/professionals/professional_form.html'
    success_url = reverse_lazy('professional_list')

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

class ProfessionalUpdateView(UpdateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = 'services/professionals/professional_form.html'
    success_url = reverse_lazy('professional_list')

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

def home(request):
    active_orders = ServiceOrder.objects.exclude(status__in=[ServiceOrder.Status.FINISHED, ServiceOrder.Status.CANCELLED]).count()
    pending_approval = ServiceOrder.objects.filter(status=ServiceOrder.Status.WAITING_APPROVAL).count()
    waiting_execution = ServiceOrder.objects.filter(status=ServiceOrder.Status.WAITING_EXECUTION).count()
    
    recent_orders = ServiceOrder.objects.all().order_by('-updated_at')[:5]
    
    return render(request, 'services/home.html', {
        'active_orders': active_orders,
        'pending_approval': pending_approval,
        'waiting_execution': waiting_execution,
        'recent_orders': recent_orders
    })

def client_list(request):
    clients = Client.objects.all().order_by('-created_at')
    return render(request, 'services/clients/client_list.html', {'clients': clients})

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

def service_order_list(request):
    orders = ServiceOrder.objects.all().order_by('-created_at')
    return render(request, 'services/orders/order_list.html', {'orders': orders})

def service_order_scheduling(request):
    if request.method == 'POST':
        form = ServiceOrderSchedulingForm(request.POST)
        formset = ServiceOrderTeamFormSet(request.POST, prefix='team_members')
        if form.is_valid() and formset.is_valid():
            service_order = form.save(commit=False)
            
            # Map scheduling type to status
            sched_type = form.cleaned_data.get('scheduling_type')
            if sched_type == 'INSPECTION':
                service_order.status = ServiceOrder.Status.BUDGET_SCHEDULED
            elif sched_type == 'EXECUTION':
                service_order.status = ServiceOrder.Status.WAITING_EXECUTION
            elif sched_type == 'WARRANTY':
                service_order.status = ServiceOrder.Status.WAITING_EXECUTION
            
            service_order.save()
            formset.instance = service_order
            
            # Manually set category based on scheduling type for the initial team
            instances = formset.save(commit=False)
            for instance in instances:
                instance.category = sched_type
                instance.save()
            formset.save_m2m()
            
            messages.success(request, 'Ordem de Serviço agendada com sucesso!')
            return redirect('service_order_detail', order_id=service_order.id)
    else:
        form = ServiceOrderSchedulingForm()
        formset = ServiceOrderTeamFormSet(prefix='team_members')
    
    return render(request, 'services/orders/order_scheduling_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Novo Agendamento'
    })

def service_order_create(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)
    if request.method == 'POST':
        form = ServiceInspectionForm(request.POST, request.FILES)
        if form.is_valid():
            service_order = form.save(commit=False)
            service_order.client_property = property_obj
            service_order.status = ServiceOrder.Status.WAITING_BUDGET
            service_order.save()
            
            # Handle Multiple Files
            files = request.FILES.getlist('files')
            for f in files:
                ServiceMedia.objects.create(
                    service_order=service_order,
                    file=f,
                    media_type=ServiceMedia.MediaType.INSPECTION
                )
            
            messages.success(request, 'Ordem de Serviço criada com sucesso!')
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
    if request.method == 'POST':
        form = ServiceOrderForm(request.POST, instance=order)
        formset = ServiceItemFormSet(request.POST, instance=order)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            
            # Auto-update status only if it's still in initial stages and items were added
            if order.status in [ServiceOrder.Status.WAITING_BUDGET, ServiceOrder.Status.BUDGET_SCHEDULED] and order.items.exists():
                order.status = ServiceOrder.Status.WAITING_APPROVAL
                order.save()
                
            messages.success(request, 'Orçamento e status atualizados com sucesso!')
            return redirect('service_order_list')
    else:
        form = ServiceOrderForm(instance=order)
        formset = ServiceItemFormSet(instance=order)
    
    return render(request, 'services/orders/service_budget_form.html', {
        'order': order,
        'form': form,
        'formset': formset,
        'title': 'Elaborar Orçamento'
    })

def service_order_detail(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    return render(request, 'services/orders/order_detail.html', {'order': order})

def service_order_team(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    
    # Helper to create formsets with category filtering
    def get_team_formset(category, prefix, data=None):
        return ServiceOrderTeamFormSet(
            data,
            instance=order,
            prefix=prefix,
            queryset=ServiceOrderTeam.objects.filter(service_order=order, category=category),
            initial=[{'category': category}] # Set initial for the first extra form
        )

    if request.method == 'POST':
        f_inspection = get_team_formset(ServiceOrderTeam.Category.INSPECTION, 'inspection', request.POST)
        f_execution = get_team_formset(ServiceOrderTeam.Category.EXECUTION, 'execution', request.POST)
        f_warranty = get_team_formset(ServiceOrderTeam.Category.WARRANTY, 'warranty', request.POST)
        
        if f_inspection.is_valid() and f_execution.is_valid() and f_warranty.is_valid():
            # Standard formset saving - category is now in the form hidden fields
            f_inspection.save()
            f_execution.save()
            f_warranty.save()

            messages.success(request, 'Equipes atualizadas com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
        else:
            messages.error(request, 'Erro ao salvar equipes. Verifique os dados informados.')
    else:
        f_inspection = get_team_formset(ServiceOrderTeam.Category.INSPECTION, 'inspection')
        f_execution = get_team_formset(ServiceOrderTeam.Category.EXECUTION, 'execution')
        f_warranty = get_team_formset(ServiceOrderTeam.Category.WARRANTY, 'warranty')
    
    return render(request, 'services/orders/order_team_form.html', {
        'order': order,
        'f_inspection': f_inspection,
        'f_execution': f_execution,
        'f_warranty': f_warranty,
        'title': 'Designar Equipe'
    })

def service_order_edit(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    if request.method == 'POST':
        form = ServiceOrderForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ordem de Serviço atualizada com sucesso!')
            return redirect('service_order_detail', order_id=order.id)
    else:
        form = ServiceOrderForm(instance=order)
    
    return render(request, 'services/orders/order_edit_full.html', {
        'form': form,
        'order': order,
        'title': f'Editar OS #{order.id.hex[:8]}'
    })

def service_order_execution(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    
    if request.method == 'POST':
        # Ao postar nesta view, estamos enviando evidências finais
        files = request.FILES.getlist('files')
        if files:
            for f in files:
                ServiceMedia.objects.create(
                    service_order=order,
                    file=f,
                    media_type=ServiceMedia.MediaType.FINAL
                )
            messages.success(request, 'Evidências de execução salvas!')
        
        # Se clicar em um botão específico de finalizar
        if 'finish_service' in request.POST:
            final_notes = request.POST.get('final_notes')
            if final_notes:
                order.technical_notes = final_notes
            order.status = ServiceOrder.Status.FINISHED
            import django.utils.timezone
            order.finished_at = django.utils.timezone.now()
            order.save()
            messages.success(request, 'Serviço finalizado com sucesso!')
            return redirect('service_order_list')

    return render(request, 'services/orders/order_execution.html', {
        'order': order,
        'title': 'Execução de Serviço'
    })

from django.http import JsonResponse
from .utils import check_professional_availability
from dateutil.parser import parse

def api_calendar_events(request):
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    prof_id = request.GET.get('professional_id')

    events = []
    buffer = timedelta(hours=1, minutes=30)

    if prof_id:
        # Visão específica do profissional: Mostra apenas os serviços onde ele está alocado
        assignments = ServiceOrderTeam.objects.filter(professional_id=prof_id).select_related(
            'service_order', 
            'service_order__client_property__client',
            'service_order__client_property'
        ).prefetch_related('service_order__team_members__professional')
        
        for assign in assignments:
            order = assign.service_order
            team = [m.professional.name for m in order.team_members.all()]
            
            # Como não há mais agendamento individual, usa os da OS
            dates = [
                (order.budget_scheduled_at, 'budget', 'ORÇ'),
                (order.execution_scheduled_at, 'execution', 'EXEC')
            ]
            
            for dt, kind, prefix in dates:
                if dt:
                    color = '#3b82f6' if kind == 'budget' else '#10b981'
                    border = '#2563eb' if kind == 'budget' else '#059669'
                    
                    events.append({
                        'id': f"assign-{assign.id}-{kind}",
                        'title': f"{prefix}: {order.client_property.client.name}",
                        'start': dt.isoformat(),
                        'end': (dt + buffer).isoformat(),
                        'backgroundColor': color,
                        'borderColor': border,
                        'url': reverse_lazy('service_order_detail', kwargs={'order_id': order.id}),
                        'extendedProps': {
                            'client': order.client_property.client.name,
                            'address': f"{order.client_property.address}, {order.client_property.number}",
                            'neighborhood': order.client_property.neighborhood,
                            'status': order.get_status_display(),
                            'type': kind,
                            'team': team,
                            'description': order.description[:100] + '...' if len(order.description) > 100 else order.description
                        }
                    })
    else:
        # Visão Geral: Mostra todos os agendamentos das OS
        orders = ServiceOrder.objects.filter(
            Q(budget_scheduled_at__isnull=False) | Q(execution_scheduled_at__isnull=False)
        ).select_related('client_property__client', 'client_property').prefetch_related('team_members__professional')
        
        for order in orders:
            team = [m.professional.name for m in order.team_members.all()]
            
            if order.budget_scheduled_at:
                events.append({
                    'id': f"budget-{order.id}",
                    'title': f"ORÇ: {order.client_property.client.name}",
                    'start': order.budget_scheduled_at.isoformat(),
                    'end': (order.budget_scheduled_at + buffer).isoformat(),
                    'backgroundColor': '#3b82f6', # Blue 500
                    'borderColor': '#2563eb',
                    'url': reverse_lazy('service_order_detail', kwargs={'order_id': order.id}),
                    'extendedProps': {
                        'client': order.client_property.client.name,
                        'address': f"{order.client_property.address}, {order.client_property.number}",
                        'neighborhood': order.client_property.neighborhood,
                        'status': order.get_status_display(),
                        'type': 'budget',
                        'team': team,
                        'description': order.description[:100] + '...' if len(order.description) > 100 else order.description
                    }
                })
            
            if order.execution_scheduled_at:
                events.append({
                    'id': f"exec-{order.id}",
                    'title': f"EXEC: {order.client_property.client.name}",
                    'start': order.execution_scheduled_at.isoformat(),
                    'end': (order.execution_scheduled_at + buffer).isoformat(),
                    'backgroundColor': '#10b981', # Emerald 500
                    'borderColor': '#059669',
                    'url': reverse_lazy('service_order_detail', kwargs={'order_id': order.id}),
                    'extendedProps': {
                        'client': order.client_property.client.name,
                        'address': f"{order.client_property.address}, {order.client_property.number}",
                        'neighborhood': order.client_property.neighborhood,
                        'status': order.get_status_display(),
                        'type': 'execution',
                        'team': team,
                        'description': order.description[:100] + '...' if len(order.description) > 100 else order.description
                    }
                })

    # Adicionar Bloqueios de Agenda
    blocks = ProfessionalScheduleBlock.objects.all()
    if prof_id:
        blocks = blocks.filter(professional_id=prof_id)

    for block in blocks:
        events.append({
            'id': f"block-{block.id}",
            'title': f"BLOQUEIO: {block.professional.name} - {block.reason}",
            'start': block.start_at.isoformat(),
            'end': block.end_at.isoformat(),
            'backgroundColor': '#64748b', # Slate 500
            'borderColor': '#475569',
            'allDay': block.is_all_day,
            'extendedProps': {
                'type': 'block',
                'professional': block.professional.name,
                'reason': block.reason
            }
        })

    return JsonResponse(events, safe=False)

def service_order_calendar(request):
    professionals = Professional.objects.filter(is_active=True)
    roles = ProfessionalRole.objects.all()
    status_choices = ServiceOrder.Status.choices
    return render(request, 'services/orders/calendar.html', {
        'professionals': professionals,
        'professional_roles': roles,
        'status_choices': status_choices,
        'title': 'Agenda Geral'
    })

def api_check_availability(request):
    prof_id = request.GET.get('professional_id')
    timestamp_str = request.GET.get('timestamp')
    
    if not prof_id or not timestamp_str:
        return JsonResponse({'available': True, 'message': 'Parâmetros incompletos.'})
        
    try:
        professional = get_object_or_404(Professional, id=prof_id)
        timestamp = parse(timestamp_str)
        available, message = check_professional_availability(professional, timestamp)
        return JsonResponse({'available': available, 'message': message})
    except Exception as e:
        return JsonResponse({'available': False, 'message': str(e)})

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
@require_POST
def api_quick_create_client(request):
    try:
        data = json.loads(request.body)
        client = Client.objects.create(name=data.get('name'), cpf=data.get('cpf'))
        return JsonResponse({'id': str(client.id), 'name': client.name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_POST
def api_quick_create_property(request):
    try:
        data = json.loads(request.body)
        client = get_object_or_404(Client, id=data.get('client_id'))
        prop = Property.objects.create(
            client=client,
            classification=data.get('classification', Property.PropertyType.CASA),
            address=data.get('address'),
            number=data.get('number'),
            neighborhood=data.get('neighborhood'),
            city=data.get('city'),
            state=data.get('state'),
            cep=data.get('cep')
        )
        return JsonResponse({'id': str(prop.id), 'address': f"{prop.address}, {prop.number}"})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_POST
def api_quick_create_order(request):
    try:
        data = json.loads(request.body)
        prop = get_object_or_404(Property, id=data.get('property_id'))
        sched_type = data.get('type', 'INSPECTION')
        scheduled_at = parse(data.get('scheduled_at'))
        team_data = data.get('team', [])

        # Map type to Status
        status = ServiceOrder.Status.WAITING_BUDGET
        if sched_type == 'INSPECTION':
            status = ServiceOrder.Status.BUDGET_SCHEDULED
        elif sched_type == 'EXECUTION':
            status = ServiceOrder.Status.WAITING_EXECUTION
        elif sched_type == 'WARRANTY':
            status = ServiceOrder.Status.WAITING_EXECUTION

        # Create Order
        order = ServiceOrder.objects.create(
            client_property=prop,
            status=status,
            description=data.get('description', '')
        )
        
        # Set main OS schedule based on type
        if sched_type == 'INSPECTION':
            order.budget_scheduled_at = scheduled_at
        else:
            order.execution_scheduled_at = scheduled_at
        order.save()

        # Add Team Members
        for member in team_data:
            prof = get_object_or_404(Professional, id=member.get('professional_id'))
            role_id = member.get('role_id')
            role = None
            if role_id:
                role = get_object_or_404(ProfessionalRole, id=role_id)
            else:
                role = prof.roles.first()
            
            ServiceOrderTeam.objects.create(
                service_order=order,
                professional=prof,
                role=role,
                category=sched_type # Also sync team category
            )

        return JsonResponse({'id': str(order.id), 'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def api_get_properties(request):
    client_id = request.GET.get('client_id')
    properties = Property.objects.filter(client_id=client_id)
    data = [{'id': str(p.id), 'address': f"{p.address}, {p.number}"} for p in properties]
    return JsonResponse(data, safe=False)

def api_get_clients(request):
    clients = Client.objects.all().order_by('name')
    data = [{'id': str(c.id), 'name': c.name} for c in clients]
    return JsonResponse(data, safe=False)
