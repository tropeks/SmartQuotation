"""
Motor de custeio GENÉRICO de permutador casco-tubo completo (qualquer designação TEMA
cujo gabarito foi extraído: BEU, BEM, ...).

quote_completo(designacao, cost_chain) compõe a Estrutura Analítica:
  matéria-prima  = Σ peso_bruto(geometria) × preço/kgf   (itens de catálogo: preço fixo)
  mão-de-obra    = Σ (preço_base) × FC + ajuste            (FC = fator de correção de MO)
  serviços       = Σ preço_fixo                            (terceiros / ensaios / insumos)

A cadeia de custos do tenant (rates.TenantCostChain) sobrescreve o fator de MO e os preços
de material por (material × forma) — mesmo contrato do feixe. Sem ela, usa os defaults
ENGEMATEX embutidos nos seeds (validados ao gabarito real de cada designação).

Seeds por designação: pricing_engine/seeds/{designacao}_materiais.json + _operacoes.json.
"""
from __future__ import annotations
import json
import os

from .beu_geometry import peso_liquido_geom, perda_familia, RHO

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")


def _rho(material):
    """Densidade kgf/mm³ do material (de norma, via materials.density), default aço-carbono."""
    try:
        from .materials import density
        return density(material or "")
    except Exception:
        return RHO


def gross_up_icms(impostos_pct: float) -> float:
    """Gross-up de imposto sobre o preço de venda.

    LIMITAÇÃO/ACHADO #4: o ICMS brasileiro é 'por dentro' (fórmula legal 1/(1−alíquota)).
    O fator 0,97 aqui é uma CALIBRAÇÃO empírica que aproxima a razão venda_com/venda_sem do
    gabarito ENGEMATEX (que embute outros efeitos — PIS/COFINS, base reduzida). NÃO é uma
    fórmula fiscal pura; deve ser substituído por um motor fiscal real (regime + alíquotas
    por tributo) quando formos modelar imposto a sério.
    """
    return 1.0 / (1.0 - impostos_pct / 100.0 * 0.97)

# família geométrica → forma de matéria-prima (chave da TenantCostChain.material_price)
_FAMILIA_FORMA = {
    "tubo": "tubo", "pipe": "tubo", "chapa_retangular": "chapa",
    "disco": "chapa", "tampo_2_1": "chapa", "anel": "forjado", "flange_wn": "forjado",
}

# ── Escala de HORAS por PARÂMETRO físico (v2, refinamentos da auditoria adversarial) ──
# Cada operação escala por UM parâmetro físico (razão projeto/referência), não por grupo
# monolítico (#2). Soldas separam direção (#5): longitudinal∝comprimento, circunf∝diâmetro.
_DRIVER_PARAM = {
    "Nº TUBOS": "tubos", "Nº FUROS": "tubos", "FUROS": "tubos",
    "Nº TIRANTES": "diametro", "Nº BARRAS": "diametro",     # ∝ diâmetro do casco, não nº tubos
    "Nº CHICANAS": "chicanas",
    "ESP PACOTE": "furacao_chicana",   # #6: furação do pacote ∝ nº tubos × nº chicanas
    "Nº Soldas": "solda_circ", "Nº Cilindros": "comprimento", "COMPR. (m)": "solda_long",
}
# parcela de SETUP fixo por parâmetro (#1): horas = horas_ref × (setup + (1-setup)×razão).
# Defaults de engenharia (editáveis): furação/calandragem têm setup alto; ensaios baixo.
_SETUP_FRAC = {
    "tubos": 0.20, "chicanas": 0.20, "furacao_chicana": 0.20,
    "comprimento": 0.15, "diametro": 0.15,
    "solda": 0.10, "solda_long": 0.10, "solda_circ": 0.10,
    "massa": 0.10, "area": 0.10, "volume": 0.10,
}
# operações ADMINISTRATIVAS / de configuração — não escalam (param None → fator 1,0)
_ADMIN_KW = ("INSPEÇÃO DIMENSIONAL", "PIT", "DATA BOOK", "DATA-BOOK", "PETROBRAS",
             "FERRAMENTAS", "TRANSPORTE", "ANEL", "ANÉIS", "EXPANDIDORES", "PLACA")


def _param_da_op(o):
    """Parâmetro físico que escala uma operação (None = fixo). Une MO e serviços (#1,#2,#3,#5)."""
    lbl = (o.get("label") or "").upper()
    if any(k in lbl for k in _ADMIN_KW):
        return None
    # serviços/ensaios por palavra-chave (#3)
    if "RAIO X" in lbl or "ULTRASSOM" in lbl or "EXAME" in lbl or "L.P" in lbl or "L. P" in lbl:
        return "solda"
    if "CONSUM" in lbl:
        return "solda"
    if "TÉRMICO" in lbl or "CALANDRAR" in lbl:
        return "massa"
    if "HIDROST" in lbl:
        return "volume"
    if "PINTURA" in lbl or "JATEAMENTO" in lbl:
        return "area"
    # soldas do casco por direção (#5) com espessura² embutida no param (#2)
    if "LONGITUDINA" in lbl:
        return "solda_long"
    if "CIRCUNFER" in lbl:
        return "solda_circ"
    return _DRIVER_PARAM.get(o.get("driver"))


def _escala_op(o, params):
    """Fator efetivo de horas da op: setup + (1-setup)×razão_do_parâmetro. 1,0 no referência."""
    p = _param_da_op(o)
    if not p:
        return 1.0
    razao = float((params or {}).get(p, 1.0))
    setup = _SETUP_FRAC.get(p, 0.15)
    return setup + (1.0 - setup) * razao


# parâmetro físico → LADO do equipamento, p/ metalurgia por componente (#agy: bimetálico).
_PARAM_LADO = {
    "tubos": "feixe", "chicanas": "feixe", "furacao_chicana": "feixe",
    "comprimento": "casco", "diametro": "casco", "solda_long": "casco",
    "solda_circ": "casco", "solda": "casco", "massa": "casco", "area": "casco", "volume": "casco",
}


# peças do FEIXE cujo param de escala é 'diametro' (escalam com Ø do casco) mas a
# metalurgia é do lado do FEIXE: tirantes, barras de selagem, curvas dos tubos-U (#agy 1.A).
_FEIXE_LABEL_KW = ("TIRANTE", "BARRA", "CURVA", "TUBOS U", "MANDRIL")


def _lado_da_op(o):
    """Lado (feixe|casco) de uma operação — define qual liga aplicar. None = sem liga."""
    lbl = (o.get("label") or "").upper()
    if any(k in lbl for k in _FEIXE_LABEL_KW):
        return "feixe"
    return _PARAM_LADO.get(_param_da_op(o))


def _lado_do_material(secao):
    """Lado de um material pela seção do seed (feixe_material→feixe; casco/cabecote→casco)."""
    return "feixe" if (secao or "").startswith("feixe") else "casco"


def _load(nome):
    with open(os.path.join(_SEEDS, nome), encoding="utf-8") as f:
        return json.load(f)


def _norm_mat(material):
    return (material or "").strip().upper()


def designacoes_disponiveis():
    """Designações com seeds de custeio presentes (ex.: ['BEM', 'BEU'])."""
    achadas = set()
    for fn in os.listdir(_SEEDS):
        if fn.endswith("_materiais.json"):
            achadas.add(fn[:-len("_materiais.json")].upper())
    return sorted(achadas)


def quote_completo(designacao: str = "BEU", cost_chain=None, fator_correcao_mo: float = 1.0,
                   fator_preco: float = 1.25, impostos_pct: float = 9.0,
                   dims_override: dict | None = None, params: dict | None = None,
                   liga_por_lado: dict | None = None, dens_por_lado: dict | None = None,
                   preco_por_lado: dict | None = None) -> dict:
    """params: {parâmetro: razão proj/ref} p/ escalar as HORAS de fabricação E serviços por
    DRIVER físico (tubos, chicanas, comprimento, diametro, solda, massa, area, volume), com
    parcela de setup fixo. Razão 1,0 = caso de referência → reconcilia 0,0%. Operações
    administrativas/config (nº de bocais/flanges, data book, transporte) não escalam.
    Aproximações geométricas (massa/solda/area/volume) e setup fractions são calibrações
    de engenharia documentadas — limitações conhecidas (ver auditoria adversarial).

    liga_por_lado/dens_por_lado: {lado: fator} — metalurgia POR LADO (feixe|casco) p/
    construção bimetálica. liga multiplica as HORAS de MO do lado; dens multiplica o PESO
    do material do lado (níquel mais pesado). Tudo 1,0 (aço-carbono) → reconcilia 0,0%."""
    liga_lado = liga_por_lado or {}
    dens_lado = dens_por_lado or {}
    preco_lado = preco_por_lado or {}
    d = designacao.lower()
    mats = _load(f"{d}_materiais.json")["materiais"]
    ops = _load(f"{d}_operacoes.json")["operacoes"]

    fc = fator_correcao_mo
    if cost_chain is not None and getattr(cost_chain, "fator_correcao_mo", None):
        fc = float(cost_chain.fator_correcao_mo)

    def preco_kgf(material, familia, default):
        if cost_chain is None:
            return default
        fn = getattr(cost_chain, "price_kgf", None)
        if callable(fn):
            try:
                return float(fn(_norm_mat(material), _FAMILIA_FORMA.get(familia, "chapa")))
            except Exception:
                pass
        return default

    secoes = {}
    custo_material = 0.0
    for m in mats:
        lado_mat = _lado_do_material(m["secao"])
        pf = float(preco_lado.get(lado_mat, 1.0))    # fator de preço/kg por liga do lado (#agy 1.C)
        if m.get("familia") == "catalogo" or not m.get("peso_bruto"):
            custo = m["preco"] * pf                  # item de catálogo (preço fixo) × liga
        else:
            peso_bruto = m["peso_bruto"]
            if dims_override and m["label"] in dims_override:
                dims = {**m.get("dims", {}), **dims_override[m["label"]]}
                liq = peso_liquido_geom(m["familia"], dims, rho=_rho(m.get("material")))
                if liq is not None:
                    qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
                    # perda real do seed se houver; senão a típica da família (#agy scrap)
                    perda = ((m["peso_bruto"] / m["peso_liq"]) if m.get("peso_liq")
                             else perda_familia(m["familia"]))
                    peso_bruto = liq * qtd * perda
            # densidade por liga do LADO do material (níquel mais pesado que aço-carbono)
            peso_bruto *= float(dens_lado.get(lado_mat, 1.0))
            # preço/kg da liga do lado (inox/níquel custam várias vezes o aço-carbono) — #agy 1.C
            custo = peso_bruto * preco_kgf(m.get("material"), m["familia"], m["price_kgf"]) * pf
        custo_material += custo
        secoes[m["secao"]] = secoes.get(m["secao"], 0.0) + custo

    custo_mo = custo_servico = 0.0
    custo_por_param = {}
    for o in ops:
        eff = _escala_op(o, params)                    # setup + (1-setup)×razão (1,0 no ref)
        pnome = _param_da_op(o) or "fixo"
        # fator de liga metalúrgica POR LADO (#3 + bimetálico): MO e serviços de solda do lado
        lado = _lado_da_op(o)
        liga = float(liga_lado.get(lado, 1.0)) if lado else 1.0
        if o["tipo"] == "mao_obra":
            ajuste = o.get("ajuste", 0.0)
            base = o["preco_gabarito"] - ajuste        # parcela de MO (R$ a FC=1, ref)
            c = base * eff * liga * fc + ajuste
            custo_mo += c
        else:
            c = o["preco_gabarito"] * eff * liga       # serviço: escala se tiver driver físico
            custo_servico += c
        custo_por_param[pnome] = round(custo_por_param.get(pnome, 0.0) + c, 2)
        secoes[o["secao"]] = secoes.get(o["secao"], 0.0) + c

    custo_total = custo_material + custo_mo + custo_servico
    # formação de preço ENGEMATEX: custo × F.C. = venda COM impostos; venda SEM impostos
    # por dedução do gross-up de imposto (ver gross_up_icms — calibração, não fórmula fiscal).
    preco_com_impostos = custo_total * fator_preco
    preco_sem_impostos = preco_com_impostos / gross_up_icms(impostos_pct)

    return {
        "designacao_tema": designacao.upper(),
        "custo_material": round(custo_material, 2),
        "custo_mao_obra": round(custo_mo, 2),
        "custo_por_param": custo_por_param,
        "custo_servicos": round(custo_servico, 2),
        "custo_total": round(custo_total, 2),
        "por_secao": {k: round(v, 2) for k, v in secoes.items()},
        "fator_correcao_mo": fc,
        "liga_por_lado": {k: round(v, 3) for k, v in liga_lado.items()} or {"feixe": 1.0, "casco": 1.0},
        "fator_preco": fator_preco,
        "impostos_pct": impostos_pct,
        "preco_com_impostos": round(preco_com_impostos, 2),
        "preco_sem_impostos": round(preco_sem_impostos, 2),
        "n_materiais": len(mats),
        "n_operacoes": len(ops),
    }
