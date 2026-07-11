from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.audit.services import log_access
from apps.materials.models import Material, MaterialPrice
from apps.quotations.models import ItemMaterial

_READ_ROLES = (
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)
_WRITE_ROLES = (
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


def _latest_quotation_usage(material_sigla, forma):
    item_material = (
        ItemMaterial.objects.select_related("item__quotation")
        .filter(material=material_sigla, forma=forma)
        .order_by("-item__quotation__created_at", "-pk")
        .first()
    )
    if item_material is None:
        return None
    return {
        "number": item_material.item.quotation.number,
        "preco_kgf": str(item_material.preco_kgf),
    }


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


def _material_detail_context(material):
    today = timezone.localdate()
    prices = _current_prices(material.precos.all(), today)
    return {
        "material": material,
        "prices": [
            {
                "forma": forma,
                "label": _FORMA_LABELS[forma],
                "preco": prices[forma].preco_brl_kg,
                "fornecedor": prices[forma].fornecedor or "—",
                "valid_from": prices[forma].valid_from,
                "valid_until": prices[forma].valid_until,
                "last_quote": _latest_quotation_usage(material.sigla, forma),
            }
            for forma, _ in MaterialPrice.FORMA
            if forma in prices
        ],
        "all_formas": [
            {
                "forma": forma,
                "label": label,
                "current": prices.get(forma),
                "last_quote": _latest_quotation_usage(material.sigla, forma),
            }
            for forma, label in MaterialPrice.FORMA
        ],
    }


@require_role(*_READ_ROLES)
def list_materials(request):
    context = _materials_context(request)
    template = "materials/_results.html" if request.headers.get("HX-Request") == "true" else "materials/list.html"
    return render(request, template, context)


@require_role(*_READ_ROLES)
def detail_material(request, pk):
    price_qs = MaterialPrice.objects.order_by("forma", "-valid_from", "-created_at")
    material = get_object_or_404(Material.objects.prefetch_related(Prefetch("precos", queryset=price_qs)), pk=pk)
    context = _material_detail_context(material)
    context["can_edit_prices"] = user_role(request.user) in _WRITE_ROLES
    template = "materials/_detail.html" if request.headers.get("HX-Request") == "true" else "materials/detail.html"
    return render(request, template, context)


def _parse_price(raw_value):
    normalized = (raw_value or "").strip().replace(",", ".")
    if not normalized:
        raise ValueError("Preço é obrigatório.")
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Preço inválido.") from exc
    if value <= 0:
        raise ValueError("Preço deve ser maior que zero.")
    return value


def _current_price_for_forma(material, forma, today):
    prices = _current_prices(material.precos.all(), today)
    return prices.get(forma)


@require_role(*_WRITE_ROLES)
@require_POST
@transaction.atomic
def save_material_price(request, pk, forma):
    if forma not in _FORMA_LABELS:
        raise Http404()

    price_qs = MaterialPrice.objects.select_for_update().order_by("forma", "-valid_from", "-created_at")
    material = get_object_or_404(Material.objects.prefetch_related(Prefetch("precos", queryset=price_qs)), pk=pk)
    today = timezone.localdate()
    current_price = _current_price_for_forma(material, forma, today)
    previous_value = str(current_price.preco_brl_kg) if current_price is not None else None

    new_value = _parse_price(request.POST.get("preco_brl_kg"))
    fornecedor = (request.POST.get("fornecedor") or "").strip()

    if current_price is not None:
        current_price.valid_until = today - timedelta(days=1)
        current_price.save(update_fields=["valid_until"])

    new_price = MaterialPrice.objects.create(
        material=material,
        forma=forma,
        preco_brl_kg=str(new_value),
        fornecedor=fornecedor,
        valid_from=today,
        valid_until=None,
    )
    log_access(
        request,
        "price_change",
        new_price,
        {
            "forma": forma,
            "anterior": previous_value,
            "novo": str(new_value),
        },
    )

    refreshed = Material.objects.prefetch_related(
        Prefetch("precos", queryset=MaterialPrice.objects.order_by("forma", "-valid_from", "-created_at"))
    ).get(pk=material.pk)
    context = _material_detail_context(refreshed)
    context["can_edit_prices"] = True
    return render(request, "materials/_detail.html", context)
