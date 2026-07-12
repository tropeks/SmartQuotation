"""
Views do data sheet do feixe — session auth + HTMX (recálculo ao vivo).
Vertical slice: criar feixe -> recompute (preview ao vivo) -> salvar -> detalhe (EAP + preço).
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.audit.models import ApprovalRequest
from apps.audit.services import log_access
from apps.quotations.models import Quotation, Customer
from apps.quotations.forms import FeixeDataSheetForm, QuotationEntryForm, CustomerQuickForm
from apps.quotations.adapter import default_inputs, to_feixe_inputs
from apps.quotations.services import create_feixe_quotation

from pricing_engine.feixe_inputs import FeixeInputs
from pricing_engine.feixe_quote import quote_feixe


# Papéis com permissão de ESCRITA em cotações (criar/recomputar/precificar/revisar).
# Viewer é somente-leitura e fica explicitamente fora deste conjunto.
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

# Papéis com permissão de LEITURA de cotações (ver detalhe/EAP/drawer). Inclui o
# viewer, que é o papel dedicado de somente-leitura.
_READ_ROLES = (
    UserProfile.ROLE_VIEWER,
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
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


def _status_options():
    return [
        {"value": value, "label": label, "class": _status_class(value)}
        for value, label in Quotation.STATUS
    ]


def _render_status_control(request, quotation):
    return render(
        request,
        "quotations/_status_dropdown.html",
        {
            "q": quotation,
            "status_options": _status_options(),
            "status_class": _status_class(quotation.status),
        },
    )


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


@require_POST
@require_role(*_ENTRY_ROLES)
def customer_quick_create(request):
    """Cadastro rápido de cliente (modal da Nova Cotação). Retorna JSON.

    Sucesso: {"ok": true, "id": <pk>, "company_name": "..."} para o front injetar
    a nova opção no <select> de Cliente e selecioná-la. Erro: {"ok": false, "errors": {...}} 400.
    """
    form = CustomerQuickForm(request.POST)
    if form.is_valid():
        customer = form.save()
        return JsonResponse(
            {"ok": True, "id": customer.pk, "company_name": customer.company_name}
        )
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


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


@require_role(*_READ_ROLES)
def quotation_detail(request, pk):
    q = get_object_or_404(Quotation.objects.select_related("customer"), pk=pk)
    itens = (q.itens.prefetch_related("materiais", "operacoes")).all()
    has_active_of = q.ordens_fabricacao.exclude(status="cancelada").exists()
    approval_engineers = UserProfile.objects.filter(
        role=UserProfile.ROLE_ENGENHEIRO,
        is_active=True,
    ).exclude(crea_number="").select_related("user")
    pending_remote_request = q.approval_requests.filter(status=ApprovalRequest.STATUS_PENDING).first()
    from apps.production.services import is_convertible
    return render(request, "quotations/detail.html",
                  {
                      "q": q,
                      "itens": itens,
                      "has_active_of": has_active_of,
                      "is_convertible": is_convertible(q),
                      "approval_engineers": approval_engineers,
                      "pending_remote_request": pending_remote_request,
                      "status_options": _status_options(),
                      "status_class": _status_class(q.status),
                  })


from apps.quotations.models import QuotationItem


@require_role(*_READ_ROLES)
def eap_item_drawer(request, pk):
    """Tela 05 item 4 (parte B): parcial HTMX do DRAWER de uma linha da EAP (N1).

    Devolve os materiais (ItemMaterial) e a mão-de-obra (ItemOperation) do
    QuotationItem `pk`, com campos editáveis. Só LEITURA (monta o parcial); a
    persistência é no POST `eap_item_save`. Leitura liberada a qualquer MEMBRO
    do tenant (@require_role), como o detalhe.
    """
    item = get_object_or_404(
        QuotationItem.objects.select_related("quotation").prefetch_related("materiais", "operacoes"),
        pk=pk,
    )
    return render(request, "quotations/_eap_item_drawer.html", {"item": item})


def _parse_decimal(raw, fallback):
    """Converte um valor do form (pt-BR ou plain) em Decimal; mantém o valor atual
    se vazio/ inválido. Aceita '1234.56' e '1.234,56'."""
    from decimal import Decimal, InvalidOperation
    s = (raw or "").strip()
    if not s:
        return fallback
    # normaliza pt-BR: remove separador de milhar '.', vírgula decimal -> ponto
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return fallback


def _log_field_edit(request, resource, field, before, after):
    """Trilha de auditoria (quem/quando/campo/valor-anterior) de um override manual
    do drawer EAP — reusa o AccessLog do app `audit` (action='edit')."""
    if before == after:
        return
    log_access(request, "edit", resource, {"field": field, "before": str(before), "after": str(after)})


@require_role(*_WRITE_ROLES)
@require_POST
def eap_item_save(request, pk):
    """Tela 05 item 4 (parte B): persiste OVERRIDES MANUAIS nas rows ItemMaterial/
    ItemOperation da revisão CORRENTE e recalcula APENAS os roll-ups (item + cotação)
    por SOMA.

    GUARDRAIL ARQUITETURAL: a EAP normalmente é DERIVADA dos inputs pelo motor
    (adapter.recompute regenera TODA a EAP). Aqui é o oposto: edição no drawer é um
    override manual gravado DIRETO nas linhas — por isso NÃO chamamos o motor
    (recompute apagaria o override) e NÃO criamos nova revisão. Só somamos os custos
    já persistidos para atualizar item.custo_material/mo e os totais da cotação.

    Operação (ItemOperation): `custo_direto=True` edita custo em R$ direto (ex.:
    serviço de terceiro a preço fechado); `custo_direto=False` edita HORAS
    (horas_hh/horas_hm) e o custo é DERIVADO on-the-fly (horas × taxa_hora) via
    `ItemOperation.recalc_custo()` — não é mais um campo editável nesse caso.
    """
    item = get_object_or_404(
        QuotationItem.objects.select_related("quotation").prefetch_related("materiais", "operacoes"),
        pk=pk,
    )
    from decimal import Decimal

    for mat in item.materiais.all():
        campos = []
        peso_key = f"material_peso_{mat.pk}"
        custo_key = f"material_custo_{mat.pk}"
        if peso_key in request.POST:
            antes = mat.peso_bruto_kg
            mat.peso_bruto_kg = _parse_decimal(request.POST.get(peso_key), mat.peso_bruto_kg)
            campos.append("peso_bruto_kg")
            _log_field_edit(request, mat, "peso_bruto_kg", antes, mat.peso_bruto_kg)
        if custo_key in request.POST:
            antes = mat.custo
            mat.custo = _parse_decimal(request.POST.get(custo_key), mat.custo)
            campos.append("custo")
            _log_field_edit(request, mat, "custo", antes, mat.custo)
        if campos:
            mat.save(update_fields=campos)

    for op in item.operacoes.all():
        if op.custo_direto:
            custo_key = f"op_custo_{op.pk}"
            if custo_key in request.POST:
                antes = op.custo
                op.custo = _parse_decimal(request.POST.get(custo_key), op.custo)
                op.save(update_fields=["custo"])
                _log_field_edit(request, op, "custo", antes, op.custo)
        else:
            hh_key = f"op_horas_hh_{op.pk}"
            hm_key = f"op_horas_hm_{op.pk}"
            if hh_key in request.POST or hm_key in request.POST:
                antes_hh, antes_hm = op.horas_hh, op.horas_hm
                op.horas_hh = _parse_decimal(request.POST.get(hh_key), op.horas_hh)
                op.horas_hm = _parse_decimal(request.POST.get(hm_key), op.horas_hm)
                op.save(update_fields=["horas_hh", "horas_hm"])
                op.recalc_custo()
                _log_field_edit(request, op, "horas_hh", antes_hh, op.horas_hh)
                _log_field_edit(request, op, "horas_hm", antes_hm, op.horas_hm)

    # Roll-up SOMENTE por soma (SEM motor): item = soma das rows; cotação = soma dos itens.
    item.custo_material = sum((m.custo for m in item.materiais.all()), Decimal("0"))
    item.custo_mo = sum((o.custo for o in item.operacoes.all() if o.aplicavel), Decimal("0"))
    item.save(update_fields=["custo_material", "custo_mo"])

    q = item.quotation
    q.custo_material = sum((i.custo_material for i in q.itens.all()), Decimal("0"))
    q.custo_mo = sum((i.custo_mo for i in q.itens.all()), Decimal("0"))
    q.custo_total = q.custo_material + q.custo_mo
    # computed_at NÃO é tocado de propósito: sinaliza que o motor não rodou.
    q.save(update_fields=["custo_material", "custo_mo", "custo_total", "updated_at"])

    # Recarrega o item persistido antes do re-render para o drawer refletir o
    # estado canônico do banco, sem depender de caches/instâncias mutadas.
    item.refresh_from_db()

    return render(request, "quotations/_eap_item_drawer.html", {"item": item, "saved": True})


@require_role(*_WRITE_ROLES)
@require_POST
def quotation_set_status(request, pk):
    q = get_object_or_404(Quotation, pk=pk)
    status = request.POST.get("status", "")
    valid_statuses = dict(Quotation.STATUS)
    if status not in valid_statuses:
        return HttpResponseBadRequest("Status inválido.")

    q.status = status
    q.save(update_fields=["status", "updated_at"])
    return _render_status_control(request, q)


# Allowlist de metadados comerciais editáveis INLINE (Tela 05 item 4).
# Só `title` existe hoje no model; os demais entram no allowlist para o dia em que
# o model (ou um related) ganhar description/valid_until/delivery_weeks/payment_terms
# — o loop de update_meta ignora silenciosamente os que não existem (hasattr).
_META_FIELDS = ("title", "description", "valid_until", "delivery_weeks", "payment_terms")


@require_role(*_WRITE_ROLES)
@require_POST
def quotation_update_meta(request, pk):
    """Tela 05 item 4: edição INLINE de METADADOS comerciais da cotação ATUAL.

    NÃO confundir com o fluxo de NOVA REVISÃO (quotation_edit / quotation_revise),
    que recalcula pela pricing_engine e cria uma revisão nova. Aqui NÃO se chama o
    motor e NÃO se cria revisão: apenas persiste campos comerciais leves (title, …)
    na própria cotação. Retorna JSON para o front sair do modo edição e mostrar toast.
    """
    q = get_object_or_404(Quotation, pk=pk)
    updated = []
    for field in _META_FIELDS:
        if not hasattr(q, field) or field not in request.POST:
            continue
        value = (request.POST.get(field) or "").strip()
        if field == "title" and not value:
            return JsonResponse(
                {"ok": False, "errors": {"title": "Título é obrigatório."}}, status=400
            )
        setattr(q, field, value)
        updated.append(field)
    if updated:
        # update_fields explícito: garante que só metadados são tocados (nunca a EAP/custos).
        q.save(update_fields=[*updated, "updated_at"])
    return JsonResponse({"ok": True, "title": q.title, "updated": updated})


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
