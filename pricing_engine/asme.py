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
    # PROVISÓRIO (pesquisa web ASME II-D, NÃO confirmado pelo Wellington) — duplex 2205:
    "SA-240 S32205": {38: 206.8, 93: 177.2, 149: 171.0, 204: 164.8, 260: 160.7, 316: 159.3},
}

# specs cuja tensão admissível é PROVISÓRIA (web, pendente de confirmação da engenharia).
S_PROVISORIO = {"SA-240 S32205"}

# classe metalúrgica do app → especificação representativa para lookup de S (chapa de casco).
# NÍQUEL ainda sem S (aguardando tabela do Wellington) → não verifica espessura.
CLASSE_SPEC = {"CS": "SA-516 GR 70", "INOX": "SA-240 304",
               "DUPLEX": "SA-240 S32205", "NIQUEL": None}

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
    """Espessura mínima do casco cilíndrico sob pressão interna (ASME VIII Div.1 UG-27):
        t = P·R / (S·E − 0,6·P)   [R = raio interno]. Devolve None se o denominador ≤ 0
        (pressão alta demais p/ o material → exige análise especial)."""
    r = d_interno_mm / 2.0
    den = s_mpa * e - 0.6 * pressao_mpa
    if den <= 0:
        return None
    return pressao_mpa * r / den


def checar_espessura_casco(classe_casco: str, pressao_bar: float, temp_c: float,
                           rt_escopo: str, d_casco_mm: float, esp_casco_mm: float,
                           corrosao_mm: float = 3.0) -> list[str]:
    """Avisos de espessura do casco (UG-27). Vazio = ok. NÃO bloqueia — alerta crítico.
    corrosao_mm: sobrespessura de corrosão (CA) — t_requerida = t_UG27 + CA (#agy review13)."""
    avisos = []
    if not (pressao_bar and d_casco_mm and esp_casco_mm):
        return avisos
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
    prov = " [S PROVISÓRIO — confirmar c/ engenharia]" if spec in S_PROVISORIO else ""
    t_req = t_ug27 + corrosao_mm               # espessura nominal = calculada + sobremetal
    if esp_casco_mm < t_req:
        avisos.append(f"⛔ CRÍTICO: espessura do casco {esp_casco_mm:g}mm é MENOR que o "
                      f"mínimo ASME VIII UG-27 = {t_req:.1f}mm "
                      f"(= {t_ug27:.1f} + {corrosao_mm:g} de corrosão; P={pressao_bar:g}bar, "
                      f"{spec}, S={s:.0f}MPa, E={e:g}, T={temp_c:g}°C). Equipamento reprova "
                      f"no teste hidrostático. Aumente a espessura.{prov}")
    elif spec in S_PROVISORIO:
        avisos.append(f"ℹ️ Espessura ok p/ {spec}, mas a tensão admissível (S={s:.0f}MPa) é "
                      f"PROVISÓRIA (pesquisa, não confirmada) — validar com a engenharia.")
    return avisos
