"""Painel HTMX do log de exportação Nomus por OF + reexport manual (task 5)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.integrations.nomus.models import NomusSyncRun
from apps.production import services as production_services
from apps.production.models import OrdemFabricacao

_REEXPORT_ROLES = (
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)


def _sync_runs_for_of(of):
    return (
        NomusSyncRun.objects.filter(
            entity_type=NomusSyncRun.ENTITY_PRODUCTION_ORDER,
            payload__source_snapshot__of_id=of.pk,
        )
        .select_related("export_log")
        .order_by("-created_at")
    )


def _panel_context(request, of):
    return {
        "of": of,
        "sync_runs": _sync_runs_for_of(of),
        "can_reexport": user_role(request.user) in _REEXPORT_ROLES,
    }


@login_required
def export_panel(request, of_pk):
    of = get_object_or_404(OrdemFabricacao, pk=of_pk)
    return render(request, "nomus/_export_panel.html", _panel_context(request, of))


@require_role(*_REEXPORT_ROLES)
@require_POST
def reexport(request, of_pk):
    of = get_object_or_404(OrdemFabricacao, pk=of_pk)
    production_services.reexport_nomus(of, by=request.user, request=request)
    return render(request, "nomus/_export_panel.html", _panel_context(request, of))
