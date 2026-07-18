"""Export/import do golden template da Config de Engenharia (V2 / F3, Bloco C).

O template é a "config de ouro": o domínio-expert (Wellington) configura, valida rodando cotações
e EXPORTA, em vez de nos pedir números. Camadas:
  - física (knobs do TenantParamConfig)  → compartilhável;
  - horas (ProcessParameter, versionado) → física;
  - comercial (fator_correcao_mo + Rate + MaterialPrice DESCRIPTOGRAFADO) → CONFIDENCIAL (decisão
    Rom 2026-07-18: incluir; o arquivo carrega a estrutura de custo — tratar como confidencial).

Import (F3/B/C) valida `template_schema_version`/`kind`, ignora+avisa chave fora do `knob_registry`,
e aplica: knob sensível → proposta+aprovação (F2); versionado → nova vigência (nunca muta histórico).
"""
import json
from datetime import date
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig

TEMPLATE_SCHEMA_VERSION = 1
TEMPLATE_KIND = "smartquotation.engineering_knobs"

# knobs do TenantParamConfig que entram no template (por camada).
PHYSICAL_KNOBS = [
    "perda_por_familia", "setup_frac", "drill_method_threshold_holes",
    "tema_compat_mode", "baffle_cut_default_pct", "tube_standard_lengths_mm",
    "u_bend_min_radius_factor",
]
# sensíveis (entram no cálculo): no IMPORT vão por proposta+aprovação (F2). O resto aplica direto.
SENSITIVE_KNOBS = {"perda_por_familia", "setup_frac", "drill_method_threshold_holes"}


def _jsonable(v):
    return float(v) if isinstance(v, Decimal) else v


def _vigentes(qs):
    hoje = date.today()
    return (qs.filter(valid_from__lte=hoje)
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=hoje)))


def export_template(include_commercial=True, source_tenant=""):
    """Serializa a config de engenharia do tenant ativo num dict versionado (JSON-safe)."""
    cfg = TenantParamConfig.get_solo()
    physical = {k: _jsonable(getattr(cfg, k)) for k in PHYSICAL_KNOBS}
    horas = [
        {"operacao": p.operacao, "metodo": p.metodo, "material": p.material,
         "valor": _jsonable(p.valor), "unidade": p.unidade}
        for p in (_vigentes(ProcessParameter.objects).filter(valor__isnull=False)
                  .order_by("operacao", "metodo", "material"))
    ]
    tpl = {
        "template_schema_version": TEMPLATE_SCHEMA_VERSION,
        "kind": TEMPLATE_KIND,
        "exported_at": timezone.now().isoformat(),
        "source_tenant": source_tenant,
        "confidential": bool(include_commercial),
        "knob_registry": list(PHYSICAL_KNOBS),
        "physical": physical,
        "horas": horas,
        "commercial": None,
    }
    if include_commercial:
        rates = [
            {"operacao": r.operacao, "rate_hh": _jsonable(r.rate_hh), "rate_hm": _jsonable(r.rate_hm)}
            for r in _vigentes(Rate.objects).order_by("operacao")
        ]
        precos = []
        try:
            from apps.materials.models import MaterialPrice
            for mp in _vigentes(MaterialPrice.objects.select_related("material")):
                precos.append({
                    "material": mp.material.sigla, "forma": mp.forma,
                    "preco_brl_kg": _jsonable(mp.preco_brl_kg),   # descriptografado na leitura
                })
        except Exception:
            pass
        tpl["commercial"] = {
            "fator_correcao_mo": _jsonable(cfg.fator_correcao_mo),
            "rates": rates,
            "material_prices": precos,
        }
    return tpl


# knobs FÍSICOS que, no import, vão pela proposta+aprovação (F2). Os demais físicos aplicam direto
# (não são sensíveis / não têm UI de edição própria). Alinhado a knob_proposals.SENSITIVE_KNOB_FIELDS.
PROPOSAL_KNOBS = ("perda_por_familia", "setup_frac")


class TemplateError(Exception):
    """JSON inválido / kind errado / versão incompatível."""


def parse_template(raw):
    """Valida e parseia o JSON do template. Retorna (data, warnings). Levanta TemplateError.
    Chave física fora do knob_registry atual → warning (ignorada), nunca aplicada às cegas."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise TemplateError("Arquivo não é um JSON válido.") from exc
    if not isinstance(data, dict) or data.get("kind") != TEMPLATE_KIND:
        raise TemplateError("Arquivo não é um template de knobs desta aplicação.")
    ver = data.get("template_schema_version")
    if ver != TEMPLATE_SCHEMA_VERSION:
        raise TemplateError(
            f"Versão de template incompatível ({ver} ≠ {TEMPLATE_SCHEMA_VERSION}). "
            "Reexporte no formato atual.")
    warnings = []
    physical = data.get("physical") or {}
    unknown = sorted(k for k in physical if k not in PHYSICAL_KNOBS)
    if unknown:
        warnings.append("Chaves desconhecidas ignoradas (knob removido/renomeado): "
                        + ", ".join(unknown))
    return data, warnings


def import_knobs(user, data, request=None):
    """Aplica a camada FÍSICA de um template já parseado. Knob livre → direto (auditado);
    knob de proposta (perda/setup) → cria proposta (F2, dupla validação). NÃO toca comercial nem
    modelos versionados (F3/C). Retorna {applied_free, proposal, notes}."""
    from apps.audit.services import log_access
    from apps.engineering_params import knob_proposals as kp

    physical = {k: v for k, v in (data.get("physical") or {}).items() if k in PHYSICAL_KNOBS}
    free = {k: v for k, v in physical.items() if k not in PROPOSAL_KNOBS}
    proposta_after = {k: v for k, v in physical.items()
                      if k in PROPOSAL_KNOBS and isinstance(v, dict) and v}

    result = {"applied_free": [], "proposal": None, "notes": []}

    if free:
        with transaction.atomic():
            cfg = TenantParamConfig.objects.select_for_update().get(pk=TenantParamConfig.get_solo().pk)
            before = {k: _jsonable(getattr(cfg, k)) for k in free}
            for k, v in free.items():
                setattr(cfg, k, v)
            cfg.save(update_fields=list(free))
            if request is not None:
                log_access(request, "param_change", cfg, {
                    "knob": "import_template_livre", "anterior": before, "novo": free,
                })
        result["applied_free"] = sorted(free)

    if proposta_after:
        try:
            result["proposal"] = kp.create_proposal(user, proposta_after)
        except Exception as exc:  # ValidationError (já há pendente) etc. → vira nota, não quebra
            msgs = getattr(exc, "messages", None) or [str(exc)]
            result["notes"].append("Knobs sensíveis não propostos: " + "; ".join(msgs))

    return result
