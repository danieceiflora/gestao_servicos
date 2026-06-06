from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Avg, Sum, F, Q, ExpressionWrapper, DurationField
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import json
import calendar as _cal

from .models import (
    ServiceOrder, ServiceOrderTask, ServiceOrderTeam, Professional,
    Occurrence, User, MaintenanceContract, MaintenanceVisit,
    SalePayment, Billing, Installment, InstallmentPayment, Client,
)

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    relativedelta = None


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


def _last_n_months(n, ref_date=None):
    """Returns list of (year, month, label) for last N months including current."""
    if ref_date is None:
        ref_date = date.today()
    result = []
    for i in range(n - 1, -1, -1):
        if relativedelta:
            d = date(ref_date.year, ref_date.month, 1) - relativedelta(months=i)
        else:
            # Fallback: approximate
            total_months = ref_date.month - 1 - i
            year = ref_date.year + total_months // 12
            month = total_months % 12 + 1
            d = date(year, month, 1)
        result.append((d.year, d.month, d.strftime('%b/%y')))
    return result


@login_required
@user_passes_test(is_manager)
def bi_operacional(request):
    now = timezone.now()
    today = now.date()

    period = request.GET.get('period', '90')
    try:
        days = int(period)
    except ValueError:
        days = 90
    since = now - timedelta(days=days)

    orders_qs = ServiceOrder.objects.filter(created_at__gte=since)

    # --- OS por status ---
    status_labels = []
    status_values = []
    status_colors = []
    COLOR_MAP = {
        'AGUARDANDO_VISITA': '#94a3b8',
        'ORCAMENTO_AGENDADO': '#60a5fa',
        'ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO': '#a78bfa',
        'AGUARDANDO_APROVACAO': '#fbbf24',
        'APROVADO_AGUARDANDO_AGENDAMENTO': '#34d399',
        'REPROVADO_PELO_CLIENTE': '#f87171',
        'AGUARDANDO_EXECUCAO': '#38bdf8',
        'AGUARDANDO_PAGAMENTO': '#fb923c',
        'PAGAMENTO_PARCIAL': '#facc15',
        'FINALIZADO': '#22c55e',
        'CANCELADO': '#e2e8f0',
        'GARANTIA': '#c084fc',
    }
    for s in ServiceOrder.Status:
        count = orders_qs.filter(status=s).count()
        if count > 0:
            status_labels.append(s.label)
            status_values.append(count)
            status_colors.append(COLOR_MAP.get(s.value, '#94a3b8'))

    # --- Funil de orçamentos ---
    budgets_sent = orders_qs.filter(
        status__in=[
            ServiceOrder.Status.AGUARDANDO_APROVACAO,
            ServiceOrder.Status.APROVADO_AGUARDANDO_AGENDAMENTO,
            ServiceOrder.Status.REPROVADO_PELO_CLIENTE,
            ServiceOrder.Status.AGUARDANDO_EXECUCAO,
            ServiceOrder.Status.AGUARDANDO_PAGAMENTO,
            ServiceOrder.Status.PAGAMENTO_PARCIAL,
            ServiceOrder.Status.FINALIZADO,
        ]
    ).filter(
        Q(chatwoot_budget_message_id__isnull=False) |
        Q(client_budget_approved_at__isnull=False) |
        Q(client_budget_responded_at__isnull=False)
    ).count()

    budgets_approved = orders_qs.filter(
        client_budget_approved_at__isnull=False
    ).count()

    budgets_rejected = orders_qs.filter(
        status=ServiceOrder.Status.REPROVADO_PELO_CLIENTE
    ).count()

    budgets_pending = orders_qs.filter(
        status=ServiceOrder.Status.AGUARDANDO_APROVACAO
    ).count()

    conversion_rate = round(
        (budgets_approved / budgets_sent * 100) if budgets_sent > 0 else 0, 1
    )

    # --- Tempo médio de atendimento ---
    finished_qs = ServiceOrder.objects.filter(
        status=ServiceOrder.Status.FINALIZADO,
        finished_at__gte=since,
        finished_at__isnull=False,
    ).values('created_at', 'finished_at')

    avg_time_days = None
    total_s = 0
    count_f = 0
    for o in finished_qs:
        if o['finished_at'] and o['created_at']:
            delta = o['finished_at'] - o['created_at']
            total_s += max(delta.total_seconds(), 0)
            count_f += 1
    if count_f > 0:
        avg_time_days = round(total_s / count_f / 86400, 1)

    # --- OS por bairro (top 10) ---
    neighborhood_qs = (
        orders_qs
        .values(bairro=F('client_property__neighborhood'))
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    neighborhood_labels = [n['bairro'] or 'Não informado' for n in neighborhood_qs]
    neighborhood_values = [n['count'] for n in neighborhood_qs]

    # --- Tendência mensal (últimos 6 meses) ---
    months_meta = _last_n_months(6)
    months_labels = [m[2] for m in months_meta]
    monthly_created_values = []
    monthly_finished_values = []

    for y, m, _ in months_meta:
        _, last_day = _cal.monthrange(y, m)
        tz = timezone.get_current_timezone()
        ms = timezone.make_aware(datetime(y, m, 1), tz)
        me = timezone.make_aware(datetime(y, m, last_day, 23, 59, 59), tz)

        created_count = ServiceOrder.objects.filter(created_at__gte=ms, created_at__lte=me).count()
        finished_count = ServiceOrder.objects.filter(
            status=ServiceOrder.Status.FINALIZADO,
            finished_at__gte=ms,
            finished_at__lte=me,
        ).count()
        monthly_created_values.append(created_count)
        monthly_finished_values.append(finished_count)

    return render(request, 'services/bi/operacional.html', {
        'title': 'Painel Operacional',
        'period': str(days),
        'total_orders': orders_qs.count(),
        'total_finished': count_f,
        'total_cancelled': orders_qs.filter(status=ServiceOrder.Status.CANCELADO).count(),
        'active_count': orders_qs.exclude(
            status__in=[ServiceOrder.Status.FINALIZADO, ServiceOrder.Status.CANCELADO]
        ).count(),
        # Funil
        'budgets_sent': budgets_sent,
        'budgets_approved': budgets_approved,
        'budgets_rejected': budgets_rejected,
        'budgets_pending': budgets_pending,
        'conversion_rate': conversion_rate,
        # Tempo
        'avg_time_days': avg_time_days,
        # Charts JSON
        'status_labels_json': json.dumps(status_labels),
        'status_values_json': json.dumps(status_values),
        'status_colors_json': json.dumps(status_colors),
        'neighborhood_labels_json': json.dumps(neighborhood_labels),
        'neighborhood_values_json': json.dumps(neighborhood_values),
        'months_labels_json': json.dumps(months_labels),
        'monthly_created_json': json.dumps(monthly_created_values),
        'monthly_finished_json': json.dumps(monthly_finished_values),
    })


@login_required
@user_passes_test(is_manager)
def bi_produtividade(request):
    now = timezone.now()
    month = int(request.GET.get('month', now.month))
    year = int(request.GET.get('year', now.year))

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime(year, month, 1), tz)
    if month == 12:
        end_dt = timezone.make_aware(datetime(year + 1, 1, 1), tz)
    else:
        end_dt = timezone.make_aware(datetime(year, month + 1, 1), tz)

    professionals = Professional.objects.filter(is_active=True).order_by('name')

    tech_data = {
        str(p.id): {
            'name': p.name,
            'os_count': 0,
            'total_seconds': 0,
            'occurrences_count': 0,
            'task_ids': set(),
        }
        for p in professionals
    }

    # Allocations for finished execution tasks in period
    allocations = (
        ServiceOrderTeam.objects
        .filter(
            task__task_type=ServiceOrderTask.TaskType.EXECUCAO,
            task__status=ServiceOrderTask.TaskStatus.CONCLUIDO,
            task__finished_at__gte=start_dt,
            task__finished_at__lt=end_dt,
        )
        .select_related('professional', 'task')
    )

    for alloc in allocations:
        pid = str(alloc.professional_id)
        if pid not in tech_data:
            continue
        task_id = str(alloc.task_id)
        if task_id not in tech_data[pid]['task_ids']:
            tech_data[pid]['os_count'] += 1
            tech_data[pid]['task_ids'].add(task_id)
        if alloc.task.started_at and alloc.task.finished_at:
            delta = alloc.task.finished_at - alloc.task.started_at
            tech_data[pid]['total_seconds'] += max(delta.total_seconds(), 0)

    # Occurrences linked to tasks in period, per tech
    occ_by_task = {}
    for occ in Occurrence.objects.filter(
        task__task_type=ServiceOrderTask.TaskType.EXECUCAO,
        task__finished_at__gte=start_dt,
        task__finished_at__lt=end_dt,
    ).values('task_id'):
        tid = str(occ['task_id'])
        occ_by_task[tid] = occ_by_task.get(tid, 0) + 1

    for alloc in allocations:
        pid = str(alloc.professional_id)
        tid = str(alloc.task_id)
        if pid in tech_data and tid in occ_by_task:
            tech_data[pid]['occurrences_count'] += occ_by_task[tid]

    result = []
    for pid, d in tech_data.items():
        if d['os_count'] > 0:
            avg_h = round(d['total_seconds'] / d['os_count'] / 3600, 1)
            total_h = round(d['total_seconds'] / 3600, 1)
            result.append({
                'name': d['name'],
                'os_count': d['os_count'],
                'total_hours': total_h,
                'avg_hours': avg_h,
                'occurrences': d['occurrences_count'],
            })

    result.sort(key=lambda x: x['os_count'], reverse=True)

    # Global stats for the period (not per-tech filter)
    total_tasks_period = ServiceOrderTask.objects.filter(
        task_type=ServiceOrderTask.TaskType.EXECUCAO,
        status=ServiceOrderTask.TaskStatus.CONCLUIDO,
        finished_at__gte=start_dt,
        finished_at__lt=end_dt,
    ).count()

    total_occ_period = Occurrence.objects.filter(
        task__task_type=ServiceOrderTask.TaskType.EXECUCAO,
        task__finished_at__gte=start_dt,
        task__finished_at__lt=end_dt,
    ).count()

    return render(request, 'services/bi/produtividade.html', {
        'title': 'Produtividade da Equipe',
        'result': result,
        'total_tasks_period': total_tasks_period,
        'total_occ_period': total_occ_period,
        'tech_names_json': json.dumps([r['name'] for r in result]),
        'tech_os_json': json.dumps([r['os_count'] for r in result]),
        'tech_hours_json': json.dumps([r['total_hours'] for r in result]),
        'months': range(1, 13),
        'years': range(now.year - 2, now.year + 1),
        'selected_month': month,
        'selected_year': year,
    })


@login_required
@user_passes_test(is_manager)
def bi_manutencao(request):
    now = timezone.now()
    today = now.date()
    month = int(request.GET.get('month', now.month))
    year = int(request.GET.get('year', now.year))

    _, last_day = _cal.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    # Contract stats
    contracts = MaintenanceContract.objects.all()
    contract_stats = {
        'ativo': contracts.filter(status=MaintenanceContract.Status.ATIVO).count(),
        'pausado': contracts.filter(status=MaintenanceContract.Status.PAUSADO).count(),
        'encerrado': contracts.filter(status=MaintenanceContract.Status.ENCERRADO).count(),
    }
    contract_stats['total'] = sum(contract_stats.values())

    # Visits this month
    visits_month = MaintenanceVisit.objects.filter(
        scheduled_date__range=(month_start, month_end)
    )
    visits_stats = {
        'total': visits_month.count(),
        'concluidas': visits_month.filter(status=MaintenanceVisit.Status.CONCLUIDA).count(),
        'agendadas': visits_month.filter(status=MaintenanceVisit.Status.AGENDADA).count(),
        'em_andamento': visits_month.filter(status=MaintenanceVisit.Status.EM_ANDAMENTO).count(),
        'canceladas': visits_month.filter(status=MaintenanceVisit.Status.CANCELADA).count(),
    }
    if visits_stats['total'] > 0:
        visits_stats['pct_concluidas'] = round(
            visits_stats['concluidas'] / visits_stats['total'] * 100, 1
        )
    else:
        visits_stats['pct_concluidas'] = 0

    # Overdue visits
    overdue = (
        MaintenanceVisit.objects
        .filter(
            scheduled_date__lt=today,
            status=MaintenanceVisit.Status.AGENDADA,
        )
        .select_related(
            'contract__asset__client_property__client',
            'contract__primary_technician',
        )
        .order_by('scheduled_date')[:20]
    )

    # Commission by technician
    tech_commission = {}
    for visit in (
        visits_month
        .filter(status=MaintenanceVisit.Status.CONCLUIDA)
        .select_related('contract__asset', 'contract__primary_technician', 'executed_by')
    ):
        recipient = visit.commission_recipient()
        if recipient:
            key = str(recipient.id)
            if key not in tech_commission:
                tech_commission[key] = {
                    'name': recipient.name,
                    'visits': 0,
                    'commission': Decimal('0'),
                }
            tech_commission[key]['visits'] += 1
            tech_commission[key]['commission'] += visit.commission_value()

    tech_commission_list = sorted(
        tech_commission.values(), key=lambda x: x['commission'], reverse=True
    )

    # Monthly trend (last 6 months)
    months_meta = _last_n_months(6, date(year, month, 1))
    months_labels = [m[2] for m in months_meta]
    months_done = []
    months_scheduled = []
    for y, m_num, _ in months_meta:
        _, ld = _cal.monthrange(y, m_num)
        ms = date(y, m_num, 1)
        me = date(y, m_num, ld)
        done = MaintenanceVisit.objects.filter(
            scheduled_date__range=(ms, me),
            status=MaintenanceVisit.Status.CONCLUIDA,
        ).count()
        sched = MaintenanceVisit.objects.filter(
            scheduled_date__range=(ms, me)
        ).count()
        months_done.append(done)
        months_scheduled.append(sched)

    return render(request, 'services/bi/manutencao.html', {
        'title': 'Dashboard de Manutenção',
        'contract_stats': contract_stats,
        'visits_stats': visits_stats,
        'overdue': overdue,
        'tech_commission': tech_commission_list,
        'months_labels_json': json.dumps(months_labels),
        'months_done_json': json.dumps(months_done),
        'months_scheduled_json': json.dumps(months_scheduled),
        'months': range(1, 13),
        'years': range(now.year - 2, now.year + 1),
        'selected_month': month,
        'selected_year': year,
    })
