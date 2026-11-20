"""Um único filtro para listagem, busca, links diretos e ajuda contextual.

O papel de gerente do projeto é GERENTE (User.Roles.MANAGER), não MANAGER.
Permissão de editar documentação não concede acesso aos módulos de negócio.
"""
from django.db.models import Q

from .models import Article, Category


def allowed_modules(user):
    if not user.is_authenticated or not user.is_active:
        return set()
    modules = {Category.Module.GENERAL, Category.Module.TECHNICIAN}
    if user.is_manager:
        return set(Category.Module.values)
    if user.has_perm('services.view_client'):
        modules.add(Category.Module.CLIENTS)
    if user.has_perm('services.view_serviceorder'):
        modules.add(Category.Module.ORDERS)
    if user.has_perm('services.operate_pos'):
        modules.add(Category.Module.POS)
    if user.has_perm('producao.view_productionorder') or user.has_perm('producao.operate_production'):
        modules.add(Category.Module.PRODUCTION)
    return modules


def visible_articles(user):
    modules = allowed_modules(user)
    if not modules:
        return Article.objects.none()
    audience = Article.Audience.MANAGERS if user.is_manager else Article.Audience.COLLABORATORS
    return Article.objects.filter(
        Q(audience=Article.Audience.ALL) | Q(audience=audience),
        status=Article.Status.PUBLISHED,
        category__module__in=modules,
    ).select_related('category')


def can_manage_help(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and user.has_perm('ajuda.change_article'))
