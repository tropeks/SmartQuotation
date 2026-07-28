"""
Validação COMPLETA do feixe 136 tubos: todas as 67 operações + material vs referencial.
Uso: python -m tests.validate_feixe_completo
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing_engine.feixe_inputs import caso_136_tubos
from pricing_engine.operations_registry import REGISTRY
from pricing_engine.components import feixe_136_componentes, peso_componente

GREEN, RED, YEL, RST = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
inp = caso_136_tubos()

# --- operações ---
print("=" * 72)
print("VALIDAÇÃO COMPLETA — FEIXE 136 TUBOS")
print("=" * 72)
total_ops = 0.0
por_grupo = {}
erros = []
for op in REGISTRY:
    try:
        aplic = op.applicable(inp)
        custo = op.compute(inp) if aplic else 0.0
    except Exception as e:
        erros.append((op.code, str(e))); custo = 0.0; aplic = False
    total_ops += custo
    por_grupo[op.group] = por_grupo.get(op.group, 0.0) + custo

print(f"\n--- Custo por grupo de operação ---")
for g, v in sorted(por_grupo.items(), key=lambda x: -x[1]):
    print(f"  {g:<14} R$ {v:>10,.2f}")
print(f"  {'TOTAL OPS':<14} R$ {total_ops:>10,.2f}")
print(f"  {'referencial ops':<14} R$ {20034:>10,.2f}  (Σ CF da planilha)")
delta_ops = (total_ops - 20034) / 20034 * 100
flag = GREEN if abs(delta_ops) <= 10 else (YEL if abs(delta_ops) <= 25 else RED)
print(f"  {flag}delta ops: {delta_ops:+.1f}%{RST}")

# --- material ---
total_mat = 0.0
for c in feixe_136_componentes():
    w, st = peso_componente(c)
    total_mat += w * c.rkg
print(f"\n--- Material ---")
print(f"  material (11/17 itens) R$ {total_mat:>10,.2f}")
print(f"  referencial material      R$ {15319:>10,.2f}  (custo 35.353 − ops 20.034)")

# --- total ---
custo_total = total_ops + total_mat
print(f"\n--- TOTAL ---")
print(f"  CUSTO calculado:  R$ {custo_total:>10,.2f}")
print(f"  CUSTO referencial:   R$ {35353:>10,.2f}")
delta_tot = (custo_total - 35353) / 35353 * 100
flag = GREEN if abs(delta_tot) <= 10 else (YEL if abs(delta_tot) <= 25 else RED)
print(f"  {flag}delta total: {delta_tot:+.1f}%{RST}")

if erros:
    print(f"\n{RED}ERROS DE CÁLCULO ({len(erros)}):{RST}")
    for c, e in erros[:10]:
        print(f"  {c}: {e}")

print("\n" + "=" * 72)
print(f"OPERAÇÕES: {len([o for o in REGISTRY])} no registry | erros: {len(erros)}")
print("=" * 72)

# Gate de CI: falha se o motor regredir além de 10% ou houver erro de cálculo.
import sys
GATE = 10.0
if erros:
    print(f"\nFALHA CI: {len(erros)} erro(s) de cálculo no motor.")
    sys.exit(1)
if abs(delta_tot) > GATE:
    print(f"\nFALHA CI: delta total {delta_tot:+.1f}% excede o gate de ±{GATE:.0f}%.")
    sys.exit(1)
print(f"\nGATE OK: delta {delta_tot:+.1f}% dentro de ±{GATE:.0f}%, 0 erros.")
sys.exit(0)
