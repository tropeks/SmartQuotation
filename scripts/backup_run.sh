#!/usr/bin/env bash
# Runner do backup diário (sq-backup.service): executa TODAS as etapas em ordem, CONTINUA
# depois de falha e sai != 0 no fim se alguma falhou (a unit fica failed, visível).
#
# Por que não vários ExecStart=: com eles o systemd para na primeira falha. Aqui as etapas
# são independentes o bastante para valer a pena seguir:
#   - backup_key falhou (container parado, prova ruim)? O off-site do dump tem valor mesmo
#     sem a chave, e a chave anterior já está na custódia.
#   - offsite_key_push falhou (remote da chave fora)? O dump sai do mesmo jeito.
#   - backup_db falhou? O offsite_push roda sobre o que houver: o backfill leva o que ainda
#     não foi, e o offsite_last_success NÃO renova sobre dump velho (OFFSITE_MAX_AGE_HOURS).
#
# Ordem: backup_db → backup_media → backup_key → offsite_key_push → offsite_push.
# Registro: cada etapa com o exit code no journal e em ${BACKUP_DIR}/backup_run_last
# (atômico, 0600): timestamp, uma linha <etapa>=<exit>, failed=<lista>.

set -euo pipefail
umask 077

SQ_SCRIPT="backup_run.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
STEPS=(backup_db backup_media backup_key offsite_key_push offsite_push)

trap sq_cleanup EXIT INT TERM

RESULTS=()
FAILED=()
for step in "${STEPS[@]}"; do
  echo "${SQ_SCRIPT}: ── ${step} ──" >&2
  rc=0
  "${SCRIPT_DIR}/${step}.sh" || rc=$?
  RESULTS+=("${step}=${rc}")
  if [ "${rc}" -ne 0 ]; then
    FAILED+=("${step}")
    echo "${SQ_SCRIPT}: ${step} FALHOU (exit ${rc}) — seguindo com as próximas etapas." >&2
  fi
done

mkdir -p "${BACKUP_DIR}"
FAILED_LIST="$(IFS=,; echo "${FAILED[*]:-}")"
sq_write_status "${BACKUP_DIR}/backup_run_last" \
  "timestamp=$(sq_now_iso)" "${RESULTS[@]}" "failed=${FAILED_LIST:--}"

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "${SQ_SCRIPT}: FALHA — etapa(s) com erro: ${FAILED_LIST}. A unit fica failed." >&2
  exit 1
fi
echo "${SQ_SCRIPT}: ok — todas as etapas verdes." >&2
