import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.tz_utils import local_today
from integracoes.models import (
    CollectionSequence, CollectionStep,
    CollectionInstallmentState, CollectionLog,
)
from integracoes.chatwoot_client import ChatwootClient
from integracoes.utils import resolve_field_path, get_client_phone
from services.models import Installment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envia lembretes de cobrança conforme as réguas configuradas. Rodar diariamente via cron.'

    def add_arguments(self, parser):
        parser.add_argument('--test-phone', type=str, default='',
                            help='Se informado, envia as mensagens para este número ao invés do '
                                 'telefone real do cliente, e NÃO grava nada no banco (nem '
                                 'CollectionLog, nem avanço de estado da régua) — evita que o '
                                 'disparo real seja pulado depois por já ter "avançado" no teste.')

    def handle(self, *args, **options):
        test_phone = (options.get('test_phone') or '').strip()
        today = local_today()

        if test_phone:
            self.stdout.write(self.style.WARNING(
                f'[TESTE] Mensagens serão enviadas para {test_phone} ao invés do telefone real '
                f'do cliente. Nenhuma alteração será gravada no banco (sem logs, sem avanço de régua).'
            ))

        sequences = CollectionSequence.objects.filter(is_active=True).prefetch_related('steps__variables')
        self.stdout.write(f'[Régua de Cobrança] {today} — {sequences.count()} régua(s) ativa(s).')

        cw_client = ChatwootClient()
        sent = failed = skipped = 0

        for sequence in sequences:
            max_due_date = today - timedelta(days=sequence.start_after_days_overdue)
            min_due_date = today - timedelta(days=sequence.stop_after_days_overdue)

            installments = (
                Installment.objects
                .filter(
                    due_date__lte=max_due_date,
                    due_date__gte=min_due_date,
                    status__in=['PENDENTE', 'PARCIAL', 'ATRASADO'],
                )
                .select_related('billing__client')
                .prefetch_related('billing__client__phones', 'gateway_charges')
            )
            if sequence.date_range_start:
                installments = installments.filter(due_date__gte=sequence.date_range_start)
            if sequence.date_range_end:
                installments = installments.filter(due_date__lte=sequence.date_range_end)

            for installment in installments:
                state, _ = CollectionInstallmentState.objects.get_or_create(
                    installment=installment,
                    defaults={'sequence': sequence, 'current_occurrence': 0},
                )

                if state.sequence_id != sequence.id:
                    skipped += 1
                    continue

                if state.is_paused:
                    skipped += 1
                    continue

                if state.current_occurrence >= sequence.max_occurrences:
                    skipped += 1
                    continue

                if state.next_eligible_date and today < state.next_eligible_date:
                    skipped += 1
                    continue

                step = sequence.steps.filter(
                    occurrence__gt=state.current_occurrence
                ).order_by('occurrence').first()
                if step is None:
                    skipped += 1
                    continue

                real_phone = self._resolve_phone(installment)
                phone = test_phone or real_phone
                if not phone:
                    logger.warning('Régua "%s": parcela #%s sem telefone — ignorada.', sequence.name, installment.pk)
                    skipped += 1
                    continue

                variables = self._resolve_variables(step, installment)
                contact_name = self._resolve_contact_name(installment)
                effective_interval = max(sequence.min_interval_days, step.wait_days_before_next)

                try:
                    cw_contact = cw_client.create_contact(contact_name, phone)
                    if not cw_contact:
                        raise ValueError('Contato não criado no Chatwoot')

                    conv = cw_client.get_or_create_conversation(cw_contact['id'])
                    if not conv:
                        raise ValueError('Conversa não criada no Chatwoot')

                    button_data = self._resolve_button_data(step, installment)
                    cw_client.send_template(
                        conversation_id=conv['id'],
                        template_name=step.template_name,
                        variables=variables,
                        button_data=button_data,
                    )

                    if test_phone:
                        # Envio de teste: não grava log nem avança o estado da régua, para não
                        # "queimar" a ocorrência e pular o disparo real depois.
                        logger.info('Régua "%s" #%s enviada em modo TESTE para %s (parcela #%s) — sem gravação no banco',
                                    sequence.name, step.occurrence, phone, installment.pk)
                    else:
                        CollectionLog.objects.create(
                            installment=installment,
                            step=step,
                            occurrence_number=step.occurrence,
                            phone=phone,
                            status=CollectionLog.Status.SENT,
                        )

                        state.current_occurrence = step.occurrence
                        state.last_sent_at = today
                        state.next_eligible_date = today + timedelta(days=effective_interval)
                        state.save(update_fields=['current_occurrence', 'last_sent_at', 'next_eligible_date'])

                        logger.info('Régua "%s" #%s enviada para %s (parcela #%s)',
                                    sequence.name, step.occurrence, phone, installment.pk)
                    sent += 1

                except Exception as exc:
                    logger.error('Erro na régua "%s" #%s parcela #%s: %s',
                                 sequence.name, step.occurrence, installment.pk, exc)
                    if not test_phone:
                        CollectionLog.objects.create(
                            installment=installment,
                            step=step,
                            occurrence_number=step.occurrence,
                            phone=phone or '',
                            status=CollectionLog.Status.FAILED,
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

    def _resolve_variables(self, step, installment):
        variables = []
        for var in step.variables.filter(component='BODY').order_by('index'):
            val = resolve_field_path(installment, var.field_path)
            if hasattr(val, 'strftime'):
                val = val.strftime('%d/%m/%Y')
            variables.append(str(val) if val is not None else '')
        return variables

    def _resolve_button_data(self, step, installment):
        btn_vars = step.variables.filter(component='BUTTON').order_by('index')
        if not btn_vars.exists():
            return None
        params = {}
        for var in btn_vars:
            val = resolve_field_path(installment, var.field_path)
            params[str(var.index)] = str(val) if val is not None else ''
        return {'type': 'url_suffix', 'params': params}
