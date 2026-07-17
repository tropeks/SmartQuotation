"""
Template tags do RBAC configurável.

`user_can` expõe o MESMO enforcement (`enforcement.user_can`) para os templates —
mesma fonte da verdade das views, então flags de UI não divergem do gate real.
"""
from django import template

from apps.access.enforcement import user_can as _user_can

register = template.Library()


@register.simple_tag
def user_can(user, capability):
    """{% user_can request.user "access.manage" as flag %} -> bool (fail-closed)."""
    return _user_can(user, capability)
