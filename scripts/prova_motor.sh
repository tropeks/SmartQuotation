#!/usr/bin/env bash
# Prova do motor de custeio: os quatro gates stdlib que o job `pricing-engine` do CI roda.
# É o rótulo `motor` do `.maestro.yaml` (INTENT v2 §Limites: "gates do motor nunca regridem").
#
# Roda fora da lab: Python puro, sem Django, sem banco, sem docker, sem rede. Por isso é a
# prova que qualquer run headless consegue refazer no tip, em segundos.
#
# Todos os gates rodam mesmo quando um reprova, para que o recibo mostre o quadro inteiro;
# o exit é 1 se qualquer um reprovar.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

PY="${PYTHON:-python3}"
GATES=(
  tests.validate_feixe_completo
  tests.validate_permutador_completo
  tests.test_cost_chain_knobs
  tests.test_solda_fisica
)

falhas=()
for gate in "${GATES[@]}"; do
  echo "== $gate"
  if "$PY" -m "$gate"; then
    echo "-- $gate: OK"
  else
    echo "-- $gate: REPROVADO"
    falhas+=("$gate")
  fi
done

if [ "${#falhas[@]}" -gt 0 ]; then
  echo "prova_motor: REPROVADO em ${#falhas[@]} de ${#GATES[@]}: ${falhas[*]}" >&2
  exit 1
fi
echo "prova_motor: APROVADO (${#GATES[@]} de ${#GATES[@]} gates)"
