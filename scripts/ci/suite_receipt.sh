#!/usr/bin/env bash
# Prova de suíte do HEAD: o rótulo `suite` do `.maestro.yaml`.
#
# Por que a prova é o run verde da CI, e não a suíte rodada aqui: a suíte Django é
# multi-tenant (django-tenants, TenantTestCase) e precisa de Postgres, e o PDF da proposta
# precisa das libs do WeasyPrint. A forge não tem docker nem Postgres local; subir a stack
# seria prova de lab, e o run headless não entra na lab. O job `django-test` do `ci.yml`
# já roda a suíte num runner efêmero com Postgres 16, no mesmo SHA. Padrão herdado do
# NetForge (ordem 021, `scripts/ci/suite_receipt.sh` de lá).
#
# O que este script faz, e o que ele NUNCA faz:
#   - prova o HEAD: árvore limpa e HEAD alcançável de algum ref remoto depois de
#     `git fetch -q`. Nunca usa `@{u}`, que falha em HEAD destacado.
#   - acha, via `gh`, o run MAIS RECENTE do workflow `CI` com `headSha` igual ao HEAD e
#     reprova se ele não existir, não estiver `completed`, não for `success`, ou se
#     qualquer job obrigatório não for `success` (`skipped` e `cancelled` reprovam).
#   - NUNCA espera nem faz polling: run em curso reprova, com instrução de rodar de novo.
#   - falha do `gh` (sem auth, sem rede, JSON inválido) é exit != 0, nunca verde por omissão.
#
# `docker-build` não é obrigatório: o `ci.yml` só o roda em push/PR para a main.
set -euo pipefail

JOBS_OBRIGATORIOS=(
  "Motor de custeio (gate -10%)"
  "Testes de ops/infra (backup + media volume)"
  "pip-audit (CVEs nos locks)"
  "Django check + migrations"
  "Testes Django (multi-tenant)"
)

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
  echo "suite_receipt: $*" >&2
  exit 1
}

if [ -n "$(git status --porcelain)" ]; then
  fail "árvore suja ('git status --porcelain' não vazio): commite ou descarte antes. A prova fala do conteúdo exato que a CI viu."
fi

HEAD_SHA="$(git rev-parse HEAD)"

if ! FETCH_ERR="$(git fetch -q 2>&1)"; then
  fail "'git fetch' falhou, não dá para confirmar que o HEAD chegou a um remoto:
$FETCH_ERR"
fi

if [ -z "$(git branch -r --contains "$HEAD_SHA" 2>/dev/null || true)" ]; then
  fail "HEAD ($HEAD_SHA) não é alcançável de nenhum ref remoto: commit não empurrado? A CI só vê o que chegou ao remoto."
fi

if ! gh run list --workflow CI --commit "$HEAD_SHA" \
      --json databaseId,status,conclusion,headSha,createdAt \
      >"$TMP_DIR/runs.json" 2>"$TMP_DIR/runs.err"; then
  fail "'gh run list' falhou:
$(cat "$TMP_DIR/runs.err")"
fi

if ! RUN_ID="$(python3 - "$TMP_DIR/runs.json" "$HEAD_SHA" <<'PY'
import json
import sys

path, head_sha = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        runs = json.load(f)
except json.JSONDecodeError as e:
    sys.exit(f"JSON inválido de 'gh run list': {e}")
runs = [r for r in runs if r.get("headSha") == head_sha]
if not runs:
    sys.exit(f"nenhum run do workflow CI para o SHA {head_sha}")
runs.sort(key=lambda r: r.get("createdAt", ""))
print(runs[-1]["databaseId"])
PY
)"; then
  fail "não foi possível escolher o run de $HEAD_SHA (veja a mensagem acima)"
fi

if ! gh run view "$RUN_ID" --json jobs,conclusion,status,headSha,url,databaseId \
      >"$TMP_DIR/run.json" 2>"$TMP_DIR/run.err"; then
  fail "'gh run view $RUN_ID' falhou:
$(cat "$TMP_DIR/run.err")"
fi

python3 - "$TMP_DIR/run.json" "$HEAD_SHA" "${JOBS_OBRIGATORIOS[@]}" <<'PY'
import json
import sys

path, head_sha, *required = sys.argv[1:]
try:
    with open(path) as f:
        run = json.load(f)
except json.JSONDecodeError as e:
    sys.exit(f"JSON inválido de 'gh run view': {e}")

by_name = {j.get("name"): j for j in run.get("jobs", [])}
print(f"run: {run.get('databaseId')}")
print(f"url: {run.get('url', '')}")
print(f"headSha: {run.get('headSha', '')}")
print(f"status: {run.get('status')}")
print(f"conclusion: {run.get('conclusion')}")
print("jobs:")
for name in sorted(by_name):
    j = by_name[name]
    print(f"  {name}: {j.get('conclusion')} (status={j.get('status')})")

problems = []
if run.get("headSha") != head_sha:
    problems.append(f"headSha do run ({run.get('headSha')}) difere do HEAD ({head_sha})")
if run.get("status") != "completed":
    problems.append(
        f"run ainda não terminou (status={run.get('status')}): sem espera aqui, "
        "rode de novo quando ele concluir"
    )
elif run.get("conclusion") != "success":
    problems.append(f"conclusion do run = '{run.get('conclusion')}' (esperado 'success')")
for name in required:
    j = by_name.get(name)
    if j is None:
        problems.append(f"job obrigatório ausente do run: '{name}'")
    elif j.get("conclusion") != "success":
        problems.append(f"job obrigatório '{name}' concluiu como '{j.get('conclusion')}'")

if problems:
    print("REPROVADO:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("APROVADO: suite verde no HEAD.")
PY
