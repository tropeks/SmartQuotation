"""Catálogo TEMA + seletor de composição (front+shell+rear) com checagem de compatibilidade."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.tema_templates.models import ComponentTemplate, check_compatibility
from apps.tema_templates.services import estimate_complete, COSTABLE
from apps.engineering_params.models import TenantParamConfig


def _compat_mode():
    """block | warn | free — vem do TenantConfig (default warn)."""
    try:
        return getattr(TenantParamConfig.get_solo(), "tema_compat_mode", "warn")
    except Exception:
        return "warn"


@login_required
def catalog(request):
    grupos = {}
    for t in ComponentTemplate.objects.filter(is_active=True):
        grupos.setdefault(t.get_tema_part_display(), []).append(t)
    return render(request, "tema_templates/catalog.html", {"grupos": grupos.items()})


@login_required
def compose(request):
    fronts = ComponentTemplate.objects.filter(tema_part="front_head")
    shells = ComponentTemplate.objects.filter(tema_part="shell")
    rears = ComponentTemplate.objects.filter(tema_part="rear_head")
    return render(request, "tema_templates/compose.html",
                  {"fronts": fronts, "shells": shells, "rears": rears})


@login_required
def compose_check(request):
    """HTMX: valida a combinação TEMA escolhida e devolve designação + avisos."""
    front = request.POST.get("front", "")
    shell = request.POST.get("shell", "")
    rear = request.POST.get("rear", "")
    avisos = check_compatibility(front, shell, rear)
    mode = _compat_mode()
    designacao = f"{front}{shell}{rear}".upper() if (front and shell and rear) else None
    # blocos que compõem (feixe sempre presente; casco/cabeçotes conforme letras)
    blocos = ["Feixe Tubular"]
    if shell:
        blocos.append(f"Casco {shell.upper()}")
    if front:
        blocos.append(f"Cabeçote Frontal {front.upper()}")
    if rear and rear.upper() != "U":
        blocos.append(f"Cabeçote Traseiro {rear.upper()}")
    bloqueado = bool(avisos) and mode == "block"
    # custeio paramétrico do permutador completo (se a designação for custeável e não bloqueada)
    custo = None
    if designacao and not bloqueado:
        custo = estimate_complete(designacao)
    return render(request, "tema_templates/_compose_result.html", {
        "designacao": designacao, "avisos": avisos, "mode": mode, "blocos": blocos,
        "bloqueado": bloqueado, "custo": custo, "costable": sorted(COSTABLE),
    })
