"""Converte links, nunca HTML arbitrário, para provedores de vídeo permitidos."""
import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError


def video_embed_url(value):
    if not value:
        return ''
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or url.username or url.password or url.port:
            return ''
        host = url.hostname
        video_id = ''
        if host == 'youtu.be':
            match = re.fullmatch(r'/([A-Za-z0-9_-]{11})/?', url.path)
            video_id = match[1] if match else ''
        elif host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'www.youtube-nocookie.com'}:
            if url.path == '/watch':
                values = parse_qs(url.query).get('v', [])
                video_id = values[0] if len(values) == 1 else ''
            else:
                match = re.fullmatch(r'/(?:embed|shorts)/([A-Za-z0-9_-]{11})/?', url.path)
                video_id = match[1] if match else ''
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return f'https://www.youtube-nocookie.com/embed/{video_id}'
        if host in {'vimeo.com', 'www.vimeo.com', 'player.vimeo.com'}:
            pattern = r'/video/([0-9]{1,12})/?' if host == 'player.vimeo.com' else r'/([0-9]{1,12})(?:/([A-Za-z0-9]{6,64}))?/?'
            match = re.fullmatch(pattern, url.path)
            if match:
                token = match[2] if host != 'player.vimeo.com' and match.lastindex == 2 else ''
                tokens = parse_qs(url.query).get('h', [])
                if tokens:
                    if len(tokens) != 1 or not re.fullmatch(r'[A-Za-z0-9]{6,64}', tokens[0]):
                        return ''
                    token = tokens[0]
                suffix = f'?h={token}' if token else ''
                return f'https://player.vimeo.com/video/{match[1]}{suffix}'
    except (ValueError, TypeError):
        pass
    return ''


def validate_video_url(value):
    if value and not video_embed_url(value):
        raise ValidationError('Informe um link HTTPS válido de vídeo do YouTube ou Vimeo, não um código de incorporação.')
