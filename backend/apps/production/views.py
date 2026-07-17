"""Views de Ordens de Fabricação."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.access.enforcement import require_capability, user_can
from apps.quotations.models import Quotation
from apps.production.models import InspectionItem, OrdemFabricacao, OFOperation, ProductionObservation
from apps.production import services


_ITP_ROLES = (UserProfile.ROLE_ENGENHEIRO, UserProfile.ROLE_ADMIN)

# Papéis com permissão de CONVERTER cotação em OF. Converter dispara os exports de
# ERP (Protheus/Nomus/SAP-B1), então fica com engenharia e o comercial que responde
# pelo pedido — o orçamentista monta a cotação mas não lança manufatura. Viewer é
# somente-leitura e fica explicitamente fora.
_OF_CONVERT_ROLES = (
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)

# Papéis com permissão de TRANSICIONAR status da OF (liberar/iniciar/concluir/
# cancelar). Mesmo conjunto do ITP: são ações de chão de fábrica. `cancelar` é
# terminal e `concluir` dispara emissão de NF-e — nenhuma delas é reversível pela app.
_OF_TRANSITION_ROLES = _ITP_ROLES


@login_required
def list_ordens(request):
    ordens = OrdemFabricacao.objects.select_related("quotation__customer").all()
    return render(request, "production/list.html", {"ordens": ordens})


@login_required
def ordem_detail(request, pk):
    of = get_object_or_404(
        OrdemFabricacao.objects.select_related("quotation__customer"),
        pk=pk,
    )
    itens = of.itens.prefetch_related("materiais", "operacoes").all()
    inspection_plan = getattr(of, "inspection_plan", None) if hasattr(of, "inspection_plan") else None
    inspection_items = None
    if inspection_plan is not None:
        inspection_items = (
            inspection_plan.items
            .select_related("of_operation", "accepted_by")
            .all()
        )
    # SQ-COST-6: sinal operacional de revisão de ProcessParameter — cross-OF (agrega
    # ProductionObservation por operação, ver services.production_review_signal), mas
    # exibido aqui restrito ao roteiro desta OF para não poluir a página com ruído de
    # outras OFs. Somente leitura: não recalcula/altera nada.
    of_operacao_codes = set(
        OFOperation.objects.filter(item__ordem=of).values_list("codigo_op", flat=True)
    )
    # SQ-COST-7: proposta somente-leitura de novo ProcessParameter para as mesmas
    # operações flagged — anexada por operação ao sinal acima (mesmo escopo/filtro
    # desta OF). Escopada a of_operacao_codes (SQ-COST-8 achado 1) para não computar
    # médias/mapeamento de ProcessParameter para operações flagged de outras OFs que
    # nunca seriam renderizadas aqui. Não recalcula/altera nada; ver
    # services.processparameter_suggestion.
    suggestion_by_op = {
        row["operacao"]: row
        for row in services.processparameter_suggestion(operacoes=of_operacao_codes)
    }
    review_signal_flagged = [
        {**row, "suggestion": suggestion_by_op.get(row["operacao"])}
        for row in services.production_review_signal()
        if row["status"] == ProductionObservation.STATUS_REVIEW_RECOMMENDED
        and row["operacao"] in of_operacao_codes
    ]
    # SQ-COST-4: hour_variance_observations é uma property que ordena/itera a relação
    # observations a cada chamada — computada uma única vez aqui (em vez de 2x no
    # template, num {% if %} e num {% for %} separados) e injetada pronta no contexto.
    hour_variance_observations = of.hour_variance_observations
    # SQ-COST-5: string de exibição da tolerância derivada de TOLERANCIA_HORAS_PCT, para
    # que copy do template e lógica de classificação não possam divergir.
    tolerancia_horas_pct = f"±{ProductionObservation.TOLERANCIA_HORAS_PCT:.0f}%"
    return render(request, "production/detail.html", {
        "of": of,
        "itens": itens,
        "inspection_plan": inspection_plan,
        "inspection_items": inspection_items,
        "can_manage_itp": user_can(request.user, "itp.manage"),
        "can_manage_of": user_can(request.user, "of.transition"),
        "review_signal_flagged": review_signal_flagged,
        "hour_variance_observations": hour_variance_observations,
        "tolerancia_horas_pct": tolerancia_horas_pct,
    })


@require_capability("of.convert")
@require_POST
def convert_quotation(request, quotation_pk):
    q = get_object_or_404(Quotation, pk=quotation_pk)
    try:
        of = services.convert_quotation_to_of(q, created_by=request.user, request=request)
        messages.success(request, f"Ordem de Fabricação {of.number} criada com sucesso.")
        return redirect("production:detail", pk=of.pk)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("quotations:detail", pk=q.pk)


@require_capability("of.transition")
@require_POST
def transition_ordem(request, pk):
    of = get_object_or_404(OrdemFabricacao, pk=pk)
    action = request.POST.get("action", "")
    action_map = {
        "liberar": services.liberar,
        "iniciar": services.iniciar_producao,
        "concluir": services.concluir,
        "cancelar": services.cancelar,
    }
    fn = action_map.get(action)
    if fn is None:
        messages.error(request, f"Ação inválida: {action}")
        return redirect("production:detail", pk=of.pk)
    try:
        fn(of, by=request.user, request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("production:detail", pk=of.pk)


@require_capability("itp.manage")
@require_POST
def appoint(request, op_pk):
    op = get_object_or_404(OFOperation, pk=op_pk)
    try:
        services.log_production_entry(
            op,
            request.user,
            request.POST.get("hours_hh") or 0,
            request.POST.get("hours_hm") or 0,
            request.POST.get("entry_date") or None,
            request.POST.get("notes", ""),
            request=request,
        )
        messages.success(request, "Apontamento registrado.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("production:detail", pk=op.item.ordem_id)


@require_capability("itp.manage")
@require_POST
def generate_itp(request, pk):
    of = get_object_or_404(OrdemFabricacao, pk=pk)
    try:
        services.generate_inspection_plan(of, generated_by=request.user, request=request)
        messages.success(request, "ITP gerado.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("production:detail", pk=of.pk)


@require_capability("itp.manage")
@require_POST
def accept_itp_item(request, item_pk):
    item = get_object_or_404(InspectionItem.objects.select_related("plan__ordem"), pk=item_pk)
    try:
        services.accept_inspection_item(
            item,
            accepted_by=request.user,
            notes=request.POST.get("notes", ""),
            request=request,
        )
        messages.success(request, "Item do ITP aceito.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("production:detail", pk=item.plan.ordem_id)
