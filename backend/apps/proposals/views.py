"""Views da proposta: criar (do template) -> editar texto -> gerar DOCX/PDF -> baixar."""
import os
from smtplib import SMTPException
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role
from apps.quotations.models import Quotation
from apps.proposals.models import Proposal, ProposalTemplate
from apps.proposals.richtext import normalize_rich_text
from apps.proposals import services
from apps.audit.services import log_access

# Espelha o RBAC de production/engineering_params: só papéis que JÁ editam custeio
# criam/editam/geram proposta. Membros sem esses papéis veem (detail/download).
_WRITE_ROLES = (UserProfile.ROLE_ENGENHEIRO, UserProfile.ROLE_ADMIN)


def _proposal_redirect_target(request, proposal):
    next_url = request.POST.get("next", "")
    return next_url if next_url.startswith("/") else redirect("proposals:detail", pk=proposal.pk).url


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
    p = get_object_or_404(
        Proposal.objects.select_related("quotation", "template", "quotation__customer").prefetch_related("versions"),
        pk=pk,
    )
    if request.method == "POST":
        for f in ("intro_text", "scope_text", "terms_text", "closing_text"):
            setattr(p, f, request.POST.get(f, ""))
        p.object_text = normalize_rich_text(request.POST.get("object_text", ""))
        p.exclusions_text = normalize_rich_text(request.POST.get("exclusions_text", ""))
        p.status = "draft"
        p.save()
        if "generate" in request.POST:
            services.generate(p, generated_by=request.user)
            log_access(request, "generate", p, {"quotation_id": p.quotation_id})
            return redirect("proposals:detail", pk=p.pk)
        return redirect("proposals:edit", pk=p.pk)
    # Textos-modelo do tenant (§4 Objeto / §5 Exclusões) renderizados com os dados da
    # cotação, disponibilizados p/ o botão "Carregar modelo" injetar via Alpine (tela 06).
    object_template = exclusions_template = ""
    if p.template:
        model_texts = services.render_template_texts(p.template, services.build_context(p.quotation))
        object_template = model_texts["object_text"]
        exclusions_template = model_texts["exclusions_text"]
    return render(request, "proposals/edit.html", {
        "p": p, "q": p.quotation,
        "object_template": object_template,
        "exclusions_template": exclusions_template,
        "versions": p.versions.all(),
        "email_default_body": services.default_email_body(p),
    })


@login_required
def proposal_detail(request, pk):
    p = get_object_or_404(
        Proposal.objects.select_related("quotation", "quotation__customer").prefetch_related("versions"),
        pk=pk,
    )
    return render(request, "proposals/detail.html", {
        "p": p,
        "q": p.quotation,
        "versions": p.versions.all(),
        "email_default_body": services.default_email_body(p),
    })


@login_required
def proposal_download(request, pk, fmt):
    if fmt not in {"pdf", "docx"}:
        raise Http404("Formato inválido.")
    p = get_object_or_404(Proposal, pk=pk)
    rel = p.pdf_path if fmt == "pdf" else p.docx_path
    if not rel:
        raise Http404("Arquivo ainda não gerado.")
    if not default_storage.exists(rel):
        raise Http404("Arquivo não encontrado.")
    log_access(request, "download", p, {"format": fmt, "path": rel})
    return FileResponse(default_storage.open(rel, "rb"), as_attachment=True, filename=os.path.basename(rel))


@login_required
def proposal_preview(request, pk):
    """Serve o PDF da proposta INLINE (preview embutido em <iframe> na tela de edição/detalhe).
    Gera na hora se ainda não existir; reusa o último PDF já gerado caso contrário."""
    p = get_object_or_404(Proposal, pk=pk)
    if not p.pdf_path or not default_storage.exists(p.pdf_path):
        p.pdf_path = services.generate_pdf(p)
        p.save(update_fields=["pdf_path"])
    log_access(request, "preview", p, {"path": p.pdf_path})
    return FileResponse(default_storage.open(p.pdf_path, "rb"), filename=os.path.basename(p.pdf_path))


@require_role(*_WRITE_ROLES)
def proposal_send_email(request, pk):
    if request.method != "POST":
        raise Http404()
    p = get_object_or_404(Proposal.objects.select_related("quotation", "quotation__customer"), pk=pk)
    redirect_to = _proposal_redirect_target(request, p)
    to_email = (request.POST.get("to_email") or "").strip()
    body = request.POST.get("body", "")

    try:
        validate_email(to_email)
    except ValidationError:
        messages.error(request, "Informe um e-mail de destino válido.")
        return redirect(redirect_to)

    try:
        services.send_email(p, to_email=to_email, body=body, sent_by=request.user)
    except (ValueError, FileNotFoundError):
        messages.error(request, "Gere a proposta em PDF antes de enviar por e-mail.")
        return redirect(redirect_to)
    except (ImproperlyConfigured, OSError, ConnectionError, RuntimeError, SMTPException):
        messages.error(request, "Nao foi possivel enviar o e-mail com a configuracao atual.")
        return redirect(redirect_to)

    messages.success(request, "E-mail enviado com sucesso.")
    return redirect(redirect_to)
