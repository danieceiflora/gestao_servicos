import logging
from decimal import Decimal
from datetime import date
from django.db import transaction
from dateutil.relativedelta import relativedelta
from .models import Expense, ExpenseInstallment

logger = logging.getLogger(__name__)

def generate_expense_installments(expense, first_due_date=None):
    """
    Gera parcelas para uma despesa.
    A quantidade de parcelas é definida por expense.installments_count.
    Os vencimentos são calculados com base em expense.frequency:
    - 'DIARIA': Próximo dia corrido (+1 dia)
    - 'SEMANAL': Mesmo dia da semana seguinte (+7 dias)
    - 'QUINZENAL': +15 dias
    - 'MENSAL': Mesmo dia do mês seguinte
    - 'ANUAL': Mesma data no ano seguinte
    
    Args:
        expense: Instância do modelo Expense.
        first_due_date: Data de vencimento da primeira parcela (default: expense.issue_date).
        
    Returns:
        tuple: (success (bool), message (str))
    """
    try:
        with transaction.atomic():
            # Apenas como medida de segurança, limpa parcelas pendentes anteriores
            # caso seja uma "regeneração" das parcelas para essa despesa.
            if expense.installments.exists():
                pending_installments = expense.installments.filter(status=ExpenseInstallment.Status.PENDENTE)
                # Opcional: Verificar se o total de pendentes é igual ao total de parcelas.
                # Por ora, deletamos as pendentes para recriar de forma limpa.
                pending_installments.delete()

            installments_count = expense.installments_count
            if installments_count <= 0:
                installments_count = 1

            total_amount = expense.total_amount
            
            # Divisão do valor total pela quantidade de parcelas
            # Usa quantize para garantir precisão de duas casas decimais
            base_amount = (total_amount / Decimal(installments_count)).quantize(Decimal('0.01'))
            sum_base = base_amount * Decimal(installments_count)
            remainder = total_amount - sum_base

            current_date = first_due_date or expense.issue_date
            if not current_date:
                current_date = date.today()

            installments_to_create = []

            for i in range(1, installments_count + 1):
                amount = base_amount
                # Adiciona o restante (centavos de diferença) na primeira parcela ou última
                # Geralmente no Brasil os centavos residuais ficam na primeira ou última.
                # Aqui adicionamos na última.
                if i == installments_count:
                    amount += remainder

                installment = ExpenseInstallment(
                    expense=expense,
                    installment_number=f"{i}/{installments_count}",
                    amount=amount,
                    due_date=current_date,
                    status=ExpenseInstallment.Status.PENDENTE
                )
                installments_to_create.append(installment)

                # Calcula a data de vencimento da próxima parcela
                if i < installments_count:
                    # Se tiver frequência definida e a despesa for recorrente (is_recurrent=True)
                    # Ou mesmo se for apenas um parcelamento, usa a frequência indicada.
                    if expense.frequency:
                        if expense.frequency == Expense.Frequency.DIARIA:
                            current_date += relativedelta(days=1)
                        elif expense.frequency == Expense.Frequency.SEMANAL:
                            current_date += relativedelta(days=7)
                        elif expense.frequency == Expense.Frequency.QUINZENAL:
                            current_date += relativedelta(days=15)
                        elif expense.frequency == Expense.Frequency.MENSAL:
                            current_date += relativedelta(months=1)
                        elif expense.frequency == Expense.Frequency.ANUAL:
                            current_date += relativedelta(years=1)
                        else:
                            current_date += relativedelta(months=1) # Fallback
                    else:
                        # Se não houver frequency explícita, mas houver mais de uma parcela,
                        # assume-se o padrão mensal de parcelamentos.
                        current_date += relativedelta(months=1)

            # Salva todas as parcelas de uma vez de forma eficiente
            ExpenseInstallment.objects.bulk_create(installments_to_create)
            
            return True, f"{len(installments_to_create)} parcelas geradas com sucesso."
            
    except Exception as e:
        logger.error(f"Erro ao gerar parcelas para a despesa {expense.id}: {str(e)}")
        return False, f"Erro ao gerar parcelas: {str(e)}"
