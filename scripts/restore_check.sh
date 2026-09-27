#!/usr/bin/env bash
# Drill de restore: prova que o backup mais recente RESTAURA, não só que existe.
#
# O que faz:
#   1. Sobe um Postgres efêmero (${RESTORE_IMAGE}, default postgres:15 — mesma major da
#      produção) com --network none e --rm, nome único; auth trust (sem rede, sem senha).
#   2. Espera ficar pronto (pg_isready em 127.0.0.1: só responde depois do init da imagem).
#   3. Aplica o dump mais recente (${BACKUP_DIR}/sq_*.sql.gz) via psql. Erros do psql são só
#      CONTADOS (ex.: "role já existe" é esperado num pg_dumpall); quem decide são as checagens.
#   4. Confere: schema ${RESTORE_SCHEMA} existe; tabelas-chave presentes; contagem de
#      ${RESTORE_SCHEMA}.quotations_quotation >= ${RESTORE_MIN_QUOTATIONS}.
#   5. Valida o tar de mídia mais recente (gzip íntegro, tar tzf, entradas sob app/backend/media).
#   6. Grava ${BACKUP_DIR}/restore_last_success (só no sucesso).
# O container é SEMPRE destruído (trap), inclusive em erro no meio.
#
# Saída: só contagens e nomes de tabela. Nenhuma linha do dump, nenhuma mensagem do psql
# (que pode citar conteúdo em CONTEXT) é repassada.
#
# Variáveis:
#   BACKUP_DIR / POSTGRES_BACKUP_DIR  onde estão dump e mídia (default /backups/sq)
#   RESTORE_IMAGE           imagem do Postgres efêmero (default postgres:15)
#   RESTORE_DB              banco a conferir (default ${POSTGRES_DB:-smartquotation})
#   RESTORE_SCHEMA          schema do tenant (default engematex)
#   RESTORE_TABLES          tabelas obrigatórias no schema (default abaixo)
#   RESTORE_MIN_QUOTATIONS  mínimo de linhas em quotations_quotation (default 1)
#   RESTORE_WAIT_SECONDS    espera máxima pelo Postgres (default 90)
#   RESTORE_CHECK_MEDIA     1 valida também o tar de mídia (default 1)
#   MEDIA_ALLOW_EMPTY       1 aceita tar de mídia só com o diretório (default 0)
#   DOCKER                  binário docker (default docker)

set -euo pipefail
umask 077

SQ_SCRIPT="restore_check.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
RESTORE_IMAGE="${RESTORE_IMAGE:-postgres:15}"
RESTORE_DB="${RESTORE_DB:-${POSTGRES_DB:-smartquotation}}"
RESTORE_SCHEMA="${RESTORE_SCHEMA:-engematex}"
RESTORE_TABLES="${RESTORE_TABLES:-quotations_quotation quotations_quotationitem materials_material materials_materialprice}"
RESTORE_MIN_QUOTATIONS="${RESTORE_MIN_QUOTATIONS:-1}"
RESTORE_WAIT_SECONDS="${RESTORE_WAIT_SECONDS:-90}"
RESTORE_POLL_INTERVAL="${RESTORE_POLL_INTERVAL:-1}"
RESTORE_CHECK_MEDIA="${RESTORE_CHECK_MEDIA:-1}"
MEDIA_ALLOW_EMPTY="${MEDIA_ALLOW_EMPTY:-0}"
DOCKER="${DOCKER:-docker}"

# Tudo que entra em SQL é identificador validado por lista branca (não há bind aqui).
IDENT='^[a-z_][a-z0-9_]*$'
for v in "${RESTORE_SCHEMA}" "${RESTORE_DB}" ${RESTORE_TABLES}; do
  if ! [[ "${v}" =~ ${IDENT} ]]; then
    echo "${SQ_SCRIPT}: identificador inválido em RESTORE_SCHEMA/RESTORE_DB/RESTORE_TABLES. Recusando." >&2
    exit 1
  fi
done
for v in "${RESTORE_MIN_QUOTATIONS}" "${RESTORE_WAIT_SECONDS}" "${RESTORE_POLL_INTERVAL}"; do
  if ! [[ "${v}" =~ ^[0-9]+$ ]]; then
    echo "${SQ_SCRIPT}: RESTORE_MIN_QUOTATIONS/RESTORE_WAIT_SECONDS/RESTORE_POLL_INTERVAL têm que ser inteiros." >&2
    exit 1
  fi
done

newest() {
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name "$1" 2>/dev/null | LC_ALL=C sort | tail -n 1
}

DUMP="$(newest 'sq_*.sql.gz')"
if [ -z "${DUMP}" ]; then
  echo "${SQ_SCRIPT}: nenhum dump sq_*.sql.gz em ${BACKUP_DIR}." >&2
  exit 1
fi
if ! gzip -t "${DUMP}" 2>/dev/null; then
  echo "${SQ_SCRIPT}: $(basename -- "${DUMP}") não é gzip íntegro." >&2
  exit 1
fi

MEDIA=""
MEDIA_ENTRIES="-"
if [ "${RESTORE_CHECK_MEDIA}" = "1" ]; then
  MEDIA="$(newest 'media_*.tar.gz')"
  if [ -z "${MEDIA}" ]; then
    echo "${SQ_SCRIPT}: nenhum media_*.tar.gz em ${BACKUP_DIR} (RESTORE_CHECK_MEDIA=0 desliga)." >&2
    exit 1
  fi
fi

sq_require_docker

NAME="sq-restore-check-$(date +%Y%m%d%H%M%S)-$$"
WORK="$(mktemp -d)"
cleanup() {
  ${DOCKER} rm -f "${NAME}" >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT INT TERM

START="$(date +%s)"
echo "${SQ_SCRIPT}: dump $(basename -- "${DUMP}") → container efêmero ${NAME} (${RESTORE_IMAGE}, --network none)"

if ! ${DOCKER} run -d --rm --network none --name "${NAME}" --label sq.restore-check=1 \
      -e POSTGRES_HOST_AUTH_METHOD=trust "${RESTORE_IMAGE}" >/dev/null; then
  echo "${SQ_SCRIPT}: não consegui subir ${RESTORE_IMAGE} (imagem ausente? faça 'docker pull ${RESTORE_IMAGE}' na instalação)." >&2
  exit 1
fi

waited=0
until ${DOCKER} exec "${NAME}" pg_isready -q -U postgres -h 127.0.0.1 >/dev/null 2>&1; do
  if [ "${waited}" -ge "${RESTORE_WAIT_SECONDS}" ]; then
    echo "${SQ_SCRIPT}: Postgres efêmero não ficou pronto em ${RESTORE_WAIT_SECONDS}s." >&2
    exit 1
  fi
  sleep "${RESTORE_POLL_INTERVAL}"
  waited=$((waited + 1))
done

# Restore. stdout e stderr do psql NÃO saem daqui: o stderr pode citar linha de dado.
zcat "${DUMP}" | ${DOCKER} exec -i "${NAME}" psql -X -q -U postgres -d postgres \
  -v ON_ERROR_STOP=0 >/dev/null 2>"${WORK}/psql.err" || true
PSQL_ERRORS="$(grep -c 'ERROR:' "${WORK}/psql.err" || true)"
echo "${SQ_SCRIPT}: dump aplicado; ${PSQL_ERRORS} erro(s) do psql (contados, não exibidos — num pg_dumpall, 'role já existe' é esperado)"

q() {
  ${DOCKER} exec "${NAME}" psql -X -tA -U postgres -d "${RESTORE_DB}" -c "$1" 2>/dev/null | tr -d '[:space:]'
}

FAILED=0
SCHEMA_OK="$(q "SELECT count(*) FROM information_schema.schemata WHERE schema_name = '${RESTORE_SCHEMA}'" || true)"
if [ "${SCHEMA_OK}" != "1" ]; then
  echo "${SQ_SCRIPT}: FALHA — schema ${RESTORE_SCHEMA} ausente no banco ${RESTORE_DB} restaurado." >&2
  exit 1
fi
echo "${SQ_SCRIPT}: schema ${RESTORE_SCHEMA}: presente"

for t in ${RESTORE_TABLES}; do
  present="$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${RESTORE_SCHEMA}' AND table_name = '${t}'" || true)"
  if [ "${present}" = "1" ]; then
    echo "${SQ_SCRIPT}: tabela ${RESTORE_SCHEMA}.${t}: presente"
  else
    echo "${SQ_SCRIPT}: FALHA — tabela ${RESTORE_SCHEMA}.${t} ausente." >&2
    FAILED=1
  fi
done
[ "${FAILED}" -eq 0 ] || exit 1

QCOUNT="$(q "SELECT count(*) FROM ${RESTORE_SCHEMA}.quotations_quotation" || true)"
if ! [[ "${QCOUNT}" =~ ^[0-9]+$ ]]; then
  echo "${SQ_SCRIPT}: FALHA — não consegui contar ${RESTORE_SCHEMA}.quotations_quotation." >&2
  exit 1
fi
echo "${SQ_SCRIPT}: ${RESTORE_SCHEMA}.quotations_quotation: ${QCOUNT} linha(s) (mínimo ${RESTORE_MIN_QUOTATIONS})"
if [ "${QCOUNT}" -lt "${RESTORE_MIN_QUOTATIONS}" ]; then
  echo "${SQ_SCRIPT}: FALHA — cotações abaixo do mínimo." >&2
  exit 1
fi

if [ -n "${MEDIA}" ]; then
  if ! gzip -t "${MEDIA}" 2>/dev/null || ! tar tzf "${MEDIA}" > "${WORK}/media.list" 2>/dev/null; then
    echo "${SQ_SCRIPT}: FALHA — $(basename -- "${MEDIA}") ilegível (gzip/tar)." >&2
    exit 1
  fi
  if ! grep -q -x -E 'app/backend/media/?' "${WORK}/media.list"; then
    echo "${SQ_SCRIPT}: FALHA — $(basename -- "${MEDIA}") não contém app/backend/media/." >&2
    exit 1
  fi
  MEDIA_ENTRIES="$(grep -c -E '^app/backend/media/.+' "${WORK}/media.list" || true)"
  if [ "${MEDIA_ENTRIES}" -eq 0 ] && [ "${MEDIA_ALLOW_EMPTY}" != "1" ]; then
    echo "${SQ_SCRIPT}: FALHA — $(basename -- "${MEDIA}") sem nenhuma entrada sob app/backend/media/." >&2
    exit 1
  fi
  echo "${SQ_SCRIPT}: mídia $(basename -- "${MEDIA}"): ${MEDIA_ENTRIES} entrada(s)"
fi

DURATION=$(( $(date +%s) - START ))
sq_write_status "${BACKUP_DIR}/restore_last_success" \
  "timestamp=$(sq_now_iso)" \
  "dump=$(basename -- "${DUMP}")" \
  "schema=${RESTORE_SCHEMA}" \
  "quotations=${QCOUNT}" \
  "tables=${RESTORE_TABLES// /,}" \
  "psql_errors=${PSQL_ERRORS}" \
  "media=$( [ -n "${MEDIA}" ] && basename -- "${MEDIA}" || echo - )" \
  "media_entries=${MEDIA_ENTRIES}" \
  "duration_s=${DURATION}"

echo "${SQ_SCRIPT}: ok — restore verificado em ${DURATION}s"
