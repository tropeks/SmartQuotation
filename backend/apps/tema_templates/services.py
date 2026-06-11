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
LIGA_FATOR = {
    "CS": 1.0, "INOX": 1.4, "DUPLEX": 1.7, "NIQUEL": 2.3,
}
# densidade por classe (kgf/mm³) p/ ajuste de peso do material (níquel ~12% mais pesado).
CLASSE_DENSIDADE = {
    "CS": 7.85e-6, "INOX": 7.93e-6, "DUPLEX": 7.80e-6, "NIQUEL": 8.80e-6,
}
# fator de PREÇO/kg da matéria-prima por classe vs aço-carbono (#agy 1.C — material é ~70%
# do custo de liga nobre). Multiplicadores típicos de mercado, EDITÁVEIS — não cotados.
PRECO_FATOR = {
    "CS": 1.0, "INOX": 4.5, "DUPLEX": 6.0, "NIQUEL": 12.0,
}
LIGA_CHOICES = [("CS", "Aço Carbono"), ("INOX", "Aço Inox (300/400)"),
                ("DUPLEX", "Duplex / Superduplex"), ("NIQUEL", "Liga de Níquel (Inconel…)")]


def _metalurgia(cleaned):
    """(liga_por_lado, dens_por_lado, preco_por_lado) das classes feixe/casco. CS → 1,0.
    liga escala MO; dens escala peso; preço escala R$/kg da matéria-prima (#agy 1.C)."""
    cf = cleaned.get("classe_feixe", "CS")
    cc = cleaned.get("classe_casco", "CS")
    # base = densidade do aço-carbono: os pesos do seed BEU/BEM foram extraídos em CS, então a
    # razão classe/CS é correta. (Se um dia houver seed nativo em liga, derivar a base do seed.)
    base = CLASSE_DENSIDADE["CS"]
    liga = {"feixe": LIGA_FATOR.get(cf, 1.0), "casco": LIGA_FATOR.get(cc, 1.0)}
    dens = {"feixe": CLASSE_DENSIDADE.get(cf, base) / base,
            "casco": CLASSE_DENSIDADE.get(cc, base) / base}
    preco = {"feixe": PRECO_FATOR.get(cf, 1.0), "casco": PRECO_FATOR.get(cc, 1.0)}
    return liga, dens, preco


def tenant_cost_chain():
    """Monta a TenantCostChain do tenant (preços de material cifrados + fator de MO),
    reaproveitando o mesmo padrão do adapter de cotações. Sem dados → None (usa defaults)."""
    from pricing_engine.rates import TenantCostChain
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
        from apps.engineering_params.models import TenantParamConfig
        chain.fator_correcao_mo = float(TenantParamConfig.get_solo().fator_correcao_mo)
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


# escopo de radiografia → multiplicador dos ensaios de solda (param 'solda'). Referência do
# gabarito = Parcial (10%) → 1,0. Total (100%) ~3× a metragem; Isento mantém só UT/LP. #B agy.
RT_FATOR = {"Total": 3.0, "Parcial": 1.0, "Isento": 0.3}


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
        * RT_FATOR.get(cleaned.get("rt_escopo", "Parcial"), 1.0),
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
