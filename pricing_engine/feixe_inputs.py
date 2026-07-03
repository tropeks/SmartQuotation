"""
Inputs de geometria + config de um feixe tubular (o que o orçamentista preenche).

Caso real Petrobras RPBC (136 tubos) usado para validação. Os campos espelham os
campos amarelos da planilha (DADOS DO EQUIPAMENTO + DADOS DO FEIXE).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class FeixeInputs:
    # --- config (flags do cabeçalho que ligam/desligam operações) ---
    tipo: str = "TUBO RETO"            # TUBO RETO | TUBO U
    uniao_tubo_espelho: str = "EXPANSÃO + 2 GROOVES"
    num_grooves: int = 2
    # dado de entrada do cliente (definido por fluidos/pressao/corrosao/processo), liga/desliga as soldas de passe; default True porque o caso de referencia RPBC (136 tubos) e SOLDADO.
    solda_selagem: bool = True
    tratamento_termico: bool = False
    teste_hidrostatico: bool = False
    projeto_detalhamento: bool = False
    inspecao_q: bool = True
    pmi: bool = False
    fator_correcao_mo: float = 1.0
    # transporte é cotado caso a caso pelo orçamentista; default = caso ref RPBC.
    custo_transporte: float = 1600.0
    # markup sobre ensaios (END) e transporte é decisão POR JOB (Wellington, caso a
    # caso). Default True = baseline validado (markup sobre o custo total). False =
    # aquela parcela passa a custo (pass-through), fora da base de markup.
    markup_sobre_ensaios: bool = True
    markup_sobre_transporte: bool = True

    # --- tubos ---
    n_tubos: int = 136
    tubo_material: str = "SA-179"
    tubo_od_spec: str = '3/4"'
    tubo_wall_spec: str = "BWG 14"
    tubo_comp_mm: float = 6096.0
    tubo_od_mm: float = 19.05         # X112 na planilha (OD em mm) — controla ajustes

    # --- espelhos ---
    espelho_material: str = "SA-516 GR 70"
    n_espelhos: int = 2
    espelho_esp_bruta_mm: float = 44.5    # BK23
    espelho_od_mm: float = 475.0          # AW23 (maior)

    # --- chicanas + chapa suporte ---
    chicana_qty: int = 18                 # AP31
    chicana_esp_mm: float = 12.5          # BK31
    chicana_od_mm: float = 416.8          # AW31
    chicana_material: str = "SA-36"
    chicana_cut_remaining_mm: float = 300.0  # "CORTE": altura que sobra (hc = od - este)
    chicana_corte_laser: bool = False        # chapa chega cortada no perfil a laser (terceirizado)
                                             # → remove traçado/recorte/acabamento de contorno da MO
    chapa_suporte_qty: int = 1            # AP35
    chapa_suporte_esp_mm: float = 12.5    # BD35

    espelho_flutuante_od_mm: float = 412.0   # OD do espelho flutuante (2b)

    # --- chapa suporte ---
    chapa_suporte_material: str = "SA-36"

    # --- tirantes / barras ---
    tirante_qty: int = 12                 # AT132 (furos p/ tirantes) ~ qtd tirantes
    tirante_material: str = "SAE-1020"
    tirante_od_spec: str = '3/8"'
    tirante_comp_mm: float = 6000.0
    n_barras_selagem_desliz: int = 6      # AP55+AP59+AP63 (2+2+2)

    # --- acessórios (specs padrão do caso 136; viram defaults parametrizáveis) ---
    espacador_qty: int = 12
    espacador_material: str = "SA-214"
    espacador_comp_mm: float = 6096.0     # comprimento de COMPRA (Opção A); ver espaçador
    porcas_qty: int = 24
    plugues_qty: int = 2                  # cada conjunto (1) e (2)
    olhais_qty: int = 2

    # --- rasgos (espelho flutuante) ---
    num_rasgos: int = 0                   # BR23+BR27

    # --- derivados ---
    @property
    def num_furos(self) -> int:
        """Nº de furos = nº tubos × nº espelhos."""
        return self.n_tubos * self.n_espelhos

    @property
    def esp_pacote_chicanas_mm(self) -> float:
        """Espessura do pacote p/ furar chicanas = Σ(qtd×esp) chicanas + chapa suporte."""
        return (self.chicana_qty * self.chicana_esp_mm
                + self.chapa_suporte_qty * self.chapa_suporte_esp_mm)

    @property
    def is_u(self) -> bool:
        return self.tipo.upper().startswith("TUBO U")


def caso_136_tubos() -> FeixeInputs:
    """Caso de validação (gabarito: custo R$ 35.353)."""
    return FeixeInputs()


def caso_of_3672() -> FeixeInputs:
    """Caso REAL OF-3672 (REPLAN, opportunity nº 7004563412, feixe tubular reto, P.28510).
    Fonte: orçamento manuscrito real (uploads/OF-3672 - Feixe tubular.pdf), transcrito e
    validado pelo PE Wellington. Backtest financeiro em tests/test_golden_financial.py
    (total +3,5% dentro da banda ideal ≤5%; ver tests/golden_anchors.json).

    Transcrição do manuscrito (2 páginas):
      - IT.1: TUBO Ø3/4"×14BWG×3048mm ×210, A-179 (=SA-179) — R$15.750 (65% da MP).
      - IT.2/IT.3: DISCOS (espelhos) Ø540×27 e Ø482×27, A-266 gr.2 FORJADO — R$3.570+3.030.
      - IT.4: 10 CHAPAS 495×326×1/4" (chicanas), A-516 gr.60; cortadas a LASER (terceirizado).
      - União tubo-espelho MANDRILADA (expansão + 2 grooves), SEM solda de selagem (Wellington
        confirmou: reduz MO ao excluir soldas de passe). Transporte R$800 (TRANSP. EWG/REPLAN).
    Preços R$/kg reais deste job vivem na cost_chain do backtest, não aqui (motor = lib pura).
    """
    return FeixeInputs(
        n_tubos=210, tubo_comp_mm=3048.0, tubo_material="SA-179",
        custo_transporte=800.0,
        solda_selagem=False,                      # MANDRILADO — sem soldas de passe
        chicana_qty=10,                           # IT.4 = 10 chapas
        chicana_corte_laser=True,                 # IT.4: chapas cortadas a LASER (terceirizado)
        espelho_material="A-266 GR 2",
        espelho_od_mm=540.0, espelho_esp_bruta_mm=27.0,
        espelho_flutuante_od_mm=482.0,
    )


def caso_of_3399() -> FeixeInputs:
    """Caso de regressão OF-3399 (REFAP, opportunity nº 7004264653, feixe tubular U,
    P.544). Fonte: orçamento manuscrito real (uploads/OF-3399 - Feixe tubular U.pdf).

    Campos extraídos com confiança do manuscrito: "IT.14 = TUBO Ø3/4X14BWGX13000MMX64"
    material B.3003H14 (alumínio, resolvido via alias — ver test_material_alias.py). Os
    demais campos (chicanas, tirantes etc.) não são inequivocamente legíveis no rascunho
    manuscrito e herdam os defaults de referência — este caso é uma regressão/snapshot do
    motor, não uma validação financeira completa contra o orçamento real.
    """
    return FeixeInputs(
        tipo="TUBO U",
        n_tubos=64,
        tubo_comp_mm=13000.0,
        tubo_material="B.3003H14",
    )
