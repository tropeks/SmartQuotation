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
from datetime import date
from decimal import Decimal

from django.db import models
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
