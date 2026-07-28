"""
Horas de solda por primeiros princípios — régua INDEPENDENTE do histórico.

Por que existe
--------------
O motor custeia solda por proxy (∝ espessura², calibrado contra o orçamento fechado da
empresa). Isso reproduz o que a empresa cobraria — mas o preço dela vem de benchmark, e
segundo o próprio PE "a parte de mão de obra não vai estar ok". Calibrar contra ele
mede fidelidade, não verdade.

Este módulo calcula a hora de solda a partir da física, sem olhar histórico nenhum:

    volume da junta × densidade      = massa de metal depositado
    massa ÷ taxa de deposição        = TEMPO DE ARCO
    tempo de arco ÷ fator de operação = TEMPO REAL de trabalho

O fator de operação é o que a intuição erra: o soldador não solda o dia inteiro. Ele
posiciona peça, troca eletrodo, esmerilha, espera ponte rolante, faz inspeção visual.
Em processo manual, a literatura trabalha na faixa de 20–40% de arco aberto — ou seja,
**o tempo de arco é cerca de um terço do custo real**. Um orçamento que estime pelo arco
subestima a solda em 3×.

O que este módulo NÃO é
-----------------------
Não substitui o custeio. É régua paralela de diagnóstico: serve para comparar com o que
o orçamento estimou e mostrar a distância. Trocar a fórmula de custeio mudaria todos os
números e quebraria o gate de 0,0% — e a decisão de adotar é do dono da margem.

Números de partida: são REFERENCIAIS de literatura, não medições da fábrica. A empresa
mede o seu fator de operação e substitui — e medir isso já é, por si, um diagnóstico.

Módulo puro: sem Django, sem banco.
"""
from dataclasses import dataclass
from math import pi, tan, radians

# Densidade do aço depositado (kg/mm³). Metal de adição de aço carbono/inox varia pouco
# nesta casa; usar a densidade do próprio material não move o resultado de forma útil.
DENSIDADE_ACO_KG_MM3 = 7.85e-6

# Taxa de deposição por processo (kg/h de metal EFETIVAMENTE depositado, a 100% de arco).
# Faixas usuais de literatura; a empresa ajusta com os parâmetros que pratica.
TAXA_DEPOSICAO_KG_H = {
    "smaw": 1.6,      # eletrodo revestido
    "gmaw": 3.5,      # MIG/MAG
    "fcaw": 4.5,      # arame tubular
    "gtaw": 0.6,      # TIG — lento, usado em passe de raiz e inox fino
    "saw": 9.0,       # arco submerso — alta deposição, só posição plana
}

# Fração do turno com arco aberto. É o número que separa "tempo de arco" de "tempo real".
# Manual costuma ficar em 20–40%; automatizado sobe bastante.
FATOR_OPERACAO = {
    "smaw": 0.25,
    "gmaw": 0.35,
    "fcaw": 0.35,
    "gtaw": 0.20,
    "saw": 0.55,
}

# Eficiência de deposição: quanto do consumível vira cordão (o resto é respingo, ponta
# de eletrodo, escória). Entra no CONSUMO de material, não no tempo de arco.
EFICIENCIA_DEPOSICAO = {
    "smaw": 0.65,
    "gmaw": 0.90,
    "fcaw": 0.85,
    "gtaw": 0.95,
    "saw": 0.98,
}

PROCESSOS = tuple(TAXA_DEPOSICAO_KG_H)


class ProcessoDesconhecido(ValueError):
    """Processo de soldagem fora da tabela — melhor falhar que assumir um default."""


def _validar(processo):
    p = (processo or "").strip().lower()
    if p not in TAXA_DEPOSICAO_KG_H:
        raise ProcessoDesconhecido(
            f"Processo '{processo}' não está na tabela. Conhecidos: {', '.join(PROCESSOS)}.")
    return p


def area_chanfro_v_mm2(espessura_mm, angulo_graus=60.0, abertura_raiz_mm=2.0,
                       face_raiz_mm=1.5, reforco_mm=1.0):
    """Área da seção de um chanfro em V simples, em mm².

    Geometria: a raiz é um retângulo (abertura × altura útil) e o V é um triângulo cuja
    base cresce com a espessura e o ângulo. O reforço é a coroa acima da chapa.

    Aproximação deliberada: ignora a convexidade real do cordão. O erro fica bem abaixo
    da dispersão do fator de operação, que é o termo que domina o resultado.
    """
    if espessura_mm <= 0:
        return 0.0
    altura_v = max(espessura_mm - face_raiz_mm, 0.0)
    meia_abertura = tan(radians(angulo_graus / 2.0)) * altura_v
    area_v = meia_abertura * altura_v                      # 2 × (½ · base/2 · altura)
    area_raiz = abertura_raiz_mm * min(espessura_mm, face_raiz_mm)
    area_reforco = reforco_mm * (2 * meia_abertura + abertura_raiz_mm) * 0.5
    return area_v + area_raiz + area_reforco


def area_filete_mm2(perna_mm, reforco_pct=10.0):
    """Área da seção de um filete de perna igual, com reforço percentual."""
    if perna_mm <= 0:
        return 0.0
    return (perna_mm ** 2) / 2.0 * (1 + reforco_pct / 100.0)


@dataclass
class ResultadoSolda:
    massa_kg: float
    tempo_arco_h: float
    tempo_real_h: float
    processo: str
    fator_operacao: float
    consumivel_kg: float
    n_cordoes: int = 1
    setup_h: float = 0.0

    @property
    def parcela_arco_pct(self):
        """Quanto do tempo real é arco aberto. O resto é o trabalho invisível."""
        if self.tempo_real_h <= 0:
            return 0.0
        return self.tempo_arco_h / self.tempo_real_h * 100.0

    @property
    def modelo_otimista(self):
        """True quando há muito cordão curto e ninguém informou o setup por cordão.

        Nesse regime o tempo entre soldas domina e o modelo de deposição subestima —
        melhor dizer isso do que entregar um número limpo e errado.
        """
        return self.n_cordoes >= 20 and self.setup_h == 0.0


def horas_de_solda(area_secao_mm2, comprimento_mm, processo="smaw",
                   fator_operacao=None, taxa_deposicao_kg_h=None,
                   densidade_kg_mm3=DENSIDADE_ACO_KG_MM3,
                   n_cordoes=1, setup_por_cordao_min=0.0):
    """Tempo REAL de soldagem, a partir da geometria da junta.

    `fator_operacao` e `taxa_deposicao_kg_h` sobrescrevem a tabela — é assim que a
    empresa passa a usar o número dela em vez do referencial de literatura.

    LIMITE IMPORTANTE do modelo de deposição: ele escala com a MASSA depositada, então
    trata bem cordões longos e mal cordões curtos e numerosos. Na selagem tubo-espelho
    são centenas de soldas de poucos gramas, e aí o que domina não é depositar metal —
    é posicionar a tocha, purgar, abrir e fechar o arco, inspecionar. Só a deposição dá
    ~70 s por tubo, o que qualquer soldador reconhece como otimista demais.

    Por isso `setup_por_cordao_min`: tempo fixo por cordão, somado depois do fator de
    operação (é tempo de trabalho, não de arco). O default é **zero e não um palpite** —
    inventar 2 min/tubo daria um número mais plausível e igualmente sem lastro. Quem
    cronometra a fábrica preenche; até lá o resultado sai declaradamente otimista para
    junta curta e numerosa.
    """
    p = _validar(processo)
    taxa = taxa_deposicao_kg_h if taxa_deposicao_kg_h is not None else TAXA_DEPOSICAO_KG_H[p]
    fator = fator_operacao if fator_operacao is not None else FATOR_OPERACAO[p]
    if taxa <= 0:
        raise ValueError("Taxa de deposição precisa ser positiva.")
    if not 0 < fator <= 1:
        raise ValueError("Fator de operação é uma fração entre 0 e 1.")
    if setup_por_cordao_min < 0:
        raise ValueError("Setup por cordão não pode ser negativo.")

    massa = max(area_secao_mm2, 0.0) * max(comprimento_mm, 0.0) * densidade_kg_mm3
    tempo_arco = massa / taxa
    setup_h = max(n_cordoes, 0) * setup_por_cordao_min / 60.0
    return ResultadoSolda(
        massa_kg=massa,
        tempo_arco_h=tempo_arco,
        tempo_real_h=tempo_arco / fator + setup_h,
        processo=p,
        fator_operacao=fator,
        consumivel_kg=massa / EFICIENCIA_DEPOSICAO[p],
        n_cordoes=max(n_cordoes, 0),
        setup_h=setup_h,
    )


def solda_circunferencial(diametro_mm, espessura_mm, processo="smaw", **kw):
    """Costura circunferencial de casco/bocal: chanfro em V ao longo do perímetro."""
    return horas_de_solda(area_chanfro_v_mm2(espessura_mm), pi * max(diametro_mm, 0.0),
                          processo=processo, **kw)


def solda_longitudinal(comprimento_mm, espessura_mm, processo="smaw", **kw):
    """Costura longitudinal de virola calandrada."""
    return horas_de_solda(area_chanfro_v_mm2(espessura_mm), comprimento_mm,
                          processo=processo, **kw)


def solda_tubo_espelho(n_tubos, diametro_tubo_mm, perna_mm=3.0, processo="gtaw", **kw):
    """Selagem tubo-espelho: um filete circunferencial por tubo.

    É o caso onde a intuição mais erra — cada cordão é curto, mas há centenas deles, e o
    tempo entre cordões (posicionar, purgar, inspecionar) é que domina.
    """
    perimetro = pi * max(diametro_tubo_mm, 0.0) * max(n_tubos, 0)
    kw.setdefault("n_cordoes", max(n_tubos, 0))
    return horas_de_solda(area_filete_mm2(perna_mm), perimetro, processo=processo, **kw)


def comparar(horas_estimadas, resultado):
    """Confronta a estimativa do orçamento com a física. Não corrige nada — informa.

    `razao` > 1 significa que a física pede mais hora do que o orçamento previu.
    """
    estimadas = float(horas_estimadas or 0)
    fisica = resultado.tempo_real_h
    if fisica <= 0:
        return {"nivel": "sem_base", "razao": None,
                "texto": "Geometria não permite calcular a solda."}
    if estimadas <= 0:
        return {"nivel": "sem_estimativa", "razao": None,
                "texto": f"A física pede {fisica:.2f} h e o orçamento não previu solda."}

    ressalva = ("  (atenção: muitos cordões curtos sem setup por cordão informado — "
                "o modelo subestima neste regime)") if resultado.modelo_otimista else ""
    razao = fisica / estimadas
    if razao >= 1.25:
        return {"nivel": "subestimado", "razao": razao,
                "texto": (f"A física pede {fisica:.2f} h contra {estimadas:.2f} h "
                          f"orçadas — {(razao - 1) * 100:.0f}% a mais. "
                          f"Diferença de solda sai da margem." + ressalva)}
    if razao <= 0.8:
        return {"nivel": "folgado", "razao": razao,
                "texto": (f"O orçamento prevê {estimadas:.2f} h e a física pede "
                          f"{fisica:.2f} h. Ou há folga, ou o processo real difere do "
                          f"assumido." + ressalva)}
    return {"nivel": "coerente", "razao": razao,
            "texto": f"Estimativa ({estimadas:.2f} h) coerente com a física ({fisica:.2f} h)." + ressalva}
