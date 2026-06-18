"""
ASME BPVC Seção VIII Div. 1 — espessura mínima do casco (UG-27) + tensão admissível (S).

Tabela S validada fornecida pelo Wellington (ASME Sec. II Part D, Tabelas 1A/1B), em MPa.
Aço-carbono: S constante até ~343°C. Inox austenítico: S cai com a temperatura → interpola.

A1 (Wellington): o motor calcula a espessura mínima do casco em background; se a espessura
informada for menor que a exigida pela norma, emite ALERTA CRÍTICO. Espelho (UHX) fica manual.
"""
from __future__ import annotations

# tensão admissível S (MPa) por especificação × temperatura (°C). CS: platô até ~250°C, cai
# depois (não é platô até 343 — ASME II-D 2025). Specs em CLASSE_SPEC (ativos) rebaseados 2025.
import json
import os
from pathlib import Path

_DB_PATH = Path(__file__).parent / "seeds" / "asme_materials_2025.json"
ASME_DB = []
if _DB_PATH.exists():
    with open(_DB_PATH, "r", encoding="utf-8") as f:
        ASME_DB = json.load(f).get("data", [])

TENSAO_ADMISSIVEL_MPA = {}
S_PROCEDENCIA = {}

_SPEC_MAPPING = {
    "SA-516 GR 70": {"spec_no": "SA-516", "grade": "70"},
    "SA-516 GR 60": {"spec_no": "SA-516", "grade": "60"},
    "SA-106 GR B": {"spec_no": "SA-106", "grade": "B"},
    "SA-105": {"spec_no": "SA-105", "grade": ""},
    "SA-240 304": {"spec_no": "SA-240", "grade": "304", "line_no": "3"},
    # inox dormentes: pinar a linha CONSERVADORA (o DB tem 2 linhas, a alta = deformação
    # ligeiramente maior aceitável; usamos a conservadora, igual ao SA-240 304 L3).
    "SA-240 304L": {"spec_no": "SA-240", "grade": "304L", "line_no": "1"},
    "SA-240 316": {"spec_no": "SA-240", "grade": "316", "line_no": "12"},
    "SA-240 316L": {"spec_no": "SA-240", "grade": "316L", "line_no": "26"},
    "SA-213 304L": {"spec_no": "SA-213", "grade": "TP304L"},
    "SA-249 316L": {"spec_no": "SA-249", "grade": "TP316L", "line_no": "28"},
    "SA-240 S31803": {"spec_no": "SA-240", "uns_no": "S31803"},
    "SA-240 S32205": {"spec_no": "SA-240", "uns_no": "S32205"},
    "SB-443 N06625": {"spec_no": "SB-443", "grade": "1", "line_no": "22"},
    "SB-127 N04400": {"spec_no": "SB-127", "condition": "Annealed", "line_no": "10"},
}

for mat_name, f_args in _SPEC_MAPPING.items():
    for r in ASME_DB:
        if r.get("audit_info", {}).get("extraction_status") != "OK": continue
        match = True
        if "spec_no" in f_args and r["spec_no"].replace("–", "-") != f_args["spec_no"]: match = False
        if "grade" in f_args and r["grade"] != f_args["grade"]: match = False
        if "uns_no" in f_args and r.get("uns_no") != f_args["uns_no"]: match = False
        if "line_no" in f_args and str(r["line_no"]) != f_args["line_no"]: match = False
        if "condition" in f_args and f_args["condition"].lower() not in r.get("condition", "").lower(): match = False
            
        if match:
            TENSAO_ADMISSIVEL_MPA[mat_name] = {float(k): float(v) for k, v in r["allowable_stress_MPa"].items()}
            S_PROCEDENCIA[mat_name] = {
                "norma": "ASME BPVC II-D (M)",
                "edicao": "2025",
                "tabela": r["table"].replace("Table ", ""),
                "linha": str(r["line_no"])
            }
            break


def procedencia(spec: str) -> str | None:
    """Citação curta da fonte normativa do S (p/ memória de cálculo / certificação). None se
    a procedência ainda não foi registrada para a spec."""
    p = S_PROCEDENCIA.get((spec or "").strip().upper())
    if not p:
        return None
    ln = f" L{p['linha']}" if p.get("linha") else ""
    return f"{p['norma']} {p['edicao']}, Tab {p['tabela']}{ln}"

# classe metalúrgica do app → especificação representativa para lookup de S (chapa de casco).
# INCONEL (Ni-Cr-Mo) e MONEL (Ni-Cu) são classes distintas (#2 Wellington); NIQUEL fica como
# ALIAS de compatibilidade p/ cotações antigas (= Inconel, a liga de níquel mais comum aqui).
CLASSE_SPEC = {"CS": "SA-516 GR 70", "INOX": "SA-240 304",
               "DUPLEX": "SA-240 S31803",
               "INCONEL": "SB-443 N06625", "MONEL": "SB-127 N04400",
               "NIQUEL": "SB-443 N06625"}

# eficiência de junta E por escopo de radiografia (Wellington, ASME UW-12).
E_POR_RT = {"Total": 1.00, "Parcial": 0.85, "Isento": 0.70}

# temperatura limite de projeto (°C) p/ aviso de fluência/análise sênior.
TEMP_LIMITE = {"CS": 370, "INOX": 425, "DUPLEX": 425,
               "INCONEL": 540, "MONEL": 480, "NIQUEL": 540}


def interp_s(curva: dict, temp_c: float) -> float | None:
    """S (MPa) interpolado linearmente numa curva {temp_c: S}. Acima da maior temperatura da
    curva → None (S despenca; extrapolar seria INSEGURO). Curva vazia → None."""
    if not curva:
        return None
    temps = sorted(curva)
    if temp_c <= temps[0]:
        return curva[temps[0]]
    if temp_c > temps[-1]:
        return None
    if temp_c == temps[-1]:
        return curva[temps[-1]]
    for i in range(len(temps) - 1):           # interpolação entre as duas linhas vizinhas
        t0, t1 = temps[i], temps[i + 1]
        if t0 <= temp_c <= t1:
            s0, s1 = curva[t0], curva[t1]
            return s0 - (s0 - s1) * (temp_c - t0) / (t1 - t0)
    return None


def tensao_admissivel(spec: str, temp_c: float) -> float | None:
    """S (MPa) do material na temperatura (tabela hardcoded — fallback do cadastro de ligas)."""
    return interp_s(TENSAO_ADMISSIVEL_MPA.get((spec or "").strip().upper()), temp_c)


def eficiencia_junta(rt_escopo: str) -> float:
    return E_POR_RT.get(rt_escopo, 0.85)


def t_min_ug27(pressao_mpa: float, d_interno_mm: float, s_mpa: float, e: float) -> float | None:
    """Espessura mínima do casco cilíndrico sob pressão interna (ASME VIII Div.1 UG-27).
    Retorna a MAIOR entre a tensão circunferencial e a longitudinal (a norma exige checar
    ambas — Rom/agy). Circunferencial governa no caso usual; a longitudinal entra com E
    baixo de junta circunferencial."""
    r = d_interno_mm / 2.0
    # circunferencial UG-27(c)(1): t = P·R / (S·E − 0,6·P)
    den_c = s_mpa * e - 0.6 * pressao_mpa
    if den_c <= 0:
        return None
    t_circ = pressao_mpa * r / den_c
    # longitudinal UG-27(c)(2): t = P·R / (2·S·E + 0,4·P)
    t_long = pressao_mpa * r / (2.0 * s_mpa * e + 0.4 * pressao_mpa)
    return max(t_circ, t_long)


def t_min_ug32_tampo(pressao_mpa: float, d_interno_mm: float, s_mpa: float, e: float,
                     tipo: str = "elipsoidal") -> float | None:
    """Espessura mínima de tampo sob pressão interna (ASME VIII Div.1 UG-32). Fórmulas (Rom):
    elipsoidal 2:1  t = P·D/(2·S·E − 0,2·P) ; hemisférico  t = P·L/(2·S·E − 0,2·P), L=R."""
    den = 2.0 * s_mpa * e - 0.2 * pressao_mpa
    if den <= 0:
        return None
    d_ou_l = d_interno_mm if tipo != "hemisferico" else d_interno_mm / 2.0
    return pressao_mpa * d_ou_l / den


def checar_espessura_casco(classe_casco: str, pressao_bar: float, temp_c: float,
                           rt_escopo: str, d_casco_mm: float, esp_casco_mm: float,
                           corrosao_mm: float = 3.0, esp_tampo_mm: float = None,
                           liga: dict = None) -> list[str]:
    """Avisos de espessura do casco (UG-27). Vazio = ok. NÃO bloqueia — alerta crítico.
    corrosao_mm: sobrespessura de corrosão (CA) — t_requerida = t_UG27 + CA (#agy review13).
    liga: dict opcional do CADASTRO de ligas do tenant {spec, s_curva(°C→MPa float), temp_limite,
    procedencia}. Se omitido, usa os dicts hardcoded por classe (fallback)."""
    avisos = []
    if not (pressao_bar and d_casco_mm and esp_casco_mm):
        return avisos
    if not esp_tampo_mm:
        esp_tampo_mm = esp_casco_mm        # padrão ENGEMATEX: tampo na espessura do casco
    # resolve a liga: do cadastro do tenant (liga injetada) OU dos dicts hardcoded (fallback)
    if liga:
        spec = liga.get("spec") or (classe_casco or "CS")
        lim = liga.get("temp_limite") or 370
        proc = liga.get("procedencia")
        s = interp_s(liga.get("s_curva") or {}, temp_c or 40)
    else:
        spec = CLASSE_SPEC.get((classe_casco or "CS").upper())
        if not spec:
            avisos.append(f"Tensão admissível (S) indisponível p/ a liga do casco "
                          f"({classe_casco}) — espessura mínima NÃO verificada (validar manual).")
            return avisos
        lim = TEMP_LIMITE.get((classe_casco or "CS").upper(), 370)
        proc = procedencia(spec)
        s = tensao_admissivel(spec, temp_c or 40)
    if temp_c and temp_c > lim:
        avisos.append(f"Temperatura de projeto {temp_c:g}°C acima do limite {lim}°C p/ "
                      f"{classe_casco} — exige análise de engenharia sênior (fluência).")
    if s is None:
        avisos.append(f"Tensão admissível (S) indisponível p/ {spec} a {temp_c:g}°C "
                      f"(acima da tabela) — espessura mínima NÃO verificada.")
        return avisos
    e = eficiencia_junta(rt_escopo)
    p_mpa = pressao_bar * 0.1                  # 1 bar = 0,1 MPa
    # condição corroída: raio interno + CA (a corrosão consome metal por dentro)
    t_ug27 = t_min_ug27(p_mpa, d_casco_mm + 2 * corrosao_mm, s, e)
    if t_ug27 is None:
        avisos.append(f"Pressão {pressao_bar:g} bar alta demais p/ {spec} a {temp_c:g}°C "
                      f"(S·E ≤ 0,6·P) — exige material/espessura especial.")
        return avisos
    fonte = f" [fonte S: {proc}]" if proc else ""
    t_req = t_ug27 + corrosao_mm               # espessura nominal = calculada + sobremetal
    if esp_casco_mm < t_req:
        avisos.append(f"⛔ CRÍTICO: espessura do casco {esp_casco_mm:g}mm é MENOR que o "
                      f"mínimo ASME VIII UG-27 = {t_req:.1f}mm "
                      f"(= {t_ug27:.1f} + {corrosao_mm:g} de corrosão; P={pressao_bar:g}bar, "
                      f"{spec}, S={s:.0f}MPa, E={e:g}, T={temp_c:g}°C). Equipamento reprova "
                      f"no teste hidrostático. Aumente a espessura.{fonte}")
    # tampo 2:1 (UG-32): a espessura do tampo (≈ do casco no padrão ENGEMATEX) deve cobrir
    # o mínimo do tampo E não ser menor que a do casco (Rom). Para 2:1 o tampo pede menos
    # que o casco, então só alerta em casos atípicos (ex.: tampo informado mais fino).
    t_tampo = t_min_ug32_tampo(p_mpa, d_casco_mm + 2 * corrosao_mm, s, e, "elipsoidal")
    if t_tampo is not None:
        t_tampo_req = t_tampo + corrosao_mm
        if esp_tampo_mm and esp_tampo_mm < t_tampo_req:
            avisos.append(f"⛔ CRÍTICO: espessura do tampo 2:1 {esp_tampo_mm:g}mm < mínimo "
                          f"ASME VIII UG-32 = {t_tampo_req:.1f}mm. Aumente a espessura do tampo.{fonte}")
    return avisos
