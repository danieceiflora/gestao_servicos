from django.core.management.base import BaseCommand
from django.utils import timezone
from core.tz_utils import local_today
from services.models import RecurrenceRule, ExpenseInstallment, FinanceSettings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Gera registros de contas a pagar a partir das regras de recorrência ativas'

    def handle(self, *args, **kwargs):
        settings_obj = FinanceSettings.objects.first()
        days_ahead = settings_obj.days_before_generation if settings_obj else 7
        today = local_today()
        target_date = today + timezone.timedelta(days=days_ahead)

        self.stdout.write(
            f'Verificando recorrências: hoje={today}, horizonte={target_date} ({days_ahead} dias)'
        )

        rules = RecurrenceRule.objects.filter(is_active=True).select_related(
            'supplier', 'category'
        ).prefetch_related('expense_templates')

        total_created = 0

        for rule in rules:
            due_dates = rule.get_due_dates_in_range(today, target_date)

            template_expense = rule.expense_templates.first()

            for due_date in due_dates:
                already_exists = ExpenseInstallment.objects.filter(
                    recurrence_rule=rule,
                    recurrence_due_date=due_date,
                ).exists()

                if already_exists:
                    continue

                ExpenseInstallment.objects.create(
                    expense=template_expense,
                    recurrence_rule=rule,
                    recurrence_due_date=due_date,
                    installment_number=due_date.strftime('%m/%Y'),
                    due_date=due_date,
                    amount=rule.amount,
                    status=ExpenseInstallment.Status.PENDENTE,
                )
                total_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  [+] {rule.description} | Vencimento: {due_date.strftime("%d/%m/%Y")}'
                    )
                )

        self.stdout.write(self.style.SUCCESS(f'\nTotal gerado: {total_created} parcela(s).'))
