"""
Régua de solda por primeiros princípios (S4).

Módulo puro: roda sem Django e sem banco, como os demais gates do motor.

O que estes testes protegem não é um número mágico e sim três relações que a intuição
erra: o tempo de arco é uma fração do tempo real; a solda cresce com o QUADRADO da
espessura por causa da geometria do chanfro; e centenas de cordões curtos (tubo-espelho)
somam mais do que parece.
"""
import sys
from math import isclose, pi

from pricing_engine.solda_fisica import (DENSIDADE_ACO_KG_MM3, FATOR_OPERACAO,
                                         ProcessoDesconhecido, area_chanfro_v_mm2,
                                         area_filete_mm2, comparar, horas_de_solda,
                                         solda_circunferencial, solda_longitudinal,
                                         solda_tubo_espelho)

_falhas = []


def checa(condicao, mensagem):
    if condicao:
        print(f"  OK     {mensagem}")
    else:
        print(f"  FALHOU {mensagem}")
        _falhas.append(mensagem)


def test_massa_sai_da_geometria():
    """1 m de cordão com 100 mm² de seção = 100.000 mm³ = 0,785 kg de aço."""
    r = horas_de_solda(area_secao_mm2=100.0, comprimento_mm=1000.0, processo="smaw")
    esperado = 100.0 * 1000.0 * DENSIDADE_ACO_KG_MM3
    checa(isclose(r.massa_kg, esperado, rel_tol=1e-9),
          f"massa depositada = área × comprimento × densidade ({r.massa_kg:.4f} kg)")


def test_tempo_de_arco_e_fracao_do_tempo_real():
    """O erro que mais custa: orçar pelo arco subestima a solda em ~3× no manual."""
    r = horas_de_solda(500.0, 2000.0, processo="smaw")
    checa(r.tempo_real_h > r.tempo_arco_h, "tempo real é maior que o tempo de arco")
    checa(isclose(r.tempo_real_h, r.tempo_arco_h / FATOR_OPERACAO["smaw"], rel_tol=1e-9),
          "tempo real = tempo de arco ÷ fator de operação")
    checa(20 <= r.parcela_arco_pct <= 30,
          f"no eletrodo revestido o arco é ~25% do tempo ({r.parcela_arco_pct:.1f}%)")


def test_processo_mais_produtivo_gasta_menos_hora():
    manual = horas_de_solda(500.0, 2000.0, processo="smaw")
    submerso = horas_de_solda(500.0, 2000.0, processo="saw")
    checa(submerso.tempo_real_h < manual.tempo_real_h / 5,
          "arco submerso é mais de 5× mais rápido que eletrodo revestido")


def test_fator_de_operacao_da_empresa_sobrescreve_a_literatura():
    padrao = horas_de_solda(500.0, 2000.0, processo="smaw")
    medido = horas_de_solda(500.0, 2000.0, processo="smaw", fator_operacao=0.50)
    checa(medido.tempo_real_h < padrao.tempo_real_h,
          "fator medido melhor que o referencial reduz a hora estimada")
    checa(isclose(medido.tempo_arco_h, padrao.tempo_arco_h, rel_tol=1e-9),
          "o tempo de ARCO não muda — o que muda é o entorno")


def test_chanfro_cresce_mais_que_linearmente_com_a_espessura():
    """Dobrar a espessura mais que dobra o metal depositado: o V abre junto."""
    fina = area_chanfro_v_mm2(10.0)
    grossa = area_chanfro_v_mm2(20.0)
    checa(grossa > 2 * fina,
          f"área do chanfro 20 mm ({grossa:.0f} mm²) > 2× a de 10 mm ({fina:.0f} mm²)")


def test_espessura_zero_nao_gera_solda():
    checa(area_chanfro_v_mm2(0.0) == 0.0, "espessura zero → área zero")
    checa(area_filete_mm2(0.0) == 0.0, "perna zero → área zero")


def test_costura_circunferencial_usa_o_perimetro():
    d, esp = 800.0, 12.0
    r = solda_circunferencial(d, esp)
    direto = horas_de_solda(area_chanfro_v_mm2(esp), pi * d)
    checa(isclose(r.tempo_real_h, direto.tempo_real_h, rel_tol=1e-9),
          "circunferencial = chanfro × π × diâmetro")


def test_costura_longitudinal_usa_o_comprimento():
    r = solda_longitudinal(3000.0, 12.0)
    checa(r.tempo_real_h > 0, f"virola de 3 m com 12 mm: {r.tempo_real_h:.2f} h")


def test_tubo_espelho_soma_muito_cordao_curto():
    """Cada cordão é pequeno; 500 deles não são."""
    um = solda_tubo_espelho(1, 19.05)
    muitos = solda_tubo_espelho(500, 19.05)
    checa(isclose(muitos.tempo_real_h, um.tempo_real_h * 500, rel_tol=1e-9),
          f"500 tubos = 500× um tubo ({muitos.tempo_real_h:.1f} h)")
    checa(muitos.tempo_real_h > 5,
          f"selagem de 500 tubos não é detalhe de orçamento ({muitos.tempo_real_h:.1f} h)")
    checa(muitos.modelo_otimista,
          "e o resultado se declara OTIMISTA: sem setup por cordão, o modelo de "
          "deposição subestima cordão curto e numeroso")


def test_setup_por_cordao_domina_na_selagem_tubo_espelho():
    """Onde o modelo de deposição é fraco, o setup medido é que manda."""
    so_deposicao = solda_tubo_espelho(500, 19.05)
    com_setup = solda_tubo_espelho(500, 19.05, setup_por_cordao_min=2.0)
    checa(com_setup.tempo_real_h > so_deposicao.tempo_real_h * 2.5,
          f"2 min/tubo mais que dobra a estimativa ({so_deposicao.tempo_real_h:.1f} h "
          f"→ {com_setup.tempo_real_h:.1f} h)")
    checa(not com_setup.modelo_otimista,
          "com setup informado o resultado deixa de se declarar otimista")


def test_cordao_longo_nao_dispara_a_ressalva():
    """Uma costura circunferencial é um cordão só — o regime é outro."""
    r = solda_circunferencial(800.0, 12.0)
    checa(not r.modelo_otimista, "junta longa e única não é regime de setup dominante")


def test_consumivel_e_maior_que_o_depositado():
    """Respingo, ponta de eletrodo e escória: compra-se mais do que vira cordão."""
    r = horas_de_solda(500.0, 2000.0, processo="smaw")
    checa(r.consumivel_kg > r.massa_kg,
          f"consumível ({r.consumivel_kg:.2f} kg) > depositado ({r.massa_kg:.2f} kg)")


def test_processo_desconhecido_falha_em_vez_de_assumir():
    try:
        horas_de_solda(100.0, 1000.0, processo="laser")
    except ProcessoDesconhecido:
        checa(True, "processo fora da tabela levanta erro em vez de assumir default")
    else:
        checa(False, "processo desconhecido deveria falhar")


def test_parametro_invalido_e_recusado():
    for kwargs, rotulo in (({"fator_operacao": 0}, "fator zero"),
                           ({"fator_operacao": 1.5}, "fator acima de 1"),
                           ({"taxa_deposicao_kg_h": 0}, "taxa zero")):
        try:
            horas_de_solda(100.0, 1000.0, **kwargs)
        except ValueError:
            checa(True, f"{rotulo} é recusado")
        else:
            checa(False, f"{rotulo} deveria ser recusado")


def test_comparacao_acusa_subestimativa():
    r = horas_de_solda(500.0, 2000.0, processo="smaw")
    d = comparar(r.tempo_real_h / 3, r)     # orçamento previu um terço
    checa(d["nivel"] == "subestimado", f"orçar 1/3 da física acusa subestimativa: {d['texto']}")


def test_comparacao_reconhece_coerencia():
    r = horas_de_solda(500.0, 2000.0, processo="smaw")
    checa(comparar(r.tempo_real_h, r)["nivel"] == "coerente",
          "estimativa igual à física é coerente")


def test_comparacao_sem_estimativa_ainda_informa():
    r = horas_de_solda(500.0, 2000.0)
    d = comparar(0, r)
    checa(d["nivel"] == "sem_estimativa" and "não previu" in d["texto"],
          "orçamento sem solda é apontado, não ignorado")


def main():
    print("=" * 72)
    print("GATE — solda por primeiros princípios (régua paralela, não custeio)")
    print("=" * 72)
    for nome, funcao in sorted(globals().items()):
        if nome.startswith("test_") and callable(funcao):
            print(f"\n{nome}")
            funcao()
    print("\n" + "=" * 72)
    if _falhas:
        print(f"GATE FALHOU: {len(_falhas)} verificação(ões)")
        return 1
    print("GATE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
