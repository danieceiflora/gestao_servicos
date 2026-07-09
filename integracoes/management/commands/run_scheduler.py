import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)


def run_send_scheduled_reminders():
    call_command('send_scheduled_reminders')


def run_send_collection_reminders():
    call_command('send_collection_reminders')


def delete_old_job_executions(max_age=604_800):
    """Remove registros de execução com mais de 7 dias para não acumular no banco."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = (
        'Inicia o scheduler (APScheduler) que dispara diariamente os lembretes agendados '
        'e a régua de cobrança. Processo de longa duração — rodar em um container/serviço dedicado.'
    )

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), 'default')

        scheduler.add_job(
            run_send_scheduled_reminders,
            trigger=CronTrigger(hour=8, minute=0),
            id='send_scheduled_reminders',
            max_instances=1,
            replace_existing=True,
        )
        scheduler.add_job(
            run_send_collection_reminders,
            trigger=CronTrigger(hour=8, minute=5),
            id='send_collection_reminders',
            max_instances=1,
            replace_existing=True,
        )
        scheduler.add_job(
            delete_old_job_executions,
            trigger=CronTrigger(hour=3, minute=0),
            id='delete_old_job_executions',
            max_instances=1,
            replace_existing=True,
        )

        register_events(scheduler)

        self.stdout.write(self.style.SUCCESS(
            'Scheduler iniciado. Jobs: lembretes agendados (08:00), régua de cobrança (08:05), '
            'limpeza de histórico (03:00).'
        ))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write('Scheduler encerrado.')
