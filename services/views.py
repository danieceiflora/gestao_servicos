from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Client, Property, ServiceOrder, ServiceMedia, ServiceItem
from .forms import (
    ClientForm, PhoneFormSet, EmailFormSet, PropertyFormSet, 
    PropertyForm, ServiceInspectionForm, ServiceItemFormSet,
    ServiceOrderForm
)

def home(request):
    active_orders = ServiceOrder.objects.exclude(status__in=[ServiceOrder.Status.FINISHED, ServiceOrder.Status.CANCELLED]).count()
    pending_approval = ServiceOrder.objects.filter(status=ServiceOrder.Status.PENDING_APPROVAL).count()
    warranty_orders = ServiceOrder.objects.filter(status=ServiceOrder.Status.WARRANTY).count()
    
    recent_orders = ServiceOrder.objects.all().order_by('-updated_at')[:5]
    
    return render(request, 'services/home.html', {
        'active_orders': active_orders,
        'pending_approval': pending_approval,
        'warranty_orders': warranty_orders,
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

def service_order_create(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)
    if request.method == 'POST':
        form = ServiceInspectionForm(request.POST, request.FILES)
        if form.is_valid():
            service_order = form.save(commit=False)
            service_order.client_property = property_obj
            service_order.status = ServiceOrder.Status.INSPECTION
            service_order.save()
            
            # Handle Multiple Files
            files = request.FILES.getlist('files')
            for f in files:
                ServiceMedia.objects.create(
                    service_order=service_order,
                    file=f,
                    media_type=ServiceMedia.MediaType.INSPECTION
                )
            
            messages.success(request, 'Ordem de Serviço criada e vistoria iniciada!')
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
            
            # Auto-update status only if it's still in INSPECTION and items were added
            if order.status == ServiceOrder.Status.INSPECTION and order.items.exists():
                order.status = ServiceOrder.Status.BUDGETING
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
