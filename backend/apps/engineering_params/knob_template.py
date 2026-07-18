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


def _num(v):
    try:
        return round(float(v), 9)
    except (TypeError, ValueError):
        return None


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


# ── F3/C: import das camadas VERSIONADAS (horas + comercial) como NOVAS VIGÊNCIAS ────────────
def _upsert_rate(r, today):
    from datetime import timedelta
    op = r.get("operacao")
    if not op or r.get("rate_hh") is None:
        return False
    hh = Decimal(str(r["rate_hh"]))
    hm = None if r.get("rate_hm") in (None, "") else Decimal(str(r["rate_hm"]))
    cur = Rate.objects.vigente(op)
    if cur and cur.rate_hh == hh and cur.rate_hm == hm:
        return False
    if cur:
        if cur.valid_from == today:
            cur.rate_hh, cur.rate_hm = hh, hm
            cur.save(update_fields=["rate_hh", "rate_hm"])
            return True
        cur.valid_until = today - timedelta(days=1)
        cur.save(update_fields=["valid_until"])
    Rate.objects.create(operacao=op, rate_hh=hh, rate_hm=hm, valid_from=today)
    return True


def _upsert_param(h, today):
    from datetime import timedelta
    op, metodo, material = h.get("operacao"), h.get("metodo") or "", h.get("material") or None
    if not op or h.get("valor") is None:
        return False
    valor = Decimal(str(h["valor"]))
    cur = ProcessParameter.objects.vigente(op, metodo, material)
    if cur and cur.valor == valor:
        return False
    if cur:
        if cur.valid_from == today:
            cur.valor = valor
            cur.save(update_fields=["valor"])
            return True
        cur.valid_until = today - timedelta(days=1)
        cur.save(update_fields=["valid_until"])
    ProcessParameter.objects.create(operacao=op, metodo=metodo, material=material, valor=valor,
                                    unidade=h.get("unidade") or "fator", valid_from=today)
    return True


def _upsert_price(p, today):
    from datetime import timedelta
    from apps.materials.models import Material, MaterialPrice
    sigla, forma, preco = p.get("material"), p.get("forma"), p.get("preco_brl_kg")
    if not sigla or not forma or preco is None:
        return False, None
    mat = Material.objects.filter(sigla=sigla).first()
    if mat is None:
        return False, f"Material '{sigla}' não existe no tenant — preço ignorado."
    cur = (MaterialPrice.objects.filter(material=mat, forma=forma, valid_from__lte=today)
           .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=today))
           .order_by("-valid_from").first())
    preco_str = str(preco)
    if cur and str(cur.preco_brl_kg) == preco_str:
        return False, None
    if cur:
        if cur.valid_from == today:
            cur.preco_brl_kg = preco_str
            cur.save(update_fields=["preco_brl_kg"])
            return True, None
        cur.valid_until = today - timedelta(days=1)
        cur.save(update_fields=["valid_until"])
    MaterialPrice.objects.create(material=mat, forma=forma, preco_brl_kg=preco_str, valid_from=today)
    return True, None


def import_versioned(user, data, request=None):
    """Importa horas (ProcessParameter) + comercial (Rate/MaterialPrice) como NOVAS VIGÊNCIAS
    (nunca muta histórico). fator_correcao_mo NÃO é importado (é calibração do tenant de origem) —
    emite aviso forte de invalidação. Cada linha ruim vira nota, não quebra o lote. F3/C."""
    from apps.audit.services import log_access
    today = date.today()
    result = {"params": 0, "rates": 0, "prices": 0, "notes": []}

    for h in data.get("horas") or []:
        try:
            if _upsert_param(h, today):
                result["params"] += 1
        except Exception as exc:                                  # linha inválida → nota
            result["notes"].append(f"Horas '{h.get('operacao')}' ignorada: {exc}")

    com = data.get("commercial") or {}
    for r in com.get("rates") or []:
        try:
            if _upsert_rate(r, today):
                result["rates"] += 1
        except Exception as exc:
            result["notes"].append(f"Rate '{r.get('operacao')}' ignorada: {exc}")
    for p in com.get("material_prices") or []:
        try:
            ok, note = _upsert_price(p, today)
            if ok:
                result["prices"] += 1
            elif note:
                result["notes"].append(note)
        except Exception as exc:
            result["notes"].append(f"Preço '{p.get('material')}' ignorado: {exc}")

    if "fator_correcao_mo" in com:
        cfg = TenantParamConfig.get_solo()
        if _num(com["fator_correcao_mo"]) != _num(cfg.fator_correcao_mo):
            result["notes"].append(
                "fator_correcao_mo NÃO foi importado (é a calibração do tenant de origem). "
                "Importar rates/preços/knobs INVALIDA a calibração local — rode o back-solve de novo.")

    if request is not None and (result["params"] or result["rates"] or result["prices"]):
        log_access(request, "param_change", TenantParamConfig.get_solo(), {
            "knob": "import_template_versionado",
            "params": result["params"], "rates": result["rates"], "prices": result["prices"],
        })
    return result
