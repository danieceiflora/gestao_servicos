from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .access import allowed_modules, can_manage_help, visible_articles
from .models import ArticleStep, Category
from .search import search_articles
from .video import video_embed_url


def _base_context(request):
    return {
        'help_layout': 'base.html' if request.user.is_manager else 'base_equipe.html',
        'can_manage_help': can_manage_help(request.user),
    }


def _filters(request, articles):
    query = request.GET.get('q', '').strip()[:200]
    videos_only = request.GET.get('video') == '1'
    illustrated_only = request.GET.get('illustrated') == '1'
    if videos_only:
        articles = articles.exclude(video_url='')
    if illustrated_only:
        articles = articles.filter(Q(steps__screenshot__gt='') | Q(steps__image__gt='')).distinct()
    return search_articles(articles, query), query, videos_only, illustrated_only


@never_cache
@login_required
@require_safe
def index(request):
    visible = visible_articles(request.user).prefetch_related('steps')
    categories = Category.objects.filter(articles__in=visible).annotate(
        article_count=Count('articles', filter=Q(articles__in=visible), distinct=True),
    ).order_by('sort_order', 'name').distinct()
    selected_category = request.GET.get('category', '')[:140]
    articles = visible
    if selected_category:
        articles = articles.filter(category__slug=selected_category)
    articles, query, videos_only, illustrated_only = _filters(request, articles)
    page = Paginator(articles, 12).get_page(request.GET.get('page'))
    context = _base_context(request)
    context.update({
        'categories': categories, 'articles': page, 'page_obj': page,
        'query': query, 'q': query, 'videos_only': videos_only, 'illustrated_only': illustrated_only, 'selected_category': selected_category,
        'featured_articles': visible.filter(featured=True).annotate(
            _illustrated=Exists(ArticleStep.objects.filter(article_id=OuterRef('pk')).filter(Q(screenshot__gt='') | Q(image__gt=''))),
        ).order_by('-_illustrated', 'sort_order', 'title')[:6] if not query and not selected_category and not videos_only and not illustrated_only else [],
    })
    return render(request, 'ajuda/index.html', context)


@never_cache
@login_required
@require_safe
def category(request, slug):
    selected = get_object_or_404(Category.objects.filter(module__in=allowed_modules(request.user)), slug=slug)
    articles, query, videos_only, illustrated_only = _filters(request, visible_articles(request.user).filter(category=selected).prefetch_related('steps'))
    page = Paginator(articles, 12).get_page(request.GET.get('page'))
    context = _base_context(request)
    context.update({'category': selected, 'articles': page, 'page_obj': page, 'query': query, 'q': query, 'videos_only': videos_only, 'illustrated_only': illustrated_only})
    return render(request, 'ajuda/category.html', context)


@never_cache
@login_required
@require_safe
def article(request, slug):
    visible = visible_articles(request.user).prefetch_related('steps')
    selected = get_object_or_404(visible.prefetch_related('steps'), slug=slug)
    context = _base_context(request)
    context.update({
        'article': selected, 'steps': selected.steps.all(),
        'related_articles': visible.filter(category=selected.category).exclude(pk=selected.pk)[:4],
        'video_embed_url': video_embed_url(selected.video_url),
    })
    return render(request, 'ajuda/article.html', context)


@never_cache
@login_required
@require_safe
def contextual(request):
    """Consulta online: nenhum título editorial fica no shell offline."""
    screen = request.GET.get('screen', '')[:150]
    articles = list(visible_articles(request.user).filter(context_links__view_name=screen).distinct()[:5])
    context = _base_context(request)
    context.update({
        'help_articles': articles,
        'help_screen': screen,
        'help_category': articles[0].category if articles else None,
        'help_is_technician': screen.startswith('equipe_'),
    })
    return render(request, 'ajuda/partials/context_panel.html', context)
