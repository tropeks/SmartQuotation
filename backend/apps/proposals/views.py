"""Views da proposta: criar (do template) -> editar texto -> gerar DOCX/PDF -> baixar."""
import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role
from apps.quotations.models import Quotation
from apps.proposals.models import Proposal, ProposalTemplate
from apps.proposals import services
from apps.audit.services import log_access

# Espelha o RBAC de production/engineering_params: só papéis que JÁ editam custeio
# criam/editam/geram proposta. Membros sem esses papéis veem (detail/download).
_WRITE_ROLES = (UserProfile.ROLE_ENGENHEIRO, UserProfile.ROLE_ADMIN)


@require_role(*_WRITE_ROLES)
def proposal_create(request, quotation_pk):
    """Cria a proposta a partir do template padrão (textos já renderizados, editáveis)."""
    q = get_object_or_404(Quotation, pk=quotation_pk)
    template = ProposalTemplate.get_default()
    proposal = services.create_proposal(q, template)
    return redirect("proposals:edit", pk=proposal.pk)


@require_role(*_WRITE_ROLES)
def proposal_edit(request, pk):
    """Edita/customiza os textos da proposta (template é ponto de partida)."""
    p = get_object_or_404(Proposal.objects.select_related("quotation", "template"), pk=pk)
    if request.method == "POST":
        for f in ("intro_text", "scope_text", "terms_text", "closing_text"):
            setattr(p, f, request.POST.get(f, ""))
        p.status = "draft"
        p.save()
        if "generate" in request.POST:
            services.generate(p)
            log_access(request, "generate", p, {"quotation_id": p.quotation_id})
            return redirect("proposals:detail", pk=p.pk)
        return redirect("proposals:edit", pk=p.pk)
    return render(request, "proposals/edit.html", {"p": p, "q": p.quotation})


@login_required
def proposal_detail(request, pk):
    p = get_object_or_404(Proposal.objects.select_related("quotation"), pk=pk)
    return render(request, "proposals/detail.html", {"p": p, "q": p.quotation})


@login_required
def proposal_download(request, pk, fmt):
    if fmt not in {"pdf", "docx"}:
        raise Http404("Formato inválido.")
    p = get_object_or_404(Proposal, pk=pk)
    rel = p.pdf_path if fmt == "pdf" else p.docx_path
    if not rel:
        raise Http404("Arquivo ainda não gerado.")
    path = os.path.join(settings.MEDIA_ROOT, rel)
    if not os.path.exists(path):
        raise Http404("Arquivo não encontrado.")
    log_access(request, "download", p, {"format": fmt, "path": rel})
    return FileResponse(open(path, "rb"), as_attachment=True, filename=os.path.basename(path))
