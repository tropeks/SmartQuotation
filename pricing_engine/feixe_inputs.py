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
    tratamento_termico: bool = False
    teste_hidrostatico: bool = False
    projeto_detalhamento: bool = False
    inspecao_q: bool = True
    pmi: bool = False
    fator_correcao_mo: float = 1.0

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
