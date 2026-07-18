"""
Validações de negócio RÍGIDAS empilhadas no recompute (Quotation.avisos):
- metalurgia/térmica: incompatibilidade feixe Inox × casco Aço Carbono em espelho fixo;
  contaminação galvânica (chicana A36 + tubos Inox em serviço corrosivo).
Cada aviso: {"nivel": "warning"|"block", "codigo": str, "mensagem": str}.

Reaproveita _familia_de_material (databook) e tema_templates.check_compatibility.
"""
from apps.quotations.databook import _familia_de_material

# Coef. de expansão térmica linear (1/°C): inox austenítico ~17,3e-6; aço carbono ~11,7e-6.
ALPHA_INOX = 17.3e-6
ALPHA_CS = 11.7e-6
# Cabeçotes traseiros de ESPELHO FIXO (feixe preso aos dois espelhos → sem alívio de expansão).
ESPELHO_FIXO = {"L", "M", "N"}


def _is_inox(sigla: str) -> bool:
    return _familia_de_material(sigla) in ("inox_304L", "inox_316L")


def _is_carbono(sigla: str) -> bool:
    return bool((sigla or "").strip()) and _familia_de_material(sigla) == "aco_carbono"


def _extrair_contexto(quotation) -> dict:
    """Extrai materiais/tipo TEMA/serviço da cotação, de QuotationParts (scope=parts)
    ou dos inputs (feixe/completo)."""
    ctx = {"feixe": "", "casco": "", "chicana": "", "rear": "",
           "front": "", "shell": "", "corrosivo": False, "delta_t": 0.0}
    inputs = quotation.inputs or {}

    if quotation.scope == "parts":
        for part in quotation.parts.filter(incluso=True).select_related("template"):
            tp = part.template.tema_part
            letra = (part.tema_letter or "").upper()
            if tp == "tube_bundle":
                ctx["feixe"] = part.material_sigla
            elif tp == "shell":
                ctx["casco"] = part.material_sigla
                ctx["shell"] = letra
            elif tp == "baffle":
                ctx["chicana"] = part.material_sigla
            elif tp == "rear_head":
                ctx["rear"] = letra
            elif tp == "front_head":
                ctx["front"] = letra
            p = part.params or {}
            if p.get("corrosivo") or p.get("servico_corrosivo"):
                ctx["corrosivo"] = True
            try:
                ctx["delta_t"] = ctx["delta_t"] or abs(float(p.get("delta_t") or 0))
            except (TypeError, ValueError):
                pass

    ctx["feixe"] = ctx["feixe"] or inputs.get("tubo_material", "")
    ctx["casco"] = ctx["casco"] or inputs.get("casco_material") or inputs.get("classe_casco", "")
    ctx["chicana"] = ctx["chicana"] or inputs.get("chicana_material", "")
    desig = (inputs.get("designacao") or "")
    if not ctx["rear"] and len(desig) >= 3:
        ctx["rear"] = desig[2].upper()
    if inputs.get("servico_corrosivo") or inputs.get("corrosivo"):
        ctx["corrosivo"] = True
    if not ctx["delta_t"]:
        try:
            ctx["delta_t"] = abs(float(inputs.get("temperatura_projeto_c") or 0) - 20.0)
        except (TypeError, ValueError):
            ctx["delta_t"] = 0.0
    return ctx


def validate_metalurgia(quotation) -> list[dict]:
    avisos: list[dict] = []
    ctx = _extrair_contexto(quotation)

    # (a) expansão térmica diferencial: feixe Inox + casco Aço Carbono em espelho fixo.
    if _is_inox(ctx["feixe"]) and _is_carbono(ctx["casco"]) and ctx["rear"] in ESPELHO_FIXO:
        dt = ctx["delta_t"] or 100.0
        dl = (ALPHA_INOX - ALPHA_CS) * dt * 1000.0   # mm por metro de comprimento
        avisos.append({
            "nivel": "warning", "codigo": "THERM_EXPANSAO_FIXO",
            "mensagem": (
                f"Feixe em Inox + casco em Aço Carbono com espelho fixo (TEMA {ctx['rear']}): "
                f"expansão térmica diferencial (~{dl:.2f} mm/m a ΔT≈{dt:.0f}°C) tende a romper a "
                f"ligação tubo-espelho. Recomendado: junta de expansão no casco OU construção "
                f"TEMA U (feixe em U) ou S (cabeçote flutuante)."),
        })

    # (b) contaminação galvânica: chicana em Aço Carbono (A36) + tubos Inox + serviço corrosivo.
    if _is_inox(ctx["feixe"]) and _is_carbono(ctx["chicana"]) and ctx["corrosivo"]:
        avisos.append({
            "nivel": "block", "codigo": "GALVANICA_CHICANA",
            "mensagem": (
                "Chicana em Aço Carbono com tubos em Inox em ambiente corrosivo: risco de "
                "corrosão/contaminação galvânica. Use chicana em material compatível (inox)."),
        })

    # Folga periférica do feixe de reposição (RCB-4.3) — some ao mesmo aviso.
    avisos.extend(validate_folga_feixe(quotation))

    # Raio mínimo da curva em U (RCB-2.3): fator × OD, fator vindo do TenantParamConfig (C3).
    avisos.extend(validate_u_bend_radius(quotation))

    # Compatibilidade TEMA (reuso) quando as letras estão disponíveis.
    if ctx["front"] or ctx["shell"] or ctx["rear"]:
        try:
            from apps.tema_templates.models import check_compatibility
            for msg in check_compatibility(ctx["front"], ctx["shell"], ctx["rear"]):
                avisos.append({"nivel": "warning", "codigo": "TEMA_COMPAT", "mensagem": msg})
        except Exception:
            pass

    return avisos


def _to_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _is_u_feixe(inputs: dict) -> bool:
    tipo = (inputs.get("tipo") or "").upper()
    return tipo.startswith("TUBO U") or tipo == "TUBO U"


def validate_u_bend_radius(quotation) -> list[dict]:
    """Raio mínimo da curva em U (TEMA RCB-2.3): raio ≥ fator × OD do tubo. O fator é
    configurável por tenant (TenantParamConfig.u_bend_min_radius_factor, C3). Só se aplica a
    feixe em U e quando o raio da curva foi informado no data sheet."""
    from apps.quotations.domain_params import u_bend_min_radius_mm

    inputs = quotation.inputs or {}
    if not _is_u_feixe(inputs):
        return []
    raio = _to_float(inputs.get("u_bend_radius_mm"))
    od = _to_float(inputs.get("tubo_od_mm") or inputs.get("od_tubo_mm"))
    if raio <= 0 or od <= 0:
        return []
    try:
        from apps.engineering_params.models import TenantParamConfig
        factor = float(TenantParamConfig.get_solo().u_bend_min_radius_factor)
    except Exception:
        factor = 1.5
    minimo = u_bend_min_radius_mm(od, factor)
    if raio < minimo:
        return [{"nivel": "block", "codigo": "U_BEND_RAIO_MINIMO",
                 "mensagem": (
                     f"Raio da curva em U ({raio:.1f} mm) abaixo do mínimo TEMA RCB-2.3: "
                     f"{factor:g}×OD = {minimo:.1f} mm (OD {od:.1f} mm). Aumente o raio ou "
                     f"reduza o OD do tubo.")}]
    return []


def _contexto_feixe(quotation) -> dict:
    """Geometria do feixe de reposição + Ø do casco EXISTENTE do cliente (parts ou inputs)."""
    inputs = quotation.inputs or {}
    ctx = {"n_tubos": 0, "od": 0.0, "d_casco": 0.0, "rear": ""}
    if quotation.scope == "parts":
        for part in quotation.parts.filter(incluso=True).select_related("template"):
            tp = part.template.tema_part
            p = part.params or {}
            if tp == "tube_bundle":
                ctx["n_tubos"] = int(_to_float(p.get("n_tubos")))
                ctx["od"] = _to_float(p.get("od_tubo_mm") or p.get("tubo_od_mm"))
                ctx["d_casco"] = _to_float(p.get("d_casco_mm") or p.get("diametro_casco_mm"))
                ctx["rear"] = ctx["rear"] or (p.get("cabecote") or part.tema_letter or "").upper()
            elif tp == "rear_head":
                ctx["rear"] = (part.tema_letter or "").upper()
    if not ctx["n_tubos"]:
        ctx["n_tubos"] = int(_to_float(inputs.get("n_tubos")))
    ctx["od"] = ctx["od"] or _to_float(inputs.get("tubo_od_mm") or inputs.get("od_tubo_mm"))
    ctx["d_casco"] = ctx["d_casco"] or _to_float(
        inputs.get("diametro_casco_mm") or inputs.get("d_casco_mm"))
    if not ctx["rear"]:
        desig = inputs.get("designacao") or ""
        if len(desig) >= 3:
            ctx["rear"] = desig[2].upper()
    return ctx


def validate_folga_feixe(quotation) -> list[dict]:
    """Folga periférica shell-to-bundle (TEMA RCB-4.3): garante que o feixe de reposição
    ENTRA e não trava no casco EXISTENTE do cliente. Reaproveita o motor puro
    (permutador_layout.d_feixe_min + folga_cabecote)."""
    from pricing_engine.permutador_layout import d_feixe_min, folga_cabecote

    ctx = _contexto_feixe(quotation)
    n, od, d_casco, rear = ctx["n_tubos"], ctx["od"], ctx["d_casco"], ctx["rear"]
    if not (n and od and d_casco):
        return []
    d_feixe = d_feixe_min(n, od)
    folga_min = folga_cabecote(rear)          # folga diametral mínima (RCB-4.3) por cabeçote
    folga_disp = d_casco - d_feixe
    if folga_disp < 0:
        return [{"nivel": "block", "codigo": "FOLGA_RCB43_NEGATIVA",
                 "mensagem": (
                     f"Feixe de reposição NÃO entra no casco do cliente: envelope do feixe "
                     f"≈ {d_feixe:.0f}mm > Ø casco {d_casco:.0f}mm. Reveja tube-count/OD "
                     f"(TEMA RCB-4.3).")}]
    if folga_disp < folga_min:
        return [{"nivel": "warning", "codigo": "FOLGA_RCB43_APERTADA",
                 "mensagem": (
                     f"Folga periférica insuficiente (TEMA RCB-4.3): disponível ~{folga_disp:.0f}mm "
                     f"< mínimo {folga_min:.0f}mm p/ cabeçote '{rear or '—'}'. Risco do feixe "
                     f"travar no casco Ø{d_casco:.0f}mm (feixe ≈ {d_feixe:.0f}mm).")}]
    return []
