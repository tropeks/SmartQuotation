"""Wizard de cadeia de custos: top-down (seed) + back-solve (calibração contra job real)."""
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from apps.cost_discovery.models import CostDiscoverySession
from apps.cost_discovery import services
from apps.engineering_params.models import TenantParamConfig
from apps.materials.models import MaterialPrice


@login_required
def wizard_home(request):
    cfg = TenantParamConfig.get_solo()
    ctx = {
        "fator_mo": cfg.fator_correcao_mo,
        "n_precos": MaterialPrice.objects.count(),
        "sessions": CostDiscoverySession.objects.all()[:10],
    }
    return render(request, "cost_discovery/home.html", ctx)


@login_required
def top_down(request):
    """Seed: o empresário entra preços de material e o fator de MO de cabeça."""
    if request.method == "POST":
        prices = []
        siglas = request.POST.getlist("sigla")
        formas = request.POST.getlist("forma")
        precos = request.POST.getlist("preco")
        for s, f, p in zip(siglas, formas, precos):
            if s and p:
                prices.append({"sigla": s, "forma": f, "preco": p})
        fator = request.POST.get("fator_mo") or None
        res = services.apply_top_down(prices, fator)
        CostDiscoverySession.objects.create(
            method="top_down", created_by=request.user,
            notes=f"{res['precos_gravados']} preços, fator MO {res['fator_mo']}")
        return redirect("cost_discovery:home")
    return render(request, "cost_discovery/top_down.html",
                  {"fator_mo": TenantParamConfig.get_solo().fator_correcao_mo})


@login_required
def back_solve(request):
    """Calibração: entra um job real (specs + preço conhecido) → fator de MO que o reproduz."""
    result = None
    if request.method == "POST":
        ref = {
            "n_tubos": int(request.POST.get("n_tubos") or 136),
            "tubo_material": request.POST.get("tubo_material") or "SA-179",
            "tubo_od_spec": request.POST.get("tubo_od_spec") or '3/4"',
            "tubo_wall_spec": request.POST.get("tubo_wall_spec") or "BWG 14",
            "tubo_comp_mm": float(request.POST.get("tubo_comp_mm") or 6096),
            "espelho_od_mm": float(request.POST.get("espelho_od_mm") or 475),
            "chicana_qty": int(request.POST.get("chicana_qty") or 18),
        }
        known = Decimal(request.POST.get("known_price") or "0")
        session = CostDiscoverySession.objects.create(
            method="back_solve", reference_inputs=ref, reference_known_price=known,
            created_by=request.user)
        services.run_back_solve(session)
        result = session
        if "apply" in request.POST:
            return redirect("cost_discovery:home")
    return render(request, "cost_discovery/back_solve.html", {"result": result})
