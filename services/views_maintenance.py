from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from .models import (
    User, Asset, AssetCategory, MaintenanceContract,
    MaintenanceVisit, MaintenanceMonthlyClosing, MaintenanceClosingEntry,
    Professional, Property, Client,
)
from .forms_maintenance import (
    AssetCategoryForm, AssetForm, MaintenanceContractForm, MaintenanceVisitForm,
)


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


# ─── ASSET CATEGORIES ────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_manager)
def asset_category_list(request):
    categories = AssetCategory.objects.all().order_by('name')
    return render(request, 'services/maintenance/asset_category_list.html', {
        'categories': categories,
        'title': 'Categorias de Equipamentos',
    })


@login_required
@user_passes_test(is_manager)
def asset_category_create(request):
    if request.method == 'POST':
        form = AssetCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoria criada com sucesso!')
            return redirect('asset_category_list')
    else:
        form = AssetCategoryForm()
    return render(request, 'services/maintenance/asset_category_form.html', {
        'form': form, 'title': 'Nova Categoria',
    })


@login_required
@user_passes_test(is_manager)
def asset_category_edit(request, pk):
    category = get_object_or_404(AssetCategory, pk=pk)
    if request.method == 'POST':
        form = AssetCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoria atualizada com sucesso!')
            return redirect('asset_category_list')
    else:
        form = AssetCategoryForm(instance=category)
    return render(request, 'services/maintenance/asset_category_form.html', {
        'form': form, 'title': f'Editar: {category.name}', 'category': category,
    })


# ─── ASSETS ──────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_manager)
def asset_list(request):
    assets = Asset.objects.select_related(
        'client_property__client', 'category'
    ).order_by('client_property__client__name', 'name')

    client_id = request.GET.get('client')
    if client_id:
        assets = assets.filter(client_property__client_id=client_id)

    clients = Client.objects.order_by('name')
    return render(request, 'services/maintenance/asset_list.html', {
        'assets': assets,
        'clients': clients,
        'selected_client': client_id,
        'title': 'Equipamentos / Bens',
    })


@login_required
@user_passes_test(is_manager)
def asset_create(request):
    if request.method == 'POST':
        form = AssetForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipamento cadastrado com sucesso!')
            return redirect('asset_list')
    else:
        form = AssetForm()
    clients = Client.objects.order_by('name')
    return render(request, 'services/maintenance/asset_form.html', {
        'form': form, 'title': 'Novo Equipamento', 'clients': clients,
    })


@login_required
@user_passes_test(is_manager)
def asset_edit(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == 'POST':
        form = AssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipamento atualizado com sucesso!')
            return redirect('asset_list')
    else:
        form = AssetForm(instance=asset)
    clients = Client.objects.order_by('name')
    return render(request, 'services/maintenance/asset_form.html', {
        'form': form, 'title': f'Editar: {asset.name}',
        'asset': asset, 'clients': clients,
    })


@login_required
@user_passes_test(is_manager)
def api_get_properties_for_asset(request):
    client_id = request.GET.get('client_id')
    if not client_id:
        return JsonResponse([], safe=False)
    props = Property.objects.filter(client_id=client_id).order_by('address')
    data = [{'id': str(p.id), 'label': f"{p.address}, {p.number or 'S/N'}"} for p in props]
    return JsonResponse(data, safe=False)


# ─── CONTRACTS ───────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_manager)
def contract_list(request):
    contracts = MaintenanceContract.objects.select_related(
        'asset__client_property__client', 'asset__category', 'primary_technician'
    ).order_by('status', 'asset__client_property__client__name')

    status_filter = request.GET.get('status')
    tech_filter = request.GET.get('technician')
    if status_filter:
        contracts = contracts.filter(status=status_filter)
    if tech_filter:
        contracts = contracts.filter(primary_technician_id=tech_filter)

    professionals = Professional.objects.filter(is_active=True).order_by('name')
    return render(request, 'services/maintenance/contract_list.html', {
        'contracts': contracts,
        'professionals': professionals,
        'status_choices': MaintenanceContract.Status.choices,
        'selected_status': status_filter,
        'selected_tech': tech_filter,
        'title': 'Contratos de Manutenção',
    })


@login_required
@user_passes_test(is_manager)
def contract_create(request):
    if request.method == 'POST':
        form = MaintenanceContractForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contrato criado com sucesso!')
            return redirect('contract_list')
    else:
        form = MaintenanceContractForm()
    return render(request, 'services/maintenance/contract_form.html', {
        'form': form, 'title': 'Novo Contrato de Manutenção',
    })


@login_required
@user_passes_test(is_manager)
def contract_edit(request, pk):
    contract = get_object_or_404(MaintenanceContract, pk=pk)
    if request.method == 'POST':
        form = MaintenanceContractForm(request.POST, instance=contract)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contrato atualizado com sucesso!')
            return redirect('contract_detail', pk=pk)
    else:
        form = MaintenanceContractForm(instance=contract)
    return render(request, 'services/maintenance/contract_form.html', {
        'form': form, 'title': f'Editar Contrato — {contract.asset.name}', 'contract': contract,
    })


@login_required
@user_passes_test(is_manager)
def contract_detail(request, pk):
    contract = get_object_or_404(
        MaintenanceContract.objects.select_related(
            'asset__client_property__client', 'asset__category', 'primary_technician'
        ), pk=pk
    )
    visits = contract.visits.select_related('executed_by').order_by('-scheduled_date')

    month_filter = request.GET.get('month')
    year_filter = request.GET.get('year')
    if month_filter and year_filter:
        visits = visits.filter(
            scheduled_date__month=int(month_filter),
            scheduled_date__year=int(year_filter),
        )

    today = timezone.localdate()
    expected_this_month = contract.calculate_expected_visits(today.month, today.year)
    commission_per_visit = contract.commission_per_visit(today.month, today.year)

    return render(request, 'services/maintenance/contract_detail.html', {
        'contract': contract,
        'visits': visits,
        'expected_this_month': expected_this_month,
        'commission_per_visit': commission_per_visit,
        'month_filter': month_filter,
        'year_filter': year_filter,
        'months': range(1, 13),
        'title': f'Contrato — {contract.asset.name}',
    })


@login_required
@user_passes_test(is_manager)
def contract_toggle_status(request, pk):
    contract = get_object_or_404(MaintenanceContract, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(MaintenanceContract.Status.choices):
            contract.status = new_status
            contract.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Status alterado para {contract.get_status_display()}.')
    return redirect('contract_detail', pk=pk)


# ─── VISITS ──────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_manager)
def visit_create(request, contract_id):
    contract = get_object_or_404(MaintenanceContract, pk=contract_id)
    if request.method == 'POST':
        form = MaintenanceVisitForm(request.POST, contract=contract)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.contract = contract
            # Default executante to titular if not set
            if not visit.executed_by and not visit.external_technician_name:
                visit.executed_by = contract.primary_technician
            visit.save()
            messages.success(request, 'Visita registrada com sucesso!')
            return redirect('contract_detail', pk=contract_id)
    else:
        form = MaintenanceVisitForm(contract=contract)
    return render(request, 'services/maintenance/visit_form.html', {
        'form': form, 'contract': contract, 'title': 'Registrar Visita',
    })


@login_required
@user_passes_test(is_manager)
def visit_edit(request, pk):
    visit = get_object_or_404(MaintenanceVisit.objects.select_related('contract'), pk=pk)
    contract = visit.contract
    if request.method == 'POST':
        form = MaintenanceVisitForm(request.POST, instance=visit, contract=contract)
        if form.is_valid():
            form.save()
            messages.success(request, 'Visita atualizada com sucesso!')
            return redirect('contract_detail', pk=contract.pk)
    else:
        form = MaintenanceVisitForm(instance=visit, contract=contract)
    return render(request, 'services/maintenance/visit_form.html', {
        'form': form, 'contract': contract, 'visit': visit, 'title': 'Editar Visita',
    })


@login_required
@user_passes_test(is_manager)
def visit_quick_status(request, pk):
    """AJAX: change visit status quickly from the contract detail page."""
    visit = get_object_or_404(MaintenanceVisit, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(MaintenanceVisit.Status.choices):
            visit.status = new_status
            if new_status == MaintenanceVisit.Status.EM_ANDAMENTO and not visit.check_in_at:
                visit.check_in_at = timezone.now()
            elif new_status == MaintenanceVisit.Status.CONCLUIDA and not visit.check_out_at:
                visit.check_out_at = timezone.now()
            visit.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'status': visit.get_status_display()})
    return redirect('contract_detail', pk=visit.contract_id)


# ─── MONTHLY CLOSING ─────────────────────────────────────────────────────────

def _build_closing_data(month, year):
    """Aggregate completed visits into per-technician commission entries."""
    visits = MaintenanceVisit.objects.filter(
        scheduled_date__month=month,
        scheduled_date__year=year,
        status=MaintenanceVisit.Status.CONCLUIDA,
        is_extra=False,
    ).select_related(
        'contract__asset__client_property__client',
        'contract__primary_technician',
        'executed_by',
    )

    tech_data = {}  # {professional.id: {...}}

    for visit in visits:
        recipient = visit.commission_recipient()
        if not recipient:
            continue

        tech_id = str(recipient.id)
        if tech_id not in tech_data:
            tech_data[tech_id] = {
                'technician': recipient,
                'total_commission': Decimal('0'),
                'visits_count': 0,
                'contracts': {},
            }

        contract_key = str(visit.contract.id)
        if contract_key not in tech_data[tech_id]['contracts']:
            cpv = visit.contract.commission_per_visit(month, year)
            prop = visit.contract.asset.client_property
            tech_data[tech_id]['contracts'][contract_key] = {
                'contract_id': contract_key,
                'asset_name': visit.contract.asset.name,
                'client': visit.contract.client.name,
                'property': f"{prop.address}, {prop.number or 'S/N'}",
                'monthly_value': str(visit.contract.monthly_value),
                'commission_rate': str(visit.contract.commission_rate),
                'commission_per_visit': str(cpv),
                'visits': 0,
                'subtotal': Decimal('0'),
            }

        cpv = Decimal(tech_data[tech_id]['contracts'][contract_key]['commission_per_visit'])
        tech_data[tech_id]['contracts'][contract_key]['visits'] += 1
        tech_data[tech_id]['contracts'][contract_key]['subtotal'] += cpv
        tech_data[tech_id]['total_commission'] += cpv
        tech_data[tech_id]['visits_count'] += 1

    return tech_data


MONTH_CHOICES = [
    (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
    (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
    (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
]


@login_required
@user_passes_test(is_manager)
def closing_list(request):
    closings = MaintenanceMonthlyClosing.objects.prefetch_related('entries__technician').order_by('-year', '-month')
    today = timezone.localdate()
    return render(request, 'services/maintenance/closing_list.html', {
        'closings': closings,
        'month_choices': MONTH_CHOICES,
        'current_month': today.month,
        'current_year': today.year,
        'title': 'Fechamentos Mensais',
    })


@login_required
@user_passes_test(is_manager)
def closing_generate(request):
    """Generate (or regenerate) a draft closing for month/year."""
    if request.method != 'POST':
        return redirect('closing_list')

    try:
        month = int(request.POST.get('month'))
        year = int(request.POST.get('year'))
    except (TypeError, ValueError):
        messages.error(request, 'Mês ou ano inválido.')
        return redirect('closing_list')

    closing, created = MaintenanceMonthlyClosing.objects.get_or_create(
        month=month, year=year,
        defaults={'created_by': request.user},
    )

    if closing.status == MaintenanceMonthlyClosing.Status.APROVADO:
        messages.warning(request, 'Este fechamento já foi aprovado e não pode ser regerado.')
        return redirect('closing_detail', pk=closing.pk)

    with transaction.atomic():
        closing.entries.all().delete()
        tech_data = _build_closing_data(month, year)

        for tech_id, data in tech_data.items():
            detail_list = []
            for c in data['contracts'].values():
                c_copy = dict(c)
                c_copy['subtotal'] = str(c_copy['subtotal'])
                detail_list.append(c_copy)

            MaintenanceClosingEntry.objects.create(
                closing=closing,
                technician=data['technician'],
                total_commission=data['total_commission'],
                visits_count=data['visits_count'],
                detail=detail_list,
            )

    action = 'gerado' if created else 'regerado'
    messages.success(request, f'Fechamento de {closing.month_display()} {action} com sucesso!')
    return redirect('closing_detail', pk=closing.pk)


@login_required
@user_passes_test(is_manager)
def closing_detail(request, pk):
    closing = get_object_or_404(
        MaintenanceMonthlyClosing.objects.prefetch_related('entries__technician'),
        pk=pk,
    )
    total_geral = sum(e.total_commission for e in closing.entries.all())
    return render(request, 'services/maintenance/closing_detail.html', {
        'closing': closing,
        'total_geral': total_geral,
        'title': f'Fechamento — {closing.month_display()}',
    })


@login_required
@user_passes_test(is_manager)
def closing_approve(request, pk):
    closing = get_object_or_404(MaintenanceMonthlyClosing, pk=pk)
    if request.method == 'POST':
        if closing.status == MaintenanceMonthlyClosing.Status.APROVADO:
            messages.warning(request, 'Este fechamento já está aprovado.')
        else:
            closing.status = MaintenanceMonthlyClosing.Status.APROVADO
            closing.closed_at = timezone.now()
            closing.save(update_fields=['status', 'closed_at'])
            messages.success(request, f'Fechamento de {closing.month_display()} aprovado!')
    return redirect('closing_detail', pk=pk)
