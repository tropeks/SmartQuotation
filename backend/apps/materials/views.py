from django.db.models import Prefetch, Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role
from apps.materials.models import Material, MaterialPrice

_READ_ROLES = (
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)

_FORMA_LABELS = dict(MaterialPrice.FORMA)


def _current_prices(prices, today):
    current = {}
    for price in prices:
        if price.valid_from and price.valid_from > today:
            continue
        if price.valid_until and price.valid_until < today:
            continue

        existing = current.get(price.forma)
        if existing is None:
            current[price.forma] = price
            continue
        if price.valid_from > existing.valid_from:
            current[price.forma] = price
            continue
        if price.valid_from == existing.valid_from and price.created_at > existing.created_at:
            current[price.forma] = price
    return current


def _materials_context(request):
    search = (request.GET.get("q") or "").strip()
    today = timezone.localdate()
    price_qs = MaterialPrice.objects.order_by("forma", "-valid_from", "-created_at")
    qs = Material.objects.prefetch_related(Prefetch("precos", queryset=price_qs))

    if search:
        qs = qs.filter(Q(sigla__icontains=search) | Q(tipo__icontains=search))

    qs = qs.order_by("sigla")
    rows = []
    for material in qs:
        prices = _current_prices(material.precos.all(), today)
        rows.append(
            {
                "obj": material,
                "prices": [
                    {
                        "forma": forma,
                        "label": _FORMA_LABELS[forma],
                        "preco": prices[forma].preco_brl_kg,
                        "fornecedor": prices[forma].fornecedor or "—",
                        "valid_from": prices[forma].valid_from,
                        "valid_until": prices[forma].valid_until,
                    }
                    for forma, _ in MaterialPrice.FORMA
                    if forma in prices
                ],
            }
        )

    return {
        "materials": rows,
        "search": search,
    }


@require_role(*_READ_ROLES)
def list_materials(request):
    context = _materials_context(request)
    template = "materials/_results.html" if request.headers.get("HX-Request") == "true" else "materials/list.html"
    return render(request, template, context)
