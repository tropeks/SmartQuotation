"""
Views do data sheet do feixe — session auth + HTMX (recálculo ao vivo).
Vertical slice: criar feixe -> recompute (preview ao vivo) -> salvar -> detalhe (EAP + preço).
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.quotations.models import Quotation, Customer
from apps.quotations.forms import FeixeDataSheetForm, QuotationEntryForm
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

_ENTRY_ROLES = (
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_ADMIN,
)

_STATUS_PILL_CLASSES = {
    "draft": "q-status--draft",
    "in_review": "q-status--review",
    "approved": "q-status--approved",
    "sent": "q-status--sent",
    "won": "q-status--won",
    "lost": "q-status--lost",
}


def _initial_from_defaults() -> dict:
    d = default_inputs()
    d["title"] = "Feixe Tubular"
    d["customer_name"] = ""
    return d


def _revision_label(revision: int) -> str:
    if 0 <= revision < 26:
        return f"Rev. {chr(ord('A') + revision)}"
    return f"Rev. {revision + 1}"


def _status_class(status: str) -> str:
    return _STATUS_PILL_CLASSES.get(status, "q-status--draft")


def _list_context(request):
    qs = Quotation.objects.select_related("customer", "created_by")

    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(number__icontains=search)
            | Q(title__icontains=search)
            | Q(customer__company_name__icontains=search)
        )

    statuses = [status for status in request.GET.getlist("status") if status]
    if statuses:
        qs = qs.filter(status__in=statuses)

    customer_id = request.GET.get("customer") or ""
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    qs = qs.order_by("-created_at")
    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)
    rows = []
    for quotation in page_obj.object_list:
        created_by = quotation.created_by
        created_by_display = "—"
        if created_by is not None:
            created_by_display = created_by.get_full_name() or created_by.username
        rows.append({
            "obj": quotation,
            "revision_label": _revision_label(quotation.revision),
            "status_class": _status_class(quotation.status),
            "status_label": quotation.get_status_display(),
            "created_by_display": created_by_display,
            "validity_display": "—",
            "is_italic": quotation.status in {"lost", "cancelled", "canceled"},
        })

    return {
        "quotations": rows,
        "page_obj": page_obj,
        "querystring": querystring.urlencode(),
        "status_choices": Quotation.STATUS,
        "selected_statuses": statuses,
        "customers": Customer.objects.order_by("company_name"),
        "selected_customer": customer_id,
        "search": search,
        "can_create_quotation": user_role(request.user) in _ENTRY_ROLES,
    }


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
    return render(request, "quotations/list.html", _list_context(request))


@require_role(*_ENTRY_ROLES)
def quotation_new(request):
    """COT-02: formulário linear para criar uma cotação draft."""
    customer_qs = Customer.objects.order_by("company_name")
    engineer_qs = UserProfile.objects.filter(role=UserProfile.ROLE_ENGENHEIRO, is_active=True).select_related("user")

    if request.method == "POST":
        form = QuotationEntryForm(
            request.POST,
            customer_queryset=customer_qs,
            engineer_queryset=engineer_qs,
        )
        if form.is_valid():
            q = create_feixe_quotation(
                form.cleaned_data["customer"],
                form.cleaned_data["title"],
                created_by=request.user,
            )
            return redirect("quotations:detail", pk=q.pk)
    else:
        form = QuotationEntryForm(customer_queryset=customer_qs, engineer_queryset=engineer_qs)

    return render(
        request,
        "quotations/new.html",
        {
            "form": form,
        },
    )


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


@require_role(*_WRITE_ROLES)
def quotation_edit(request, pk):
    """Tier A: edita os inputs de uma cotação de FEIXE, agrupados por componente,
    e salva o resultado como uma NOVA revisão (recalculada pelo motor). O motor
    deriva a EAP dos inputs, então toda edição vai pra Quotation.inputs, não pras
    linhas da EAP (que o recompute regenera)."""
    orig = get_object_or_404(Quotation.objects.select_related("customer"), pk=pk)
    if orig.scope == "complete":
        # Permutador tem fluxo de dados próprio; edição fora do Tier A.
        return redirect("quotations:detail", pk=orig.pk)

    if request.method == "POST":
        form = FeixeDataSheetForm(request.POST)
        if form.is_valid():
            from apps.quotations.services import next_number, create_calculation_snapshot
            from apps.quotations.adapter import recompute
            customer, _ = Customer.objects.get_or_create(company_name=form.cleaned_data["customer_name"])
            q = Quotation.objects.create(
                number=next_number(),
                revision=orig.revision + 1,
                customer=customer,
                title=form.cleaned_data["title"],
                scope=orig.scope,
                status="draft",
                inputs=form.to_inputs_dict(),
                fator_preco=orig.fator_preco,
                impostos_pct=orig.impostos_pct,
                created_by=request.user,
            )
            recompute(q)
            create_calculation_snapshot(q)
            return redirect("quotations:detail", pk=q.pk)
        # inválido → re-render com erros (preview cai nos inputs originais)
        results = _preview(dict(orig.inputs or {}))
        return render(request, "quotations/edit.html", {"form": form, "results": results, "orig": orig})

    form = FeixeDataSheetForm(initial=FeixeDataSheetForm.initial_from_quotation(orig))
    results = _preview(dict(orig.inputs or {}))
    return render(request, "quotations/edit.html", {"form": form, "results": results, "orig": orig})


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
