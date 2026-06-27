"""
Views do data sheet do feixe — session auth + HTMX (recálculo ao vivo).
Vertical slice: criar feixe -> recompute (preview ao vivo) -> salvar -> detalhe (EAP + preço).
"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role
from apps.quotations.models import Quotation, Customer
from apps.quotations.forms import FeixeDataSheetForm
from apps.quotations.adapter import default_inputs, to_feixe_inputs
from apps.quotations.services import create_feixe_quotation

from pricing_engine.feixe_inputs import FeixeInputs
from pricing_engine.feixe_quote import quote_feixe


# Papéis com permissão de ESCRITA em cotações (criar/recomputar/precificar/revisar).
# Espelha o padrão require_role de apps/production e apps/engineering_params: os papéis
# que editam engineering_params/production (engenheiro, gestor_comercial, admin) escrevem,
# e o orçamentista é o autor das cotações (papel default). Ver/listar fica liberado a
# qualquer membro autenticado do tenant.
_WRITE_ROLES = (
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)


def _initial_from_defaults() -> dict:
    d = default_inputs()
    d["title"] = "Feixe Tubular"
    d["customer_name"] = ""
    return d


def _preview(inputs: dict):
    """Computa um preview (sem persistir) → contexto de resultados."""
    merged = {**default_inputs(), **inputs}
    valid = {k: v for k, v in merged.items() if k in {f.name for f in FeixeInputs.__dataclass_fields__.values()}}
    cot = quote_feixe(FeixeInputs(**valid))
    perda = sum(mp.perda_kg for it in cot.itens for mp in it.materias_primas)
    peso_bruto = sum(mp.peso_kg for it in cot.itens for mp in it.materias_primas)
    return {
        "cot": cot,
        "itens": [it for it in cot.itens if it.custo_total > 0],
        "peso_bruto": peso_bruto,
        "perda": perda,
        "perda_pct": (perda / peso_bruto * 100) if peso_bruto else 0,
    }


@login_required
def list_quotations(request):
    quotations = Quotation.objects.select_related("customer").all()
    return render(request, "quotations/list.html", {"quotations": quotations})


@require_role(*_WRITE_ROLES)
def feixe_data_sheet(request):
    """Tela do data sheet com form + painel de resultados (recálculo HTMX)."""
    form = FeixeDataSheetForm(initial=_initial_from_defaults())
    ctx = {"form": form, "results": _preview(default_inputs())}
    return render(request, "quotations/data_sheet.html", ctx)


@require_role(*_WRITE_ROLES)
def recompute_preview(request):
    """HTMX: recalcula ao vivo a partir dos campos atuais (sem persistir)."""
    form = FeixeDataSheetForm(request.POST)
    if form.is_valid():
        results = _preview(form.to_inputs_dict())
        return render(request, "quotations/_results.html", {"results": results})
    return render(request, "quotations/_results.html",
                  {"results": _preview(default_inputs()), "form_errors": form.errors})


@require_role(*_WRITE_ROLES)
def create_quotation(request):
    """Persiste a cotação (deep-copy/snapshot via adapter) e vai pro detalhe."""
    form = FeixeDataSheetForm(request.POST)
    if not form.is_valid():
        return render(request, "quotations/data_sheet.html",
                      {"form": form, "results": _preview(default_inputs())})
    customer, _ = Customer.objects.get_or_create(company_name=form.cleaned_data["customer_name"])
    q = create_feixe_quotation(customer, form.cleaned_data["title"],
                               created_by=request.user, inputs=form.to_inputs_dict())
    return redirect("quotations:detail", pk=q.pk)


@login_required
def quotation_detail(request, pk):
    q = get_object_or_404(Quotation.objects.select_related("customer"), pk=pk)
    itens = (q.itens.prefetch_related("materiais", "operacoes")).all()
    has_active_of = q.ordens_fabricacao.exclude(status="cancelada").exists()
    return render(request, "quotations/detail.html",
                  {"q": q, "itens": itens, "has_active_of": has_active_of})


@require_role(*_WRITE_ROLES)
@require_POST
def quotation_revise(request, pk):
    orig = get_object_or_404(Quotation, pk=pk)
    
    from apps.quotations.adapter import recompute
    from apps.quotations.services import create_permutador_quotation
    from pricing_engine.permutador_quote import quote_completo

    if orig.scope == "complete":
        desig = orig.inputs.get("designacao", "BEU")
        from apps.tema_templates.services import estimate_from_inputs
        # recomputa com as DIMENSÕES da cotação original (não o seed); fallback defensivo no seed
        resultado = estimate_from_inputs(desig, orig.inputs) or quote_completo(desig)
        q = create_permutador_quotation(
            customer=orig.customer,
            designacao=desig,
            cleaned=orig.inputs,
            resultado=resultado,
            created_by=request.user,
            title=orig.title,
            revision=orig.revision + 1
        )
        q.status = "draft"
        q.save()
    else:
        from apps.quotations.services import next_number
        q = Quotation.objects.create(
            number=next_number(),
            revision=orig.revision + 1,
            customer=orig.customer,
            title=orig.title,
            scope=orig.scope,
            status="draft",
            inputs=orig.inputs,
            fator_preco=orig.fator_preco,
            impostos_pct=orig.impostos_pct,
            created_by=request.user
        )
        recompute(q)
        from apps.quotations.services import create_calculation_snapshot
        create_calculation_snapshot(q)

    return redirect("quotations:detail", pk=q.pk)
