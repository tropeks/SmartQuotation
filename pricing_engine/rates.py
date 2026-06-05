"""
Rate (custo) — dados de TENANT, editáveis, versionados.

Separação-chave: ProcessParameter gera HORAS (física); Rate converte HORAS → R$ (custo).
- RateHH: R$/hora homem-hora por operação
- RateHM: R$/hora hora-máquina (ops de usinagem)
- MaterialPrice: R$/kgf por (material × forma)  — RESOLVIDO Q4
- fator_correcao_mo: multiplica TODAS as horas (B31 na planilha)
- fator_preco: markup final ; impostos por NCM/local
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TenantCostChain:
    """A 'cadeia de custos' do tenant (ENGEMATEX) — o que o wizard A1-c popula."""
    # R$/hora homem-hora por operação (rate HH). Valores da planilha ENGEMATEX.
    rate_hh: dict[str, float] = field(default_factory=dict)
    # R$/hora hora-máquina por operação (rate HM).
    rate_hm: dict[str, float] = field(default_factory=dict)
    # R$/kgf por (material_sigla, forma). forma: chapa|tubo|barra|forjado|fundido
    material_price: dict[tuple[str, str], float] = field(default_factory=dict)
    fator_correcao_mo: float = 1.0
    fator_preco: float = 1.0          # markup final
    impostos_pct: float = 0.0         # % sobre preço (ICMS+PIS+COFINS...)

    def hh(self, operacao: str, default: float = 0.0) -> float:
        return self.rate_hh.get(operacao, default)

    def hm(self, operacao: str, default: float = 0.0) -> float:
        return self.rate_hm.get(operacao, default)

    def price_kgf(self, material: str, forma: str) -> float:
        key = (material.strip().upper(), forma.strip().lower())
        if key in self.material_price:
            return self.material_price[key]
        # fallback: qualquer forma do material
        for (m, _f), v in self.material_price.items():
            if m == key[0]:
                return v
        raise KeyError(f"Preço R$/kgf indisponível p/ {material!r} forma {forma!r}")


def engematex_seed() -> TenantCostChain:
    """Seed da cadeia de custos ENGEMATEX (rates lidos das fórmulas da planilha).

    NOTA: no produto, isto vem do wizard de descoberta de custo (A1-c), editável.
    Aqui é seed p/ validar o motor contra o caso real de 136 tubos.
    """
    return TenantCostChain(
        rate_hh={
            "FURAR_ESPELHO": 110, "ALARGAR_ESPELHO": 110, "ESCAREAR_ESPELHO": 110,
            "GROOVES_ESPELHO": 110, "USINAR_FUROS_TIRANTES": 110, "ESCAREAR_CHICANA": 110,
            "FURAR_CHICANA": 110, "TRACAR_FUROS_ESPELHO": 80, "TRACAR_RASGOS": 80,
            "TRACAR_FUROS_CHICANA": 80, "MANDRILAR": 120, "SOLDAR_RAIZ": 90,
            "SOLDAR_ACABAMENTO": 90, "CURVAR_TUBO_U": 160, "MONTAR_TUBOS": 40,
            "ACABAMENTO_ESPELHO": 40, "CHICANA_TRACAR_RECORTAR": 90,
            "CHICANA_RECORTAR_ACABAMENTO": 130, "PREPARAR_TIRANTES": 120,
        },
        rate_hm={"MANDRILAR": 80, "USINAR_RASGOS": 150, "CHICANA_USINAR": 150},
        material_price={
            ("A-179", "tubo"): 13.5, ("SA-179", "tubo"): 13.5,
            ("SA-516 GR 70", "chapa"): 6.5, ("A-516 GR 70", "chapa"): 6.5,
            ("SA-36", "chapa"): 6.5, ("A-36", "chapa"): 6.5,
            ("SAE-1020", "barra"): 4.5,
        },
        fator_correcao_mo=1.0,
        fator_preco=1.20,     # ~ custo 35353 → venda s/imposto 35840? ajustar; ver harness
        impostos_pct=0.0,
    )
