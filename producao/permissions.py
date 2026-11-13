"""Guardas de acesso do módulo de Expedição / Produção.

O público do painel é o separador/produtor, que neste projeto é
`User.Roles.COLLABORATOR` — para quem `user.is_manager` é False. Por isso o
padrão dominante `@user_passes_test(is_manager)` não serve aqui, e o módulo usa
permissões dedicadas, como o frente de caixa já faz (`services/views_pos.py`).

Conceda `producao.operate_production` ao pessoal de oficina pelo /admin.
Outros departamentos acompanham o painel com `producao.view_productionorder`.
"""


def can_view(user):
    return user.is_authenticated and (
        user.is_manager or user.has_perm('producao.view_productionorder')
        or user.has_perm('producao.operate_production')
    )


def can_operate(user):
    return user.is_authenticated and (
        user.is_manager or user.has_perm('producao.operate_production')
    )


def can_manage(user):
    return user.is_authenticated and (
        user.is_manager or user.has_perm('producao.manage_production')
    )
