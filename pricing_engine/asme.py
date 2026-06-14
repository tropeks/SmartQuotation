"""
ASME BPVC Seção VIII Div. 1 — espessura mínima do casco (UG-27) + tensão admissível (S).

Tabela S validada fornecida pelo Wellington (ASME Sec. II Part D, Tabelas 1A/1B), em MPa.
Aço-carbono: S constante até ~343°C. Inox austenítico: S cai com a temperatura → interpola.

A1 (Wellington): o motor calcula a espessura mínima do casco em background; se a espessura
informada for menor que a exigida pela norma, emite ALERTA CRÍTICO. Espelho (UHX) fica manual.
"""
from __future__ import annotations

# tensão admissível S (MPa) por especificação × temperatura (°C). CS: platô até 343°C.
TENSAO_ADMISSIVEL_MPA = {
    "SA-516 GR 70": {40: 138, 343: 138},
    "SA-516 GR 60": {40: 118, 343: 118},
    "SA-106 GR B": {40: 118, 343: 118},
    "SA-105":      {40: 138, 343: 138},
    "SA-240 304":  {40: 138, 65: 129, 100: 115, 150: 103, 200: 94.5, 250: 88.3, 300: 83.4},
    "SA-240 304L": {40: 115, 65: 108, 100: 98.6, 150: 89.6, 200: 81.4, 250: 75.8, 300: 71.0},
    "SA-240 316":  {40: 138, 65: 134, 100: 122, 150: 110, 200: 100, 250: 92.4, 300: 86.2},
    "SA-240 316L": {40: 115, 65: 110, 100: 101, 150: 91.7, 200: 83.4, 250: 77.2, 300: 72.4},
    "SA-213 304L": {40: 115, 65: 108, 100: 98.6, 150: 89.6, 200: 81.4, 250: 75.8, 300: 71.0},
    "SA-249 316L": {40: 97.7, 65: 93.5, 100: 85.8, 150: 77.9, 200: 70.8, 250: 65.6, 300: 61.5},
    # === Ligas especiais: extraídas da ASME BPVC II-D MÉTRICA 2025 (edição LICENCIADA fornecida
    # pelo Wellington). Valores oficiais por temperatura métrica nativa; procedência (norma/
    # edição/tabela/linha) em S_PROCEDENCIA p/ rastreabilidade de certificação ASME. ===
    # Duplex 2205 S31803 (SA-240, Tab 1A L12) — DEFAULT da classe DUPLEX (S menor = conservador):
    "SA-240 S31803": {40: 177, 65: 177, 100: 177, 150: 171, 200: 165, 250: 161, 300: 160},
    # Duplex 2205 S32205 (SA-240, Tab 1A L21) — usar só se o MTR confirmar a UNS (S maior):
    "SA-240 S32205": {40: 187, 65: 187, 100: 187, 150: 180, 200: 174, 250: 170, 300: 168},
    # Inconel 625 (SB-443 N06625, Tab 1B L22) GRADE 1 recozido — chapa p/ vaso em temps usuais
    # (Grade 2 sol. ann. = 184 MPa, p/ alta temp). Liga Ni-Cr-Mo:
    "SB-443 N06625": {40: 217, 65: 217, 100: 217, 150: 217, 200: 217, 250: 217, 300: 205},
    # Monel 400 (SB-127 N04400, Tab 1B L10, recozido). Liga Ni-Cu, DISTINTA do Inconel:
    "SB-127 N04400": {40: 129, 65: 121, 100: 112, 150: 105, 200: 101, 250: 101, 300: 101},
}

# procedência normativa de cada valor de S — rastreabilidade exigida p/ certificação ASME
# (norma + edição + tabela + linha). Specs sem entrada = pendentes de rebase à edição licenciada
# (CS/inox vieram da tabela do Wellington, edição a confirmar na Fase B do rebase 2025).
S_PROCEDENCIA = {
    "SA-240 S31803": {"norma": "ASME BPVC II-D (M)", "edicao": "2025", "tabela": "1A", "linha": "12"},
    "SA-240 S32205": {"norma": "ASME BPVC II-D (M)", "edicao": "2025", "tabela": "1A", "linha": "21"},
    "SB-443 N06625": {"norma": "ASME BPVC II-D (M)", "edicao": "2025", "tabela": "1B", "linha": "22"},
    "SB-127 N04400": {"norma": "ASME BPVC II-D (M)", "edicao": "2025", "tabela": "1B", "linha": "10"},
}


def procedencia(spec: str) -> str | None:
    """Citação curta da fonte normativa do S (p/ memória de cálculo / certificação). None se
    a procedência ainda não foi registrada para a spec."""
    p = S_PROCEDENCIA.get((spec or "").strip().upper())
    if not p:
        return None
    ln = f" L{p['linha']}" if p.get("linha") else ""
    return f"{p['norma']} {p['edicao']}, Tab {p['tabela']}{ln}"

# classe metalúrgica do app → especificação representativa para lookup de S (chapa de casco).
CLASSE_SPEC = {"CS": "SA-516 GR 70", "INOX": "SA-240 304",
               "DUPLEX": "SA-240 S31803", "NIQUEL": "SB-443 N06625"}

# eficiência de junta E por escopo de radiografia (Wellington, ASME UW-12).
E_POR_RT = {"Total": 1.00, "Parcial": 0.85, "Isento": 0.70}

# temperatura limite de projeto (°C) p/ aviso de fluência/análise sênior.
TEMP_LIMITE = {"CS": 370, "INOX": 425, "DUPLEX": 425, "NIQUEL": 540}


def tensao_admissivel(spec: str, temp_c: float) -> float | None:
    """S (MPa) do material na temperatura, interpolando linearmente entre as linhas da tabela."""
    tab = TENSAO_ADMISSIVEL_MPA.get((spec or "").strip().upper())
    if not tab:
        return None
    temps = sorted(tab)
    if temp_c <= temps[0]:
        return tab[temps[0]]
    if temp_c > temps[-1]:
        return None   # acima da tabela: S NÃO é platô (despenca) — extrapolar seria INSEGURO
    if temp_c == temps[-1]:
        return tab[temps[-1]]
    for i in range(len(temps) - 1):           # interpolação entre as duas linhas vizinhas
        t0, t1 = temps[i], temps[i + 1]
        if t0 <= temp_c <= t1:
            s0, s1 = tab[t0], tab[t1]
            return s0 - (s0 - s1) * (temp_c - t0) / (t1 - t0)
    return None


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
                           corrosao_mm: float = 3.0, esp_tampo_mm: float = None) -> list[str]:
    """Avisos de espessura do casco (UG-27). Vazio = ok. NÃO bloqueia — alerta crítico.
    corrosao_mm: sobrespessura de corrosão (CA) — t_requerida = t_UG27 + CA (#agy review13)."""
    avisos = []
    if not (pressao_bar and d_casco_mm and esp_casco_mm):
        return avisos
    if not esp_tampo_mm:
        esp_tampo_mm = esp_casco_mm        # padrão ENGEMATEX: tampo na espessura do casco
    spec = CLASSE_SPEC.get((classe_casco or "CS").upper())
    if not spec:
        avisos.append(f"Tensão admissível (S) indisponível p/ a liga do casco "
                      f"({classe_casco}) — espessura mínima NÃO verificada (validar manual).")
        return avisos
    lim = TEMP_LIMITE.get((classe_casco or "CS").upper(), 370)
    if temp_c and temp_c > lim:
        avisos.append(f"Temperatura de projeto {temp_c:g}°C acima do limite {lim}°C p/ "
                      f"{classe_casco} — exige análise de engenharia sênior (fluência).")
    s = tensao_admissivel(spec, temp_c or 40)
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
    proc = procedencia(spec)
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
