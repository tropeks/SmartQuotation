"""Template tags do inbox de aprovações (RBAC V2 M5)."""
from django import template

from apps.accounts.rbac import user_role
from apps.audit import approvals

register = template.Library()


@register.inclusion_tag("audit/_inbox_badge.html")
def inbox_badge(user):
    """Renderiza o badge do inbox (com poller) já com a contagem inicial do papel do user."""
    count = 0
    if getattr(user, "is_authenticated", False):
        count = approvals.inbox_count_for_role_cached(user_role(user))
    return {"count": count}
