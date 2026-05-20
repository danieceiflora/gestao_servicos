import errno
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}

DEFAULT_IMAGE_MAX_DIMENSION = 1920
DEFAULT_IMAGE_QUALITY = 82
DEFAULT_VIDEO_MAX_WIDTH = 1280
DEFAULT_VIDEO_CRF = 28
DEFAULT_VIDEO_PRESET = 'medium'
DEFAULT_VIDEO_AUDIO_BITRATE = '128k'
DEFAULT_FFMPEG_NICE = 10
DEFAULT_FFMPEG_REALTIME = True
DEFAULT_MEDIA_LOCK_TIMEOUT = 0


@dataclass(frozen=True)
class ProcessedMedia:
    output_path: str
    output_name: str
    content_type: str
    kind: str
    input_size: int
    output_size: int


@dataclass(frozen=True)
class MediaFileInfo:
    name: str
    content_type: str
    size: int


class MediaProcessingBusyError(RuntimeError):
    pass


class MediaProcessingLock:
    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = max(0, int(timeout_seconds))
        self._file_handle = None

    def __enter__(self):
        lock_path = getattr(settings, 'MEDIA_PROCESSING_LOCK_PATH', None)
        if not lock_path:
            lock_path = os.path.join(tempfile.gettempdir(), 'media_processing.lock')

        lock_dir = os.path.dirname(lock_path)
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)
        self._file_handle = open(lock_path, 'a+')

        start = time.time()
        while True:
            try:
                self._acquire_lock(self._file_handle)
                return self
            except BlockingIOError:
                if self._timeout_seconds == 0 or (time.time() - start) >= self._timeout_seconds:
                    self._file_handle.close()
                    self._file_handle = None
                    raise MediaProcessingBusyError(
                        'Servidor ocupado processando outra mídia. Tente novamente em instantes.'
                    )
                time.sleep(0.2)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN):
                    if self._timeout_seconds == 0 or (time.time() - start) >= self._timeout_seconds:
                        self._file_handle.close()
                        self._file_handle = None
                        raise MediaProcessingBusyError(
                            'Servidor ocupado processando outra mídia. Tente novamente em instantes.'
                        )
                    time.sleep(0.2)
                else:
                    self._file_handle.close()
                    self._file_handle = None
                    raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file_handle:
            self._release_lock(self._file_handle)
            self._file_handle.close()
            self._file_handle = None
        return False

    @staticmethod
    def _acquire_lock(file_handle):
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _release_lock(file_handle):
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def media_processing_lock() -> MediaProcessingLock:
    timeout = int(getattr(settings, 'MEDIA_PROCESSING_LOCK_TIMEOUT', DEFAULT_MEDIA_LOCK_TIMEOUT))
    return MediaProcessingLock(timeout)


def process_uploaded_media(uploaded_file) -> ProcessedMedia:
    input_path = _write_upload_to_temp(uploaded_file)
    file_info = _build_file_info(
        name=getattr(uploaded_file, 'name', ''),
        content_type=getattr(uploaded_file, 'content_type', ''),
        size=getattr(uploaded_file, 'size', 0),
    )
    try:
        return process_media_path(input_path, file_info)
    finally:
        _safe_unlink(input_path)


def cleanup_processed_media(processed: ProcessedMedia) -> None:
    _safe_unlink(processed.output_path)


def save_upload_for_processing(uploaded_file) -> tuple[str, MediaFileInfo]:
    processing_root = getattr(settings, 'MEDIA_PROCESSING_ROOT', None)
    if not processing_root:
        processing_root = os.path.join(str(getattr(settings, 'MEDIA_ROOT', tempfile.gettempdir())), 'processing')
    os.makedirs(processing_root, exist_ok=True)

    suffix = Path(uploaded_file.name or '').suffix
    filename = f'raw_{uuid.uuid4().hex}{suffix}'
    input_path = os.path.join(processing_root, filename)
    with open(input_path, 'wb') as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)

    file_info = _build_file_info(
        name=getattr(uploaded_file, 'name', ''),
        content_type=getattr(uploaded_file, 'content_type', ''),
        size=getattr(uploaded_file, 'size', 0),
    )
    return input_path, file_info


def process_media_path(input_path: str, file_info: MediaFileInfo | None = None) -> ProcessedMedia:
    info = file_info or _build_file_info(name=os.path.basename(input_path), content_type='', size=0)
    kind = _detect_media_kind(info, input_path)
    if kind == 'image':
        output_path, content_type = _process_image(input_path)
    elif kind == 'video':
        output_path, content_type = _process_video(input_path)
    else:
        raise ValueError('Tipo de arquivo não suportado para processamento.')

    output_name = _build_output_name(kind)
    input_size = info.size or (os.path.getsize(input_path) if os.path.exists(input_path) else 0)
    output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    logger.info(
        "Processamento de mídia concluído (tipo=%s, tamanho_original=%s, tamanho_final=%s)",
        kind,
        input_size,
        output_size,
    )

    return ProcessedMedia(
        output_path=output_path,
        output_name=output_name,
        content_type=content_type,
        kind=kind,
        input_size=input_size,
        output_size=output_size,
    )


def _write_upload_to_temp(uploaded_file) -> str:
    suffix = Path(uploaded_file.name or '').suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        return tmp.name


def _detect_media_kind(file_info: MediaFileInfo, input_path: str) -> str:
    content_type = (file_info.content_type or '').lower()
    if content_type.startswith('image/'):
        return 'image'
    if content_type.startswith('video/'):
        return 'video'

    extension = Path(file_info.name or '').suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return 'image'
    if extension in VIDEO_EXTENSIONS:
        return 'video'

    if _looks_like_image(input_path):
        return 'image'
    if _looks_like_video(input_path):
        return 'video'

    raise ValueError('Tipo de arquivo não suportado. Envie imagem ou vídeo.')


def _build_file_info(name: str, content_type: str, size: int) -> MediaFileInfo:
    return MediaFileInfo(name=name or '', content_type=content_type or '', size=int(size or 0))


def _looks_like_image(input_path: str) -> bool:
    try:
        with Image.open(input_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _looks_like_video(input_path: str) -> bool:
    if shutil.which('ffprobe') is None:
        return False
    result = subprocess.run(
        [
            'ffprobe',
            '-v',
            'error',
            '-select_streams',
            'v:0',
            '-show_entries',
            'stream=codec_type',
            '-of',
            'default=noprint_wrappers=1:nokey=1',
            input_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and 'video' in (result.stdout or '').lower()


def _process_image(input_path: str) -> tuple[str, str]:
    max_dimension = int(getattr(settings, 'MEDIA_IMAGE_MAX_DIMENSION', DEFAULT_IMAGE_MAX_DIMENSION))
    quality = int(getattr(settings, 'MEDIA_IMAGE_QUALITY', DEFAULT_IMAGE_QUALITY))

    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGBA')
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert('RGB')

        img.thumbnail((max_dimension, max_dimension))

        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            output_path = tmp.name

        try:
            img.save(
                output_path,
                format='JPEG',
                quality=quality,
                optimize=True,
                progressive=True,
            )
        except Exception:
            _safe_unlink(output_path)
            raise

        return output_path, 'image/jpeg'


def _process_video(input_path: str) -> tuple[str, str]:
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('ffmpeg não está instalado no servidor.')

    max_width = int(getattr(settings, 'MEDIA_VIDEO_MAX_WIDTH', DEFAULT_VIDEO_MAX_WIDTH))
    crf = int(getattr(settings, 'MEDIA_VIDEO_CRF', DEFAULT_VIDEO_CRF))
    preset = getattr(settings, 'MEDIA_VIDEO_PRESET', DEFAULT_VIDEO_PRESET)
    audio_bitrate = getattr(settings, 'MEDIA_VIDEO_AUDIO_BITRATE', DEFAULT_VIDEO_AUDIO_BITRATE)
    threads = int(getattr(settings, 'MEDIA_FFMPEG_THREADS', 1))
    nice_level = int(getattr(settings, 'MEDIA_FFMPEG_NICE', DEFAULT_FFMPEG_NICE))
    realtime = bool(getattr(settings, 'MEDIA_FFMPEG_REALTIME', DEFAULT_FFMPEG_REALTIME))

    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
        output_path = tmp.name

    command = ['ffmpeg', '-y']
    if realtime:
        command.append('-re')
    command.extend([
        '-i',
        input_path,
        '-threads',
        str(max(1, threads)),
        '-vf',
        f"scale='min({max_width},iw)':-2",
        '-c:v',
        'libx264',
        '-preset',
        str(preset),
        '-crf',
        str(crf),
        '-pix_fmt',
        'yuv420p',
        '-c:a',
        'aac',
        '-b:a',
        str(audio_bitrate),
        '-movflags',
        '+faststart',
        output_path,
    ])

    preexec_fn = None
    if nice_level > 0 and hasattr(os, 'nice'):
        def _set_nice():
            os.nice(nice_level)
        preexec_fn = _set_nice

    result = subprocess.run(command, capture_output=True, text=True, check=False, preexec_fn=preexec_fn)
    if result.returncode != 0:
        _safe_unlink(output_path)
        error_message = (result.stderr or '').strip() or 'Falha ao processar o vídeo.'
        raise RuntimeError(error_message)

    return output_path, 'video/mp4'


def _build_output_name(kind: str) -> str:
    suffix = '.jpg' if kind == 'image' else '.mp4'
    return f'processed_{uuid.uuid4().hex}{suffix}'


def _safe_unlink(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("Falha ao remover arquivo temporário: %s", path)
