import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integracoes.models import ScheduledReminder, ScheduledReminderLog
from integracoes.chatwoot_client import ChatwootClient
from integracoes.utils import resolve_field_path, get_client_phone
from services.models import Installment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envia lembretes agendados (disparo único por parcela). Rodar diariamente via cron.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Simula o envio sem despachar mensagens ou gravar logs.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.localdate()

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nenhuma mensagem será enviada.'))

        reminders = ScheduledReminder.objects.filter(is_active=True).prefetch_related('variables')
        self.stdout.write(f'[Lembretes] {today} — {reminders.count()} lembrete(s) ativo(s).')

        cw_client = ChatwootClient()
        sent = failed = skipped = 0

        for reminder in reminders:
            # offset_days = -1 → parcelas que vencem amanhã (today+1)
            # offset_days =  0 → parcelas que vencem hoje
            # offset_days =  3 → parcelas com 3 dias de atraso
            target_due_date = today - timedelta(days=reminder.offset_days)

            installments = (
                Installment.objects
                .filter(
                    due_date=target_due_date,
                    status__in=['PENDENTE', 'PARCIAL', 'ATRASADO'],
                )
                .select_related('billing__client')
                .prefetch_related('billing__client__phones', 'gateway_charges')
            )

            for installment in installments:
                # Pula se já enviado com sucesso (falhas podem ser retentadas)
                already_sent = ScheduledReminderLog.objects.filter(
                    reminder=reminder,
                    installment=installment,
                    status=ScheduledReminderLog.Status.SENT,
                ).exists()
                if already_sent:
                    skipped += 1
                    continue

                phone = self._resolve_phone(installment)
                if not phone:
                    logger.warning('Lembrete "%s": parcela #%s sem telefone — ignorada.', reminder.name, installment.pk)
                    skipped += 1
                    continue

                variables = self._resolve_variables(reminder, installment)
                contact_name = self._resolve_contact_name(installment)

                if dry_run:
                    self.stdout.write(
                        f'  [DRY-RUN] "{reminder.name}" ({reminder.offset_label}) → '
                        f'parcela #{installment.pk} (vence {installment.due_date}) → {phone} vars={variables}'
                    )
                    sent += 1
                    continue

                try:
                    cw_contact = cw_client.create_contact(contact_name, phone)
                    if not cw_contact:
                        raise ValueError('Contato não criado no Chatwoot')

                    conv = cw_client.get_or_create_conversation(cw_contact['id'])
                    if not conv:
                        raise ValueError('Conversa não criada no Chatwoot')

                    button_data = self._resolve_button_data(reminder, installment)
                    cw_client.send_template(
                        conversation_id=conv['id'],
                        template_name=reminder.template_name,
                        variables=variables,
                        button_data=button_data,
                    )

                    ScheduledReminderLog.objects.create(
                        reminder=reminder,
                        installment=installment,
                        phone=phone,
                        status=ScheduledReminderLog.Status.SENT,
                    )

                    logger.info('Lembrete "%s" enviado para %s (parcela #%s)',
                                reminder.name, phone, installment.pk)
                    sent += 1

                except Exception as exc:
                    logger.error('Erro no lembrete "%s" parcela #%s: %s',
                                 reminder.name, installment.pk, exc)
                    ScheduledReminderLog.objects.create(
                        reminder=reminder,
                        installment=installment,
                        phone=phone or '',
                        status=ScheduledReminderLog.Status.FAILED,
                        notes=str(exc),
                    )
                    failed += 1

        self.stdout.write(
            self.style.SUCCESS(f'Concluído. Enviados: {sent} | Ignorados: {skipped} | Falhas: {failed}')
        )

    def _resolve_phone(self, installment):
        client = getattr(getattr(installment, 'billing', None), 'client', None)
        return get_client_phone(client)

    def _resolve_contact_name(self, installment):
        client = getattr(getattr(installment, 'billing', None), 'client', None)
        if client:
            return getattr(client, 'name', None) or getattr(client, 'display_name', None) or 'Cliente'
        return 'Cliente'

    def _resolve_variables(self, reminder, installment):
        variables = []
        for var in reminder.variables.filter(component='BODY').order_by('index'):
            val = resolve_field_path(installment, var.field_path)
            if hasattr(val, 'strftime'):
                val = val.strftime('%d/%m/%Y')
            variables.append(str(val) if val is not None else '')
        return variables

    def _resolve_button_data(self, reminder, installment):
        btn_vars = reminder.variables.filter(component='BUTTON').order_by('index')
        if not btn_vars.exists():
            return None
        params = {}
        for var in btn_vars:
            val = resolve_field_path(installment, var.field_path)
            params[str(var.index)] = str(val) if val is not None else ''
        return {'type': 'url_suffix', 'params': params}
