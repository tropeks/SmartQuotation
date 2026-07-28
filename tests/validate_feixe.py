"""
Harness de validação — feixe de 136 tubos (caso real Petrobras RPBC).
Roda o pricing_engine e confere as operações-driver contra o referencial da planilha.

Uso:  python -m tests.validate_feixe   (a partir de ~/dev/SmartQuotation)
"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing_engine import dimensions as dim, materials as mat, operations as ops
from pricing_engine import process_params as pp
from pricing_engine.rates import engematex_seed
from pricing_engine.wbs import Cotacao, Item, MateriaPrima, OperacaoExecutada

# --- Geometria do caso real (da planilha "Itens para Cotação" + cabeçalho) ---
N_TUBOS = 136
TUBO = dict(material="SA-179", forma="tubo", od='3/4"', bwg="BWG 14", comp=6096.0)
ESPELHO = dict(material="SA-516 GR 70", forma="chapa", esp=44.5, ods=[475.0, 412.0])  # 2 espelhos
CHICANA = dict(material="SA-36", forma="chapa", qty=18, od=416.8, esp=12.5)
TIRANTE = dict(material="SAE-1020", forma="barra", qty=12)

NUM_FUROS = N_TUBOS * 2          # 2 espelhos
ESP_PACOTE_CHICANAS = CHICANA["qty"] * CHICANA["esp"]   # mm

cc = engematex_seed()
GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


def check(nome, calc, referencial, tol=0.01):
    ok = abs(calc - referencial) <= max(tol, abs(referencial) * tol)
    flag = f"{GREEN}OK {RESET}" if ok else f"{RED}DIF{RESET}"
    print(f"  [{flag}] {nome:<28} calc={calc:>10,.2f}  referencial={referencial:>10,.2f}")
    return ok


print("=" * 70)
print("VALIDAÇÃO — FEIXE TUBULAR 136 TUBOS (Petrobras RPBC)")
print("=" * 70)

# --- PESOS (geometria → peso) ---
print("\n--- PESOS (computados da geometria) ---")
peso_tubos = dim.tube_weight_kg(TUBO["od"], TUBO["bwg"], TUBO["comp"], N_TUBOS,
                                mat.density(TUBO["material"]))
peso_espelhos = sum(dim.disc_weight_kg(od, ESPELHO["esp"], mat.density(ESPELHO["material"]))
                    for od in ESPELHO["ods"])
print(f"  Tubos:    {peso_tubos:>8,.1f} kg  (custo R$ {peso_tubos*cc.price_kgf('SA-179','tubo'):,.0f})")
print(f"  Espelhos: {peso_espelhos:>8,.1f} kg  (bruto, sem desconto de furos)")

# --- OPERAÇÕES-DRIVER vs REFERENCIAL ---
print("\n--- OPERAÇÕES (fórmula vs referencial da planilha) ---")
metodo_furar = pp.choose_drill_method(NUM_FUROS)   # 272 ≤ 600 → radial
print(f"  (furação: {NUM_FUROS} furos ≤ {pp.DRILL_METHOD_THRESHOLD_HOLES} → método '{metodo_furar}')")

results = []
h = ops.furar_espelho_horas(NUM_FUROS, ESPELHO["esp"])
results.append(check("ESPELHOS - FURAR", h * cc.hh("FURAR_ESPELHO"), 660))

h_hh = ops.mandrilar_horas_hh(NUM_FUROS)
h_hm = ops.mandrilar_horas_hm(h_hh)
custo_mand = h_hh * cc.hh("MANDRILAR") + h_hm * cc.hm("MANDRILAR")
results.append(check("MANDRILAR (HH+HM)", custo_mand, 720))

h = ops.furar_chicana_horas(ESP_PACOTE_CHICANAS, N_TUBOS)
results.append(check("CHICANAS - FURAR", h * cc.hh("FURAR_CHICANA"), 1650))

h = ops.soldar_horas(NUM_FUROS, "raiz")
results.append(check("SOLDAR PASSE DE RAIZ", h * cc.hh("SOLDAR_RAIZ"), 630))

h = ops.escarear_espelho_horas(NUM_FUROS)
print(f"  [info] ESCAREAR (sem referencial isolado): {h}h → R$ {h*cc.hh('ESCAREAR_ESPELHO'):,.0f}")

# --- EAP / roll-up parcial (demonstração da estrutura) ---
print("\n--- ESTRUTURA ANALÍTICA (parcial, itens-driver) ---")
item_tubos = Item("TUB-01", "Tubos de Troca Térmica",
                  materias_primas=[MateriaPrima("MP-TUB", "Tubo SA-179 3/4\" BWG14", "SA-179",
                                                "tubo", peso_tubos, cc.price_kgf("SA-179", "tubo"))])
item_esp = Item("ESP-01", "Espelhos (2)",
                materias_primas=[MateriaPrima("MP-ESP", "Chapa SA-516 GR70 44.5mm", "SA-516 GR 70",
                                              "chapa", peso_espelhos, cc.price_kgf("SA-516 GR 70", "chapa"))],
                operacoes=[
                    OperacaoExecutada("OP-FUR", "Furar", metodo_furar,
                                      NUM_FUROS, ops.furar_espelho_horas(NUM_FUROS, ESPELHO["esp"]),
                                      0, cc.hh("FURAR_ESPELHO")),
                ])
cot = Cotacao("COT-FEIXE-DEMO", "Feixe tubular 136 tubos (parcial)",
              itens=[item_tubos, item_esp], fator_preco=cc.fator_preco)
print(cot.arvore())

# --- VEREDITO ---
print("\n" + "=" * 70)
n_ok = sum(results)
print(f"OPERAÇÕES-DRIVER VALIDADAS: {n_ok}/{len(results)} batem com a planilha")
print(f"REFERENCIAL TOTAL: custo R$ 35.353 · venda c/imposto R$ 44.192 (alvo do gate 10%)")
print(f"PENDENTE: implementar as 67 ops completas + impostos + eng/ferramentas p/ fechar o total")
print("=" * 70)
