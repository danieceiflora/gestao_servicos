import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.tz_utils import local_today
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
        today = local_today()

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nenhuma mensagem será enviada.'))

        reminders = ScheduledReminder.objects.filter(is_active=True).prefetch_related('variables')
        self.stdout.write(f'[Lembretes] {today} — {reminders.count()} lembrete(s) ativo(s).')

        cw_client = ChatwootClient()
        sent = failed = skipped = 0

        for reminder in reminders:
            # offset_days é sempre relativo ao campo em reminder.anchor_field
            # (due_date ou discount_deadline). Ex: anchor=discount_deadline,
            # offset_days=-1 → parcelas cujo limite de desconto é amanhã.
            target_date = today - timedelta(days=reminder.offset_days)

            installments = (
                Installment.objects
                .filter(
                    status__in=['PENDENTE', 'PARCIAL', 'ATRASADO'],
                    **{reminder.anchor_field: target_date},
                )
                .select_related('billing__client')
                .prefetch_related('billing__client__phones', 'gateway_charges')
            )

            # Restringe pelo canal de pagamento — evita disparar um template que
            # referencia dado de gateway (ex: código Pix) para quem paga por outro meio.
            active_charge_status = ['PENDING', 'OVERDUE']
            if reminder.payment_channel == ScheduledReminder.PaymentChannel.PIX:
                installments = installments.filter(
                    gateway_charges__status__in=active_charge_status,
                    gateway_charges__method='PIX',
                ).distinct()
            elif reminder.payment_channel == ScheduledReminder.PaymentChannel.BOLETO:
                installments = installments.filter(
                    gateway_charges__status__in=active_charge_status,
                    gateway_charges__method='BOLETO',
                ).distinct()
            elif reminder.payment_channel == ScheduledReminder.PaymentChannel.SEM_GATEWAY:
                installments = installments.exclude(
                    gateway_charges__status__in=active_charge_status,
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
                        f'  [DRY-RUN] "{reminder.name}" ({reminder.offset_label}, canal={reminder.get_payment_channel_display()}) → '
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
