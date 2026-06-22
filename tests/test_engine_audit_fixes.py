import pytest

from pricing_engine.feixe_inputs import caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.permutador_quote import gross_up_icms, quote_completo
from pricing_engine.rates import TenantCostChain


def _feixe_mo(cot):
    return sum(it.custo_mo for it in cot.itens) + cot.custo_engenharia + cot.custo_ferramentas


def test_quote_feixe_rates_alteram_mao_de_obra():
    inp = caso_136_tubos()
    base = quote_feixe(inp)
    sem_furacao = quote_feixe(
        inp,
        cost_chain=TenantCostChain(
            rate_hh={"FURAR_ESPELHO": 0, "FURAR_CHICANA": 0},
            fator_correcao_mo=1.0,
        ),
    )

    assert _feixe_mo(sem_furacao) < _feixe_mo(base)
    assert sem_furacao.custo_total < base.custo_total


def test_quote_feixe_rate_hm_altera_mandrilagem():
    inp = caso_136_tubos()
    base = quote_feixe(inp)
    sem_hm = quote_feixe(
        inp,
        cost_chain=TenantCostChain(
            rate_hh={"MANDRILAR": 120},
            rate_hm={"MANDRILAR": 0},
            fator_correcao_mo=1.0,
        ),
    )

    assert _feixe_mo(sem_hm) < _feixe_mo(base)


def test_quote_feixe_nao_engole_erro_de_operacao(monkeypatch):
    from pricing_engine import feixe_quote

    op = feixe_quote.REGISTRY[0]
    original = op.compute
    op.compute = lambda _inp: (_ for _ in ()).throw(ValueError("boom"))
    try:
        with pytest.raises(RuntimeError, match=op.code):
            quote_feixe(caso_136_tubos())
    finally:
        op.compute = original


def test_permutador_quantidade_tubos_recomputa_material():
    base = quote_completo("BEU")
    dobrado = quote_completo(
        "BEU",
        dims_override={"TUBOS DE TROCA TÉRMICA": {"QUANTIDADE": 136}},
    )

    assert dobrado["custo_material"] > base["custo_material"]


def test_permutador_virola_ratio_e_espessura_recomputam_material():
    base = quote_completo("BEU")
    maior = quote_completo(
        "BEU",
        dims_override={"VIROLA": {"_LARGURA_RATIO": 2.0, "ESP.": 19.0}},
    )

    assert maior["custo_material"] > base["custo_material"]


def test_permutador_rate_tenant_altera_mao_de_obra():
    base = quote_completo("BEU")
    sem_furar = quote_completo(
        "BEU",
        cost_chain=TenantCostChain(rate_hh={"FAB-FURAR-1": 0}, fator_correcao_mo=1.0),
    )

    assert sem_furar["custo_mao_obra"] < base["custo_mao_obra"]


def test_gross_up_icms_valida_intervalo():
    assert gross_up_icms(9.0) > 1.0
    with pytest.raises(ValueError):
        gross_up_icms(100.0)
    with pytest.raises(ValueError):
        gross_up_icms(-1.0)
