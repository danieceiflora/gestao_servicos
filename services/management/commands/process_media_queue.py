import os
import time

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from services.models import ChecklistResponseMedia, MediaProcessingJob, ServiceMedia
from services.utils_media import MediaFileInfo, cleanup_processed_media, process_media_path


class Command(BaseCommand):
    help = "Processa a fila de conversão de mídias (uma por vez)."

    def add_arguments(self, parser):
        parser.add_argument('--sleep', type=int, default=3, help='Intervalo em segundos quando não há jobs.')
        parser.add_argument('--once', action='store_true', help='Processa apenas um job e encerra.')

    def handle(self, *args, **options):
        sleep_seconds = max(1, int(options['sleep']))
        run_once = options['once']

        while True:
            job = self._next_job()
            if not job:
                if run_once:
                    break
                time.sleep(sleep_seconds)
                continue

            self._process_job(job)

            if run_once:
                break

    def _next_job(self):
        with transaction.atomic():
            job = (
                MediaProcessingJob.objects
                .select_for_update(skip_locked=True)
                .filter(status=MediaProcessingJob.Status.PENDENTE)
                .order_by('created_at')
                .first()
            )
            if not job:
                return None
            job.status = MediaProcessingJob.Status.PROCESSANDO
            job.save(update_fields=['status', 'updated_at'])
            return job

    def _process_job(self, job: MediaProcessingJob):
        try:
            if not job.raw_path or not os.path.exists(job.raw_path):
                raise RuntimeError('Arquivo bruto não encontrado para processamento.')

            file_info = MediaFileInfo(
                name=job.original_name or os.path.basename(job.raw_path),
                content_type=job.content_type or '',
                size=os.path.getsize(job.raw_path) if job.raw_path else 0,
            )
            processed = process_media_path(job.raw_path, file_info=file_info)
            try:
                with open(processed.output_path, 'rb') as processed_handle:
                    processed_file = File(processed_handle, name=processed.output_name)

                    if job.response_id:
                        media = ChecklistResponseMedia.objects.create(
                            response=job.response,
                            file=processed_file
                        )
                        job.result_media_type = 'checklist'
                    else:
                        media = ServiceMedia.objects.create(
                            task=job.task,
                            occurrence=job.occurrence,
                            file=processed_file
                        )
                        job.result_media_type = 'task'

                job.result_media_id = media.id
                job.status = MediaProcessingJob.Status.CONCLUIDO
                job.processed_at = timezone.now()
                job.error_message = ''
                job.save(update_fields=[
                    'status',
                    'processed_at',
                    'error_message',
                    'result_media_type',
                    'result_media_id',
                    'updated_at',
                ])
            finally:
                cleanup_processed_media(processed)
                try:
                    os.remove(job.raw_path)
                except OSError:
                    pass
        except Exception as exc:
            job.status = MediaProcessingJob.Status.ERRO
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message', 'updated_at'])
