"""Catálogo TEMA + seletor de composição (front+shell+rear) com checagem de compatibilidade."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.tema_templates.models import ComponentTemplate, check_compatibility
from apps.tema_templates.services import (
    estimate_complete, reference_inputs, _physical_params, _metalurgia,
    layout_avisos, espessura_avisos, flange_corpo_avisos, rt_exposicoes_info, COSTABLE)
from apps.tema_templates.forms import PermutadorDataSheetForm
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
def data_sheet(request):
    """Data sheet do permutador completo: dimensões reais → recálculo geométrico do custo.
    Prova a parametria (#1/#9): mudar comprimento/nº de tubos move o custo de material."""
    custo = ref = None
    avisos = []
    if request.method == "POST":
        form = PermutadorDataSheetForm(request.POST)
        if form.is_valid():
            desig = form.cleaned_data["designacao"]
            override, fc = form.to_dims_override()
            params = _physical_params(desig, form.cleaned_data)
            avisos = (espessura_avisos(form.cleaned_data)
                      + flange_corpo_avisos(desig, form.cleaned_data)
                      + layout_avisos(desig, form.cleaned_data)
                      + rt_exposicoes_info(form.cleaned_data))
            liga, dens, preco = _metalurgia(form.cleaned_data)
            custo = estimate_complete(desig, dims_override=override, fator_correcao_mo=fc,
                                      params=params, liga_por_lado=liga, dens_por_lado=dens,
                                      preco_por_lado=preco,
                                      corrosivo=form.cleaned_data.get("fluido_corrosivo", "Tubos"))
    else:
        desig = request.GET.get("designacao") or (sorted(COSTABLE)[0] if COSTABLE else "")
        ref = reference_inputs(desig)
        form = PermutadorDataSheetForm(initial=ref)
    return render(request, "tema_templates/data_sheet.html",
                  {"form": form, "custo": custo, "avisos": avisos, "costable": sorted(COSTABLE)})


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
