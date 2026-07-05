"""Formatação de moeda/número no padrão pt-BR (separador de milhar '.', decimal ',').

Determinístico e independente de USE_THOUSAND_SEPARATOR / locale ativo — o
`numberformat` do Django só agrupa quando USE_THOUSAND_SEPARATOR=True, e encadear
`floatformat|intcomma` quebra sob pt-BR (produz "435,060,55"). Este filtro formata
com f-string e troca os separadores, então "R$ {{ v|brl }}" sempre rende
"435.060,55" e "{{ v|brl:0 }}" rende "435.061".
"""
from django import template

register = template.Library()


@register.filter
def brl(value, decimals=2):
    """Formata um número no padrão pt-BR. `decimals` casas (default 2)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2
    # US -> pt-BR: "435,060.55" vira "435.060,55"
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
