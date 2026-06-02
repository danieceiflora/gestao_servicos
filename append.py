import sys
import os

with open(sys.argv[1], 'a', encoding='utf-8') as f:
    f.write("""
# --- CONTAS A PAGAR (DESPESAS) ---

@login_required
@user_passes_test(is_manager)
def expense_list(request):
    expenses = Expense.objects.all().order_by('-issue_date')
    
    q = request.GET.get('q')
    if q:
        expenses = expenses.filter(
            Q(description__icontains=q) | 
            Q(supplier__name__icontains=q)
        )
        
    paginator = Paginator(expenses, 20)
    page = request.GET.get('page')
    expenses_page = paginator.get_page(page)
    
    context = {
        'expenses': expenses_page,
        'title': 'Contas a Pagar',
        'active_menu': 'finance'
    }
    return render(request, 'services/finance/expense_list.html', context)

@login_required
@user_passes_test(is_manager)
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                expense = form.save()
                # Gera as parcelas via Engine
                generate_expense_installments(expense)
                messages.success(request, "Despesa criada com sucesso!")
                return redirect('expense_list') # TODO: ou expense_detail
    else:
        form = ExpenseForm()
        
    context = {
        'form': form,
        'title': 'Nova Conta a Pagar',
        'is_edit': False
    }
    return render(request, 'services/finance/expense_form.html', context)

@login_required
@user_passes_test(is_manager)
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                # Se as parcelas mudam dependendo da frequência, o ideal seria atualizar as parcelas (complexo).
                # Por ora, mantemos o simples.
                messages.success(request, "Despesa atualizada com sucesso!")
                return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
        
    context = {
        'form': form,
        'title': f'Editar Despesa: {expense.description}',
        'is_edit': True
    }
    return render(request, 'services/finance/expense_form.html', context)

@login_required
@user_passes_test(is_manager)
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Despesa excluída com sucesso!")
        return redirect('expense_list')
    # Se for GET, podemos renderizar uma pág de confirmação, ou só redirecionar (melhor POST via botão)
    return redirect('expense_list')

@login_required
@user_passes_test(is_manager)
def render_expense_installments_preview(request):
    try:
        total_amount = Decimal(request.GET.get('total_amount', '0').replace(',', '.'))
        installments_count = int(request.GET.get('installments_count', '1'))
        frequency = request.GET.get('frequency', '')
        issue_date_str = request.GET.get('issue_date')
        
        issue_date = timezone.now().date()
        if issue_date_str:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()

        # Simulação de geração usando os utilitários da expense_engine, mas em memória
        from dateutil.relativedelta import relativedelta
        from datetime import timedelta
        
        preview_installments = []
        base_amount = total_amount / installments_count
        remainder = total_amount - (base_amount * installments_count)
        
        current_date = issue_date
        for i in range(installments_count):
            amount = base_amount
            if i == installments_count - 1:
                amount += remainder
                
            preview_installments.append({
                'installment_number': i + 1,
                'amount': amount,
                'due_date': current_date
            })
            
            # Incrementa a data
            if frequency == Expense.Frequency.DAILY:
                current_date += timedelta(days=1)
            elif frequency == Expense.Frequency.WEEKLY:
                current_date += timedelta(weeks=1)
            elif frequency == Expense.Frequency.BIWEEKLY:
                current_date += timedelta(weeks=2)
            elif frequency == Expense.Frequency.MONTHLY:
                current_date += relativedelta(months=1)
            elif frequency == Expense.Frequency.YEARLY:
                current_date += relativedelta(years=1)
            
    except (ValueError, TypeError, Exception):
        preview_installments = []
        
    return render(request, 'services/partials/expense_installments_preview.html', {
        'installments': preview_installments
    })

""")
