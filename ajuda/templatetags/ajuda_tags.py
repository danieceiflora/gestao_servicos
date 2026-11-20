from django import template
from django.urls import reverse
from urllib.parse import urlencode

from ajuda.access import visible_articles

register = template.Library()


@register.inclusion_tag('ajuda/partials/context_trigger.html', takes_context=True)
def contextual_help(context):
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return {}
    match = getattr(request, 'resolver_match', None)
    if not match or match.namespace == 'ajuda':
        return {}
    if not visible_articles(request.user).filter(context_links__view_name=match.view_name).exists():
        return {}
    return {
        'help_context_url': reverse('ajuda:contextual') + '?' + urlencode({'screen': match.view_name}),
    }
