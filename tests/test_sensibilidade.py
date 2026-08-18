"""Guarda da varredura de sensibilidade (scripts/sensibilidade_motor.py).

Não testa o MOTOR (isso é validate_feixe_completo / validate_permutador_completo /
test_cost_chain_knobs) — testa o HARNESS: que ele reproduz o baseline em perturbação
zero, que roda ponta a ponta sem exceção para os 4 casos, e que pelo menos um punhado
de números tem sinal/ordem de grandeza conhecidos ANALITICAMENTE (não "porque o script
disse"), então uma regressão no motor OU no harness estoura aqui, não só no relatório.

Rodar: python -m tests.test_sensibilidade   (ou pytest tests/test_sensibilidade.py)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pytest  # noqa: E402

import sensibilidade_motor as sm  # noqa: E402
from pricing_engine.permutador_quote import quote_completo, _SETUP_FRAC  # noqa: E402
from pricing_engine.rates import TenantCostChain  # noqa: E402

DESIGNACOES_COM_FORM = ["BEU", "BEM"]
TODAS_PERMUTADOR = ["BEU", "BEM", "OF3683"]


# ═══════════════════════════════════════════════════════════════════════════════════
# 1) Perturbação ZERO reproduz o baseline EXATAMENTE — pega drift do motor e do harness
# ═══════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("designacao", DESIGNACOES_COM_FORM)
def test_dims_override_ratio_1_reproduz_baseline_exatamente(designacao):
    """Data sheet preenchido com os PRÓPRIOS valores de referência (razão 1,0 em tudo)
    tem que reconciliar 0,0% — é o mesmo caminho de código que um formulário real usa,
    só que sem nenhum erro humano de preenchimento."""
    ref = sm.reference_inputs(designacao)
    dims_override = sm.to_dims_override(designacao, ref)
    params = sm.physical_params(designacao, ref)
    chain = TenantCostChain(fator_correcao_mo=1.0)
    com_form = quote_completo(designacao, cost_chain=chain, dims_override=dims_override,
                              params=params)
    sem_form = quote_completo(designacao, cost_chain=chain)
    assert com_form["custo_total"] == sem_form["custo_total"]
    assert com_form["custo_mao_obra"] == sem_form["custo_mao_obra"]
    assert com_form["custo_material"] == sem_form["custo_material"]


@pytest.mark.parametrize("designacao", TODAS_PERMUTADOR)
def test_setup_frac_perturbado_no_ponto_de_referencia_nao_move_nada(designacao):
    """Câmbio DIRETO (sem passar pelo harness): qualquer setup_frac, com todo driver físico
    em 1,0 (params=None), reproduz o custo exatamente — é identidade algébrica de
    permutador_quote._escala_op (setup + (1-setup)×1,0 = 1,0 p/ qualquer setup), não
    coincidência numérica."""
    base = quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=1.0))
    absurdo = quote_completo(designacao, cost_chain=TenantCostChain(
        fator_correcao_mo=1.0, setup_frac={k: 0.99 for k in _SETUP_FRAC}))
    assert absurdo["custo_total"] == base["custo_total"]
    assert absurdo["custo_mao_obra"] == base["custo_mao_obra"]


@pytest.mark.parametrize("designacao", TODAS_PERMUTADOR)
def test_material_chain_mult_1_reproduz_pelo_menos_o_dominante(designacao):
    """A cadeia de preço/kg construída pelo harness (dominant-weight por colisão de chave
    material×forma) reproduz EXATAMENTE o preço do item de maior peso em cada chave — não
    testamos reprodução total (documentado: pode haver drift por colisão; ver
    colisoes_preco_kgf), só que o mecanismo de resolução funciona como projetado."""
    chain = sm.material_chain_permutador(designacao, mult=1.0)
    colisoes = {c["material"]: c for c in sm.colisoes_preco_kgf(designacao)}
    for key, price in chain.material_price.items():
        material, forma = key
        if material in colisoes:
            dominante = max(colisoes[material]["itens"], key=lambda i: i["peso_bruto_kg"])
            assert price == pytest.approx(dominante["price_kgf"])


def test_feixe_perturbacao_zero_reproduz_baseline():
    """replace(inp, campo=valor_original) é uma perturbação nula — tem que reproduzir o
    baseline bit-a-bit (dataclasses.replace não muta o original)."""
    from dataclasses import replace
    inp = sm.caso_136_tubos()
    igual = replace(inp, n_tubos=inp.n_tubos)
    from pricing_engine.feixe_quote import quote_feixe
    a = quote_feixe(inp)
    b = quote_feixe(igual)
    assert a.custo_total == b.custo_total


# ═══════════════════════════════════════════════════════════════════════════════════
# 2) A varredura roda ponta a ponta, sem exceção, para os 4 casos
# ═══════════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def dados_completos():
    return sm.montar_tudo()


def test_monta_tudo_produz_os_4_casos(dados_completos):
    nomes = {c["nome"] for c in dados_completos["casos"]}
    assert nomes == {"BEU", "BEM", "OF3683", "FEIXE-136"}


def test_todo_caso_tem_entradas_com_pontos(dados_completos):
    for caso in dados_completos["casos"]:
        assert len(caso["entradas"]) >= 8, f"{caso['nome']} tem poucas entradas varridas"
        for ent in caso["entradas"]:
            if not ent["pontos"]:
                # entrada explicitamente pulada (ex.: preço/kg p/ designação com colisão
                # grande demais) — tem que vir com nota explicando por quê, não silêncio.
                assert ent["nota"], f"{caso['nome']}/{ent['nome']} sem pontos e sem nota"
                continue
            for chave, ponto in ent["pontos"].items():
                assert ponto["custo_total_bruto"] is not None, (caso["nome"], ent["nome"], chave)


def test_ranking_nao_fica_vazio(dados_completos):
    ranking = sm.ranking_movimenta_dinheiro(dados_completos)
    assert len(ranking) >= 30


# ═══════════════════════════════════════════════════════════════════════════════════
# 3) Sanidade econômica — sinal e ordem de grandeza conhecidos ANALITICAMENTE
# ═══════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("designacao", TODAS_PERMUTADOR)
def test_fc_afim_em_fc_hipotese_verificada_num_terceiro_ponto(designacao):
    """O back-solve (solve_fc_affine) assume custo_total AFIM em fc usando só 2 pontos
    (fc=1,0 e fc=2,0). Prova empírica: um TERCEIRO ponto (fc=1,5) tem que cair EXATAMENTE
    na reta que os 2 primeiros definem — senão a hipótese algébrica do módulo está errada
    e todo E_calib do relatório é lixo."""
    def custo(fc):
        return quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=fc))["custo_total"]
    y1, y2, y15 = custo(1.0), custo(2.0), custo(1.5)
    esperado = y1 + (y2 - y1) * 0.5
    assert y15 == pytest.approx(esperado, abs=0.01)


@pytest.mark.parametrize("designacao", TODAS_PERMUTADOR)
def test_fator_preco_e_bruta_e_exatamente_1(designacao):
    """preco_com_impostos = custo_total × fator_preco (quote_completo) — proporcionalidade
    DIRETA, então E_bruta(fator_preco → preco_com_impostos) = 1,0 exato, sempre, por
    qualquer δ. Se isso quebrar, ou o motor mudou a fórmula de preço, ou o harness está
    medindo a métrica errada."""
    caso = sm.montar_caso_permutador(designacao, designacao)
    entradas = sm.montar_entradas_permutador(caso)
    fp = next(e for e in entradas if e.nome.startswith("fator_preco"))
    for ponto in fp.pontos.values():
        assert ponto.e_bruta == pytest.approx(1.0, abs=1e-4)


def test_feixe_fator_preco_e_bruta_e_exatamente_1():
    caso = sm.CasoFeixe(nome="FEIXE-136", referencial=sm.REFERENCIAL_FEIXE,
                        fator_preco=sm.FATOR_PRECO_FEIXE_136, impostos_pct=sm.IMPOSTOS_FEIXE_136)
    entradas = sm.montar_entradas_feixe(caso)
    fp = next(e for e in entradas if e.nome.startswith("fator_preco"))
    for ponto in fp.pontos.values():
        assert ponto.e_bruta == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize("designacao", TODAS_PERMUTADOR)
def test_elasticidade_fc_nao_passa_da_fracao_de_mo(designacao):
    """A elasticidade de custo_total a fator_correcao_mo (um driver PURO de MO — multiplica
    toda mão-de-obra uniformemente) não pode superar a fração de MO no custo total: fc só
    move a parcela de MO, nunca material nem serviço fixo. Bound analítico direto, não
    medido — se estourar, o motor passou a deixar fc vazar pra fora da MO (ou o cálculo de
    fração de MO do harness está errado)."""
    caso = sm.montar_caso_permutador(designacao, designacao)
    entradas = sm.montar_entradas_permutador(caso)
    fc_entry = next(e for e in entradas if e.nome == "fator_correcao_mo")
    fracao_mo = caso.baseline["custo_mao_obra"] / caso.baseline["custo_total"]
    for ponto in fc_entry.pontos.values():
        assert 0 < ponto.e_bruta <= fracao_mo + 1e-9


def test_impostos_pct_nao_move_preco_com_impostos_no_permutador():
    """ACHADO estrutural do motor (ver docs/SENSIBILIDADE_MOTOR.md): em quote_completo,
    preco_com_impostos = custo_total × fator_preco é calculado ANTES do gross-up de
    impostos; impostos_pct só afeta preco_sem_impostos (derivado por divisão). Pino esse
    comportamento — se um dia mudar, é uma mudança de modelo de preço que merece ser vista,
    não um bug do harness."""
    for designacao in TODAS_PERMUTADOR:
        base = quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=1.0),
                              impostos_pct=9.0)
        outro = quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=1.0),
                               impostos_pct=20.0)
        assert base["preco_com_impostos"] == outro["preco_com_impostos"]
        assert base["preco_sem_impostos"] != outro["preco_sem_impostos"]


def test_mo_fraction_beu_diverge_do_numero_citado_no_handoff():
    """PIN de regressão do achado do relatório: docs/HANDOFF_MIGRACAO.md §4 cita MO=32%
    (R$40.990/R$128.160) no BEU — o motor ATUAL mede ~38-39%. Divergência real (motor
    evoluiu desde a discussão de 2026-07-31: refinos v3 de solda∝espessura²/fator de liga),
    não erro de medição. Este teste pina o valor MEDIDO; se ele voltar pra perto de 32%,
    quer dizer que o motor regrediu os refinos v3 — investigar, não só atualizar o número."""
    caso = sm.montar_caso_permutador("BEU", "BEU")
    fracao = caso.baseline["custo_mao_obra"] / caso.baseline["custo_total"] * 100
    assert 37.0 <= fracao <= 40.5, (
        f"MO% do BEU = {fracao:.1f}% — fora da banda esperada (37-40,5%); "
        f"handoff citava 32%, mas isso é hipótese desatualizada, não gate.")


def test_mandrilar_gap_beu_e_exatamente_120_reais():
    """PIN do achado #8: FAB-MANDRILAR-1 (BEU) tem `rate=80` no seed de operações,
    inconsistente com `preco_referencial=360,0` (que só bate com rate=120,0 —
    `3,0h×120=360`, não `3,0h×80=240`). O gap dispara quando a TenantCostChain em uso NÃO
    tem rate_hh para MANDRILAR (cai no fallback `o["rate"]=80` via `hh_any`) — sem chain
    (`None`, usa `preco_referencial` direto) R$128.162,69; chain vazia (sem
    rate_hh["MANDRILAR"]) R$128.042,69, -R$120,00 exatos. Isolando SÓ o rate de MANDRILAR
    (sem misturar com as outras diferenças que `rates.engematex_seed()` completo introduz
    em OUTRAS operações — motivo de não comparar contra ele aqui): uma chain com
    `rate_hh={"MANDRILAR": 120}` (o valor correto, o mesmo de `engematex_seed()`) reproduz
    o "sem chain" BIT-A-BIT — prova de que o gap é 100% isolado nesse rate."""
    sem_chain = quote_completo("BEU", cost_chain=None)["custo_total"]
    chain_vazia = quote_completo("BEU", cost_chain=TenantCostChain(fator_correcao_mo=1.0))["custo_total"]
    so_mandrilar_certo = quote_completo(
        "BEU", cost_chain=TenantCostChain(fator_correcao_mo=1.0, rate_hh={"MANDRILAR": 120})
    )["custo_total"]

    assert sem_chain - chain_vazia == pytest.approx(120.0, abs=0.01)
    assert so_mandrilar_certo == pytest.approx(sem_chain, abs=0.01)


@pytest.mark.parametrize("designacao", DESIGNACOES_COM_FORM)
def test_comprimento_casco_e_exatamente_inerte_ao_canal_de_mo(designacao):
    """PIN do achado #1: comprimento_casco_mm move dims_override (material da VIROLA) mas
    NÃO entra em nenhum driver físico de `_physical_params` (que usa comprimento_TUBO_mm
    para o driver "comprimento" que escala a MO do casco) — custo_mao_obra tem que ficar
    BIT-A-BIT igual ao baseline quando só esse campo muda."""
    ref = sm.reference_inputs(designacao)
    baseline = quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=1.0),
                              dims_override=sm.to_dims_override(designacao, ref),
                              params=sm.physical_params(designacao, ref))
    cleaned = dict(ref)
    cleaned["comprimento_casco_mm"] = float(ref["comprimento_casco_mm"]) * 1.10
    perturbado = quote_completo(designacao, cost_chain=TenantCostChain(fator_correcao_mo=1.0),
                                dims_override=sm.to_dims_override(designacao, cleaned),
                                params=sm.physical_params(designacao, cleaned))
    assert perturbado["custo_mao_obra"] == baseline["custo_mao_obra"]
    assert perturbado["custo_material"] != baseline["custo_material"]  # o canal de material MOVE


# ═══════════════════════════════════════════════════════════════════════════════════
# main() — modo `python -m tests.test_sensibilidade`, no padrão dos outros gates puros
# ═══════════════════════════════════════════════════════════════════════════════════

def main():
    """Modo `python -m tests.test_sensibilidade`: os testes usam fixtures e
    parametrize (pytest-only), então delega para o pytest em vez de reimplementar um
    runner — mais simples e não diverge do que `pytest tests/test_sensibilidade.py` roda."""
    print("=" * 72)
    print("GATE — guarda da varredura de sensibilidade (via pytest)")
    print("=" * 72)
    codigo = pytest.main([os.path.abspath(__file__), "-v"])
    print("=" * 72)
    print("GATE OK" if codigo == 0 else f"GATE FALHOU (pytest exit={codigo})")
    print("=" * 72)
    sys.exit(int(codigo))


if __name__ == "__main__":
    main()
