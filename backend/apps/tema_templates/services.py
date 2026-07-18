"""Ponte composição TEMA ↔ motor de custeio do permutador completo (pricing_engine).

Designações TEMA com custeio paramétrico validado contra gabarito ENGEMATEX:
  BEU (bonnet + casco 1 passe + feixe em U)        — Δ 0,0% vs R$ 128.160
  BEM (bonnet + casco 1 passe + cabeçote fixo)     — Δ 0,0% vs R$ 119.295
Derivado dinamicamente dos seeds presentes (pricing_engine/seeds/{d}_materiais.json).
"""
from __future__ import annotations

from pricing_engine.permutador_quote import designacoes_disponiveis

# designações cujo custeio paramétrico já foi validado contra gabarito real
COSTABLE = set(designacoes_disponiveis())

# fator multiplicador de horas de caldeiraria/solda por classe metalúrgica (#3 agy).
# Aço-carbono = 1,0 (referência). Defaults de engenharia EDITÁVEIS — não medidos.
# Aplicado POR LADO (feixe/casco) → suporta construção bimetálica (feixe inox + casco CS).
# INCONEL (Ni-Cr-Mo) e MONEL (Ni-Cu) são classes distintas (#2 Wellington); NIQUEL = alias de
# compat (= Inconel). Fatores de engenharia EDITÁVEIS — não medidos.
LIGA_FATOR = {
    "CS": 1.0, "INOX": 1.4, "DUPLEX": 1.7, "INCONEL": 2.3, "MONEL": 2.0, "NIQUEL": 2.3,
}
# densidade por classe (kgf/mm³): Inconel 625 ~8,44; Monel 400 ~8,80.
CLASSE_DENSIDADE = {
    "CS": 7.85e-6, "INOX": 7.93e-6, "DUPLEX": 7.80e-6,
    "INCONEL": 8.44e-6, "MONEL": 8.80e-6, "NIQUEL": 8.44e-6,
}
# fator de PREÇO/kg da matéria-prima por classe vs aço-carbono (#agy 1.C — material é ~70%
# do custo de liga nobre). Multiplicadores típicos de mercado, EDITÁVEIS — não cotados.
PRECO_FATOR = {
    "CS": 1.0, "INOX": 4.5, "DUPLEX": 6.0, "INCONEL": 13.0, "MONEL": 9.0, "NIQUEL": 13.0,
}
LIGA_CHOICES = [("CS", "Aço Carbono"), ("INOX", "Aço Inox (300/400)"),
                ("DUPLEX", "Duplex / Superduplex"),
                ("INCONEL", "Inconel 625 (Ni-Cr-Mo)"), ("MONEL", "Monel 400 (Ni-Cu)")]


# ---- Cadastro de ligas (tenant) com FALLBACK nas constantes hardcoded acima ----
# O cadastro (apps.materials.LigaMetalurgica) permite a ENGEMATEX criar/editar ligas sem deploy
# (#2 Wellington). Se a liga não estiver cadastrada (ou sem banco), usa as constantes.

def _liga_db(codigo):
    """LigaMetalurgica ativa do tenant por código (None se não cadastrada / fora de request)."""
    try:
        from apps.materials.models import LigaMetalurgica
        return LigaMetalurgica.objects.filter(codigo=(codigo or "").upper(), is_active=True).first()
    except Exception:
        return None


def _fator_liga(codigo):
    """(liga_fator, densidade_kg_mm3, preco_fator) — do cadastro do tenant, fallback nas constantes."""
    cu = (codigo or "CS").upper()
    obj = _liga_db(cu)
    if obj:
        dens = float(obj.densidade_kg_mm3) or CLASSE_DENSIDADE.get(cu, CLASSE_DENSIDADE["CS"])
        return float(obj.liga_fator), dens, float(obj.preco_fator)
    return (LIGA_FATOR.get(cu, 1.0), CLASSE_DENSIDADE.get(cu, CLASSE_DENSIDADE["CS"]),
            PRECO_FATOR.get(cu, 1.0))


def liga_para_asme(codigo):
    """dict p/ asme.checar_espessura_casco do cadastro do tenant (None → fallback hardcoded)."""
    obj = _liga_db(codigo)
    if not obj:
        return None
    return {"spec": obj.spec, "s_curva": obj.s_curva_num(),
            "temp_limite": obj.temp_limite_c, "procedencia": obj.procedencia()}


def liga_choices():
    """Choices do dropdown de classe — do cadastro do tenant (ativas), fallback nas constantes."""
    try:
        from apps.materials.models import LigaMetalurgica
        qs = list(LigaMetalurgica.objects.filter(is_active=True).order_by("ordem", "codigo"))
        if qs:
            return [(o.codigo, o.nome) for o in qs]
    except Exception:
        pass
    return LIGA_CHOICES


def _metalurgia(cleaned):
    """(liga_por_lado, dens_por_lado, preco_por_lado) das classes feixe/casco. CS → 1,0.
    liga escala MO; dens escala peso; preço escala R$/kg da matéria-prima (#agy 1.C).
    Fatores do cadastro de ligas do tenant (fallback nas constantes)."""
    cf = cleaned.get("classe_feixe", "CS")
    cc = cleaned.get("classe_casco", "CS")
    # base = densidade do aço-carbono: os pesos do seed BEU/BEM foram extraídos em CS, então a
    # razão classe/CS é correta. (Se um dia houver seed nativo em liga, derivar a base do seed.)
    base = CLASSE_DENSIDADE["CS"]
    lf_f, df_f, pf_f = _fator_liga(cf)
    lf_c, df_c, pf_c = _fator_liga(cc)
    liga = {"feixe": lf_f, "casco": lf_c}
    dens = {"feixe": df_f / base, "casco": df_c / base}
    preco = {"feixe": pf_f, "casco": pf_c}
    return liga, dens, preco


def tenant_cost_chain():
    """Monta a TenantCostChain do tenant (preços de material cifrados + fator de MO),
    reaproveitando o mesmo padrão do adapter de cotações. Sem dados → None (usa defaults)."""
    from pricing_engine.rates import TenantCostChain, op_key
    chain = TenantCostChain()
    try:
        from datetime import date
        from apps.materials.models import MaterialPrice
        hoje = date.today()
        for mp in MaterialPrice.objects.select_related("material").filter(valid_from__lte=hoje):
            if mp.valid_until and mp.valid_until < hoje:
                continue
            try:
                chain.material_price[(mp.material.sigla.upper(), mp.forma.lower())] = float(mp.preco_brl_kg)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    try:
        from datetime import date
        from django.db import models
        from apps.engineering_params.models import Rate, TenantParamConfig
        hoje = date.today()
        for r in (Rate.objects.filter(valid_from__lte=hoje)
                  .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=hoje))
                  .order_by("valid_from")):
            chain.rate_hh[op_key(r.operacao)] = float(r.rate_hh)
            if r.rate_hm is not None:
                chain.rate_hm[op_key(r.operacao)] = float(r.rate_hm)
        cfg = TenantParamConfig.get_solo()
        chain.fator_correcao_mo = float(cfg.fator_correcao_mo)
        # knob configurável (V2/F1): scrap por família → override do motor. É AQUI que a perda
        # pega no custeio (estimate_complete usa dims_override). Coerção visível reusa o adapter.
        from apps.quotations.adapter import _coerce_factor_map
        chain.perda_por_familia = _coerce_factor_map(cfg.perda_por_familia, "perda_por_familia")
        chain.setup_frac = _coerce_factor_map(cfg.setup_frac, "setup_frac")
    except Exception:
        pass
    return chain


def reference_inputs(designacao: str):
    """Valores de referência (do seed) p/ pré-preencher o data sheet do trocador completo."""
    d = (designacao or "").upper()
    if d not in COSTABLE:
        return {}
    import json
    import os
    from pricing_engine import permutador_quote as pq
    path = os.path.join(os.path.dirname(pq.__file__), "seeds", f"{d.lower()}_materiais.json")
    try:
        mats = json.load(open(path, encoding="utf-8"))["materiais"]
    except Exception:
        return {}
    import math
    by_label = {m["label"]: m.get("dims", {}) for m in mats if m.get("label")}
    tub = by_label.get("TUBOS DE TROCA TÉRMICA", {})
    vir = by_label.get("VIROLA", {})
    # nº de chicanas: material 'CHICANAS TRANSVERSAIS' (família perfurado)
    chic = next((m.get("dims", {}) for m in mats
                 if "CHICANA" in (m.get("label") or "").upper()), {})
    # diâmetro do casco: a maior virola tem LARGURA = circunferência → D ≈ LARGURA/π
    larguras = [m.get("dims", {}).get("LARGURA") for m in mats if "VIROLA" in (m.get("label") or "")]
    larg = max([x for x in larguras if x], default=None)
    d_casco = round(larg / math.pi, 1) if larg else None
    return {
        "designacao": d,
        "n_tubos": tub.get("QUANTIDADE"),
        "comprimento_tubo_mm": tub.get("COMPR."),
        "od_tubo_mm": tub.get("OD"),
        "esp_tubo_mm": tub.get("ESP."),
        "comprimento_casco_mm": vir.get("COMPR."),
        "n_chicanas": chic.get("QUANTIDADE") or 1,
        "diametro_casco_mm": d_casco,
        "esp_casco_mm": vir.get("ESP."),
        # nº de passes dos tubos (referência): BEU feixe-U ≥ 2 passes; demais ~2 (típico).
        "n_passes_tubos": 2,
        "fator_correcao_mo": 1.0,
    }


# escopo de radiografia → multiplicador do raio-X (param 'rt'). Referência do gabarito = Total
# (100%, confirmado Wellington 2026-06-13) → baseline 1,0. Parcial (10%) ~1/3 (setup domina, não
# é linear); Isento mantém só UT/LP. Relações preservadas da calibração anterior (÷3). #B agy.
RT_FATOR = {"Total": 1.0, "Parcial": 0.33, "Isento": 0.1}


def _physical_params(designacao, cleaned):
    """Razões físicas proj/ref que escalam horas de fabricação e serviços. 1,0 no referência.

    massa/solda/area/volume são PROXIES geométricos (limitação conhecida): massa∝D·L,
    solda≈½L+½D (longitudinal+circunferencial), area∝D·L (πDL), volume∝D²·L.
    """
    ref = reference_inputs(designacao)
    if not ref:
        return {}

    def r(campo):
        rv, v = ref.get(campo), cleaned.get(campo)
        return (float(v) / float(rv)) if (v and rv) else 1.0

    tubos = r("n_tubos")
    chicanas = r("n_chicanas")
    # divisórias de passe = nº de passes − 1 (1 passe→0, 2→1, 4→3...). Razão (N−1)/(ref−1).
    np_ref = float(ref.get("n_passes_tubos") or 2)
    np_proj = float(cleaned.get("n_passes_tubos") or np_ref)
    rasgos = max(np_proj - 1.0, 0.0) / max(np_ref - 1.0, 1.0)
    comprimento = r("comprimento_tubo_mm")   # comprimento axial do casco ∝ comprimento do tubo
    diametro = r("diametro_casco_mm")
    esp_casco_ratio = r("esp_casco_mm")       # espessura proj/ref (linear)
    esp2 = esp_casco_ratio ** 2               # #2: volume de chanfro/solda ∝ espessura²
    return {
        "tubos": tubos, "chicanas": chicanas, "comprimento": comprimento, "diametro": diametro,
        "rasgos": rasgos,
        # furação do pacote de chicanas ∝ nº tubos × nº chicanas (cada chicana furada com o
        # padrão completo de tubos) — #6 agy
        "furacao_chicana": tubos * chicanas,
        # massa cresce mais que linear com D (seção ∝ D² e a espessura cresce com D) — #2.2 agy
        "massa": diametro * diametro * comprimento,
        # soldas DE DEPOSIÇÃO escalam com comprimento/diâmetro E espessura² (volume de chanfro)
        "solda_long": comprimento * esp2,
        "solda_circ": diametro * esp2,
        # ultrassom/LP/consumíveis ∝ metro de junta × espessura (linear) — NÃO escalam com o
        # escopo de RT (#agy review12 #1).
        "solda": (0.5 * comprimento + 0.5 * diametro) * esp_casco_ratio,
        # SÓ o raio-X escala com o escopo de RT escolhido (Total/Parcial/Isento) — #B Wellington.
        "rt": (0.5 * comprimento + 0.5 * diametro) * esp_casco_ratio
        * RT_FATOR.get(cleaned.get("rt_escopo", "Total"), 1.0),
        "area": diametro * comprimento,            # superfície de pintura πDL
        "volume": diametro * diametro * comprimento,
    }


def estimate_complete(designacao: str, dims_override: dict | None = None,
                      fator_correcao_mo: float | None = None, params: dict | None = None,
                      liga_por_lado: dict | None = None, dens_por_lado: dict | None = None,
                      preco_por_lado: dict | None = None, corrosivo: str = "Tubos"):
    """Estimativa de custo/preço de um permutador completo pela designação TEMA.

    dims_override: {label_material: {dim: valor}} — dimensões reais do projeto que
    recomputam o peso geométrico (parametria de verdade, não replay do seed). Ex.:
    {"TUBOS DE TROCA TÉRMICA": {"COMPR.": 8000, "QUANTIDADE": 200}}.
    fator_correcao_mo: sobrescreve o fator de MO (default = o do TenantParamConfig).

    Retorna dict do motor (custo por seção + preço) ou None se não é custeável.
    """
    d = (designacao or "").upper()
    if d not in COSTABLE:
        return None
    from pricing_engine.permutador_quote import quote_completo
    chain = tenant_cost_chain()
    if fator_correcao_mo is not None:
        chain.fator_correcao_mo = float(fator_correcao_mo)
    return quote_completo(d, cost_chain=chain, dims_override=dims_override or None,
                          params=params or None, liga_por_lado=liga_por_lado or None,
                          dens_por_lado=dens_por_lado or None, preco_por_lado=preco_por_lado or None,
                          corrosivo=corrosivo)


def pressao_total_projeto(cleaned):
    """Pressão de projeto total (ASME VIII UG-21) = pressão informada + coluna estática do fluido.
    Altura da coluna ≈ diâmetro do casco (trocador horizontal); densidade default = água (1000)."""
    from pricing_engine.pressao_estatica import pressao_total_bar
    try:
        p = float(cleaned.get("pressao_projeto_bar") or 0)
        if not p:
            return p
        dens = float(cleaned.get("densidade_fluido_kg_m3") or 1000)   # default água
        altura_m = float(cleaned.get("diametro_casco_mm") or 0) / 1000.0
        return pressao_total_bar(p, dens, altura_m)
    except (TypeError, ValueError):
        return float(cleaned.get("pressao_projeto_bar") or 0)


def espessura_avisos(cleaned):
    """Alerta crítico de espessura do casco (A1, ASME VIII UG-27). Vazio = ok / sem pressão."""
    from pricing_engine.asme import checar_espessura_casco
    casco = cleaned.get("classe_casco", "CS")
    try:
        return checar_espessura_casco(
            casco,
            pressao_total_projeto(cleaned),        # UG-21: projeto + coluna estática
            float(cleaned.get("temperatura_projeto_c") or 40),
            cleaned.get("rt_escopo", "Total"),
            float(cleaned.get("diametro_casco_mm") or 0),
            float(cleaned.get("esp_casco_mm") or 0),
            float(cleaned.get("corrosao_mm") if cleaned.get("corrosao_mm") is not None else 3.0),
            liga=liga_para_asme(casco))        # cadastro do tenant (None → fallback hardcoded)
    except Exception:
        return []


def layout_avisos(designacao, cleaned):
    """Avisos de arranjo (feixe vs casco) — achado #4. Vazio = ok."""
    from pricing_engine.permutador_layout import check_layout
    rear = (designacao or "")[2:3]   # 3ª letra TEMA = cabeçote traseiro (BEU→U, BEM→M)
    try:
        return check_layout(int(cleaned.get("n_tubos") or 0),
                            float(cleaned.get("od_tubo_mm") or 0),
                            float(cleaned.get("diametro_casco_mm") or 0),
                            cabecote=rear)
    except Exception:
        return []


def rt_exposicoes_info(cleaned):
    """Estimativa do nº de exposições de RT do equipamento (ASME Seção V Art.2) — INFORMATIVO,
    cruza com o custo de RT calibrado. Vazio se faltam dimensões do casco."""
    from pricing_engine.rt_exposicoes import exposicoes_equipamento, FILME_UTIL_MM
    try:
        L = float(cleaned.get("comprimento_casco_mm") or 0)
        D = float(cleaned.get("diametro_casco_mm") or 0)
        if not (L and D):
            return []
        r = exposicoes_equipamento(L, D)
        return [f"ℹ️ RT estimado: ~{r['total']} exposições ({r['longitudinal']} longitudinal "
                f"+ {r['circunferencial']} circunferencial). [Seção V Art.2 — filme "
                f"útil {FILME_UTIL_MM:g}mm, validado pelo PE]"]
    except (TypeError, ValueError):
        return []


def memorial_asme(designacao, cleaned):
    """Memória de cálculo ASME estruturada (anexo de certificação): lista de verificações, cada
    uma com valores e PROCEDÊNCIA normativa. Vazio se não há pressão de projeto."""
    from pricing_engine.asme import (interp_s, tensao_admissivel, CLASSE_SPEC, procedencia,
                                      eficiencia_junta, t_min_ug27)
    try:
        p = pressao_total_projeto(cleaned)
        if not p:
            return []
        casco = cleaned.get("classe_casco", "CS")
        temp = float(cleaned.get("temperatura_projeto_c") or 40)
        D = float(cleaned.get("diametro_casco_mm") or 0)
        esp = float(cleaned.get("esp_casco_mm") or 0)
        CA = float(cleaned.get("corrosao_mm") if cleaned.get("corrosao_mm") is not None else 3.0)
        e = eficiencia_junta(cleaned.get("rt_escopo", "Total"))
        liga = liga_para_asme(casco)
        if liga:
            spec, s, fonte = liga["spec"], interp_s(liga["s_curva"], temp), liga["procedencia"]
        else:
            spec = CLASSE_SPEC.get((casco or "CS").upper())
            s, fonte = tensao_admissivel(spec, temp), procedencia(spec)
        memo = [{"item": "Pressão de projeto (UG-21)", "norma": "ASME VIII Div.1 UG-21",
                 "valor": f"{p:.2f} bar (projeto + coluna estática do fluido)"}]
        if s:
            memo.append({"item": "Tensão admissível (S)", "norma": "ASME II-D",
                         "fonte": fonte or "—", "valor": f"{s:.0f} MPa @ {temp:g}°C — {spec}"})
            t = t_min_ug27(p * 0.1, D + 2 * CA, s, e)
            if t is not None:
                treq = t + CA
                status = "CRÍTICO" if (esp and esp < treq) else "OK"
                memo.append({"item": "Espessura mínima do casco (UG-27)",
                             "norma": "ASME VIII Div.1 UG-27", "fonte": fonte or "—", "status": status,
                             "valor": f"t_mín={t:.1f}mm; t_req={treq:.1f}mm (c/ corrosão {CA:g}mm); "
                                      f"E={e:g}; informado {esp:g}mm"})
            # tampo 2:1 (UG-32)
            from pricing_engine.asme import t_min_ug32_tampo
            tt = t_min_ug32_tampo(p * 0.1, D + 2 * CA, s, e, "elipsoidal")
            if tt is not None:
                memo.append({"item": "Espessura mínima do tampo 2:1 (UG-32)",
                             "norma": "ASME VIII Div.1 UG-32", "fonte": fonte or "—",
                             "valor": f"t_mín={tt:.1f}mm; t_req={tt + CA:.1f}mm (c/ corrosão {CA:g}mm)"})
        # flange de corpo (Apêndice 2)
        from pricing_engine.flange_corpo import t_min_flange_corpo
        geo = _flange_corpo_seed(designacao)
        if geo and s:
            bore, od, esp_ref = geo
            tf = t_min_flange_corpo(p, bore, od, s)
            if tf is not None:
                st = "REFORÇAR" if tf > esp_ref else "OK"
                memo.append({"item": "Flange de corpo (Apêndice 2)",
                             "norma": "ASME VIII Div.1 Ap. 2", "status": st,
                             "valor": f"t_mín≈{tf:.0f}mm; referência do gabarito {esp_ref:g}mm "
                                      f"(gaxeta espiralada padrão m=3,0/y=69, validada PE)"})
        # radiografia por nº de exposições (Seção V Art.2)
        from pricing_engine.rt_exposicoes import exposicoes_equipamento
        L = float(cleaned.get("comprimento_casco_mm") or 0)
        if L and D:
            r = exposicoes_equipamento(L, D)
            memo.append({"item": "Radiografia — exposições (Seção V Art.2)",
                         "norma": "ASME Seção V Art.2",
                         "valor": f"~{r['total']} exposições ({r['longitudinal']} long + "
                                  f"{r['circunferencial']} circ) — estimativa"})
        return memo
    except (TypeError, ValueError):
        return []


def _flange_corpo_seed(designacao):
    """(bore, od, esp_ref) do flange de corpo 'FLANGE PRINCIPAL' do seed da designação. None se
    não houver."""
    import json
    import os
    from pricing_engine import permutador_quote as pq
    path = os.path.join(os.path.dirname(pq.__file__), "seeds",
                        f"{(designacao or '').lower()}_materiais.json")
    try:
        mats = json.load(open(path, encoding="utf-8"))["materiais"]
    except Exception:
        return None
    for m in mats:
        if "FLANGE PRINCIPAL" in (m.get("label") or "").upper():
            d = m.get("dims") or {}
            if d.get("ID") and d.get("OD") and d.get("ESP."):
                return float(d["ID"]), float(d["OD"]), float(d["ESP."])
    return None


def flange_corpo_avisos(designacao, cleaned):
    """Alerta do flange de corpo (ASME VIII Apêndice 2): se a espessura mínima exigida pela
    pressão de projeto exceder a referência do gabarito, avisa que precisa reforçar. Vazio = ok.
    Usa a tensão admissível S da metalurgia do casco (cadastro do tenant → fallback)."""
    from pricing_engine.flange_corpo import t_min_flange_corpo
    from pricing_engine.asme import interp_s, tensao_admissivel, CLASSE_SPEC
    try:
        p = pressao_total_projeto(cleaned)         # UG-21: projeto + coluna estática
        if not p:
            return []
        geo = _flange_corpo_seed(designacao)
        if not geo:
            return []
        bore, od, esp_ref = geo
        temp = float(cleaned.get("temperatura_projeto_c") or 40)
        casco = cleaned.get("classe_casco", "CS")
        liga = liga_para_asme(casco)
        s = (interp_s(liga["s_curva"], temp) if liga
             else tensao_admissivel(CLASSE_SPEC.get((casco or "CS").upper()), temp))
        if not s:
            return []
        t_req = t_min_flange_corpo(p, bore, od, s)
        if t_req and t_req > esp_ref:
            return [f"⚠️ Flange de corpo: espessura mínima estimada (ASME VIII Apêndice 2) ="
                    f" {t_req:.0f}mm > referência do gabarito {esp_ref:g}mm. Reforce o flange de"
                    f" corpo p/ esta pressão ({p:g}bar). [gaxeta espiralada padrão"
                    f" m=3,0/y=69, validada pelo PE; ajuste por caso se a gaxeta diferir]"]
        return []
    except Exception:
        return []


def estimate_from_inputs(designacao, cleaned):
    """Recomputa custo/preço do permutador a partir de inputs salvos (revisão de cotação),
    reconstruindo dims_override/params/metalurgia como o data sheet faz. None se inviável."""
    from apps.tema_templates.forms import PermutadorDataSheetForm
    form = PermutadorDataSheetForm(cleaned)
    if not form.is_valid():
        return None
    cd = form.cleaned_data
    override, fc = form.to_dims_override()
    params = _physical_params(designacao, cd)
    liga, dens, preco = _metalurgia(cd)
    return estimate_complete(designacao, dims_override=override, fator_correcao_mo=fc,
                             params=params, liga_por_lado=liga, dens_por_lado=dens,
                             preco_por_lado=preco, corrosivo=cd.get("fluido_corrosivo", "Tubos"))
