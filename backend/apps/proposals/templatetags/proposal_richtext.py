from django import template
from django.utils.safestring import mark_safe

from apps.proposals.richtext import normalize_rich_text

register = template.Library()


@register.filter(name="proposal_richtext")
def proposal_richtext(value):
    return mark_safe(normalize_rich_text(value))
