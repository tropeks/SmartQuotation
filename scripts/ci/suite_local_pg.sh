#!/usr/bin/env bash
# "Teste local documentado" da suíte Django contra uma major específica do Postgres (ordem
# 009): sobe um Postgres EFÊMERO postgres:<major> via docker, roda `manage.py test apps`
# contra ele com as MESMAS variáveis que o job django-test do ci.yml usa, e derruba o
# container no final — sempre, sucesso ou falha. Prova localmente, antes do push, o que a
# matriz da CI (docs/patches/009-ci-postgres-matrix.patch) vai provar nos dois majors.
#
# Uso:
#   scripts/ci/suite_local_pg.sh 15
#   scripts/ci/suite_local_pg.sh 16 -v2 apps.quotations   # args extras passam para manage.py test
#
# Isolamento de PRODUÇÃO (não é meia-medida, é recusa dura):
#   - nunca monta volume nomeado (sem -v aqui: o Postgres efêmero não persiste nada);
#   - recusa se DB_CONTAINER coincidir com "sq-prod-db" (o container avulso de produção) ou
#     se algo apontar para o volume de produção "smartquotation_sq_postgres_data".
#   - a porta só é publicada em 127.0.0.1 (nunca 0.0.0.0): nada de fora do host alcança este
#     Postgres de teste, mesmo que a major/senha coincidissem com produção por acidente.
#
# Variáveis:
#   DOCKER              binário docker (default: docker)
#   DB_CONTAINER         nome do container efêmero (default: sq-ci-pg-<major>-<pid>-<epoch>;
#                        recusado se igual a "sq-prod-db")
#   POSTGRES_PORT        porta do host a publicar (default: uma porta livre escolhida agora)
#   POSTGRES_USER        default: sq
#   POSTGRES_DB          default: smartquotation
#   POSTGRES_PASSWORD    default: aleatória (gerada agora; só vale para este container efêmero)
#   PG_WAIT_SECONDS       espera máxima pelo pg_isready (default 60)
#   PG_POLL_INTERVAL      intervalo do poll (default 1)
#   PYTHON               interpretador a usar. Default: backend/.venv/bin/python se existir,
#                        senão python3 do PATH.
#   BACKEND_DIR          default: <repo>/backend
#
# Saída: imprime `SELECT version()` do servidor efêmero logo depois dele ficar pronto — a
# prova, no log, de que a major realmente usada é a pedida.

set -euo pipefail
umask 077

SQ_SCRIPT="suite_local_pg.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source-path=SCRIPTDIR/../lib source=../lib/backup_common.sh
. "${SCRIPT_DIR}/../lib/backup_common.sh"

DOCKER="${DOCKER:-docker}"
PG_MAJOR="${1:-}"
if [ "$#" -gt 0 ]; then shift; fi
if ! [[ "${PG_MAJOR}" =~ ^[0-9]+$ ]] || [ "${PG_MAJOR}" -lt 15 ] || [ "${PG_MAJOR}" -gt 17 ]; then
  echo "${SQ_SCRIPT}: uso: ${SQ_SCRIPT} <major 15|16|17> [args extras p/ manage.py test]" >&2
  echo "${SQ_SCRIPT}: major recebida: '${PG_MAJOR}' — só 15, 16 ou 17 são suportadas." >&2
  exit 1
fi

DB_CONTAINER="${DB_CONTAINER:-sq-ci-pg-${PG_MAJOR}-$$-$(date +%s)}"
POSTGRES_USER="${POSTGRES_USER:-sq}"
POSTGRES_DB="${POSTGRES_DB:-smartquotation}"
PG_WAIT_SECONDS="${PG_WAIT_SECONDS:-60}"
PG_POLL_INTERVAL="${PG_POLL_INTERVAL:-1}"
BACKEND_DIR="${BACKEND_DIR:-${REPO_ROOT}/backend}"

# Recusa dura: nunca aponta para o container ou o volume de PRODUÇÃO (docs/INFRASTRUCTURE.md
# — sq-prod-db, volume smartquotation_sq_postgres_data do docker-compose.prod.yml). Este
# script nunca declara -v, então a checagem de volume é uma segunda trava para quem tentar
# injetar um mount por fora (ex.: um DOCKER wrapper customizado).
FORBIDDEN_CONTAINER="sq-prod-db"
FORBIDDEN_VOLUME="smartquotation_sq_postgres_data"
if [ "${DB_CONTAINER}" = "${FORBIDDEN_CONTAINER}" ]; then
  echo "${SQ_SCRIPT}: DB_CONTAINER=${DB_CONTAINER} é o nome do container de PRODUÇÃO. Recusando." >&2
  exit 1
fi
if [ "${POSTGRES_VOLUME:-}" = "${FORBIDDEN_VOLUME}" ]; then
  echo "${SQ_SCRIPT}: ${FORBIDDEN_VOLUME} é o volume de PRODUÇÃO; este script não monta volume nomeado. Recusando." >&2
  exit 1
fi

if [ -n "${PYTHON:-}" ]; then
  : # respeita override explícito (inclusive dos testes)
elif [ -x "${BACKEND_DIR}/.venv/bin/python" ]; then
  PYTHON="${BACKEND_DIR}/.venv/bin/python"
else
  PYTHON="python3"
fi

free_port() {
  python3 - <<'PY'
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

HOST_PORT="${POSTGRES_PORT:-$(free_port)}"
# Aleatória e efêmera: nasce e morre com este container de teste, nunca é a senha de
# produção nem persiste em disco — ok expô-la em -e (mesmo padrão do docker-compose.yml
# de dev deste repo).
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"

sq_require_docker

cleanup() {
  ${DOCKER} rm -fv "${DB_CONTAINER}" >/dev/null 2>&1 || true
  sq_cleanup
}
trap cleanup EXIT INT TERM

echo "${SQ_SCRIPT}: subindo postgres:${PG_MAJOR} efêmero '${DB_CONTAINER}' em 127.0.0.1:${HOST_PORT} (--rm, sem volume nomeado)"
if ! ${DOCKER} run -d --rm --name "${DB_CONTAINER}" --label sq.suite-local-pg=1 \
      -e POSTGRES_DB="${POSTGRES_DB}" -e POSTGRES_USER="${POSTGRES_USER}" \
      -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
      -p "127.0.0.1:${HOST_PORT}:5432" \
      "postgres:${PG_MAJOR}" >/dev/null; then
  echo "${SQ_SCRIPT}: não consegui subir postgres:${PG_MAJOR} (imagem ausente? 'docker pull postgres:${PG_MAJOR}')." >&2
  exit 1
fi

waited=0
until ${DOCKER} exec "${DB_CONTAINER}" pg_isready -q -U "${POSTGRES_USER}" -h 127.0.0.1 >/dev/null 2>&1; do
  if [ "${waited}" -ge "${PG_WAIT_SECONDS}" ]; then
    echo "${SQ_SCRIPT}: postgres:${PG_MAJOR} não ficou pronto em ${PG_WAIT_SECONDS}s." >&2
    exit 1
  fi
  sleep "${PG_POLL_INTERVAL}"
  waited=$((waited + 1))
done

SERVER_VERSION="$(${DOCKER} exec "${DB_CONTAINER}" psql -X -tA -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c 'SELECT version();' 2>/dev/null || true)"
echo "${SQ_SCRIPT}: servidor efêmero pronto — SELECT version(): ${SERVER_VERSION}"

# Mesmas variáveis do job django-test do ci.yml (POSTGRES_HOST aqui é sempre 127.0.0.1: é o
# único lugar onde a porta foi publicada).
export DJANGO_SETTINGS_MODULE="smartquotation.settings.development"
export POSTGRES_HOST="127.0.0.1"
export POSTGRES_PORT="${HOST_PORT}"
export POSTGRES_USER
export POSTGRES_PASSWORD
export POSTGRES_DB

echo "${SQ_SCRIPT}: rodando 'manage.py test apps' em ${BACKEND_DIR} (${PYTHON}) contra postgres:${PG_MAJOR}"
cd "${BACKEND_DIR}"
"${PYTHON}" manage.py test apps "$@"

echo "${SQ_SCRIPT}: ok — suíte Django passou contra postgres:${PG_MAJOR}"
