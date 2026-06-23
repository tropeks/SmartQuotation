"""Views de Ordens de Fabricação."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.quotations.models import Quotation
from apps.production.models import OrdemFabricacao, OFOperation
from apps.production import services


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
    return render(request, "production/detail.html", {"of": of, "itens": itens})


@login_required
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


@login_required
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


@login_required
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
