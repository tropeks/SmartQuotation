#!/usr/bin/env bash
# Backup do volume de mídia (PDFs/DOCX de propostas) montado em /app/backend/media.
#
# Modos (mesma lógica do backup_db.sh):
#   - "container": docker exec no container avulso da app (produção real: `sq-web-proto`,
#     sem docker-compose; o volume nomeado de mídia está montado em /app/backend/media).
#   - "compose":   docker compose -f ${COMPOSE_FILE} exec -T web (ambientes com compose).
# BACKUP_MODE=auto (default) usa "container" se ${MEDIA_CONTAINER} estiver RODANDO, "compose"
# se ele não existir, e FALHA se ele existir parado. Docker inacessível falha na hora.
#
# Uso: BACKUP_DIR=/backups/sq ./scripts/backup_media.sh
#
# Variáveis:
#   BACKUP_DIR / MEDIA_BACKUP_DIR  destino (default /backups/sq)
#   MEDIA_CONTAINER       container avulso da app (default: sq-web-proto)
#   COMPOSE_FILE          arquivo compose do modo compose (default: docker-compose.prod.yml)
#   WEB_SERVICE           serviço da app no compose (default: web)
#   DOCKER                binário docker (default: docker)
#   BACKUP_MODE           auto | container | compose
#   MEDIA_ALLOW_EMPTY     1 aceita mídia vazia (só o diretório). Default 0: produção tem
#                         propostas, e um tar sem nenhum arquivo é sinal de volume errado.
#   BACKUP_RETENTION_DAYS poda media_*.tar.gz com mais de N dias (default 14; 0 desliga),
#                         só depois de um backup novo validado, nunca o novo.
#
# Validação por CONTEÚDO (não por exit code): gzip íntegro, `tar tzf` lê o arquivo inteiro,
# o diretório app/backend/media está lá e há ≥1 entrada sob ele (ou MEDIA_ALLOW_EMPTY=1).
# Sucesso grava ${BACKUP_DIR}/media_last_success (timestamp, arquivo, bytes, entradas).

set -euo pipefail
umask 077

SQ_SCRIPT="backup_media.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"

MEDIA_PATH="/app/backend/media"
BACKUP_DIR="${BACKUP_DIR:-${MEDIA_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
WEB_SERVICE="${WEB_SERVICE:-web}"
MEDIA_CONTAINER="${MEDIA_CONTAINER:-sq-web-proto}"
DOCKER="${DOCKER:-docker}"
BACKUP_MODE="${BACKUP_MODE:-auto}"
MEDIA_ALLOW_EMPTY="${MEDIA_ALLOW_EMPTY:-0}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

sq_check_retention "${BACKUP_RETENTION_DAYS}"

mkdir -p "${BACKUP_DIR}"

FINAL="${BACKUP_DIR}/media_$(date +%Y%m%d_%H%M%S).tar.gz"
TMPFILE="${FINAL}.tmp"

sq_track_tmp "${TMPFILE}"
trap sq_cleanup EXIT INT TERM
sq_prune_orphan_tmp "${BACKUP_DIR}"

sq_require_docker

MODE="${BACKUP_MODE}"
if [ "${MODE}" = "auto" ]; then
  case "$(sq_container_state "${MEDIA_CONTAINER}")" in
    running)
      MODE="container"
      echo "${SQ_SCRIPT}: modo=container (auto-detectado — container '${MEDIA_CONTAINER}' rodando)" >&2 ;;
    stopped)
      echo "${SQ_SCRIPT}: container '${MEDIA_CONTAINER}' existe mas está PARADO — sem de onde ler a mídia." >&2
      exit 1 ;;
    *)
      MODE="compose"
      echo "${SQ_SCRIPT}: modo=compose (auto-detectado — container '${MEDIA_CONTAINER}' não encontrado;" \
           "usando docker compose -f ${COMPOSE_FILE}, serviço '${WEB_SERVICE}')" >&2 ;;
  esac
else
  echo "${SQ_SCRIPT}: modo=${MODE} (forçado via BACKUP_MODE)" >&2
fi

# -C / + caminho relativo: o tar não reclama de "/" inicial e o restore é `tar xzf - -C /`.
# Exit 1 do GNU tar = "file changed as we read it" (proposta gravada durante o backup): é
# AVISO, porque a validação por conteúdo logo abaixo decide. Exit > 1 é erro de verdade.
TAR_RC=0
case "${MODE}" in
  container)
    ${DOCKER} exec "${MEDIA_CONTAINER}" tar czf - -C / "${MEDIA_PATH#/}" > "${TMPFILE}" || TAR_RC=$? ;;
  compose)
    ${DOCKER} compose -f "${COMPOSE_FILE}" exec -T "${WEB_SERVICE}" \
      tar czf - -C / "${MEDIA_PATH#/}" > "${TMPFILE}" || TAR_RC=$? ;;
  *)
    echo "${SQ_SCRIPT}: BACKUP_MODE inválido: '${MODE}' (use auto|container|compose)" >&2
    exit 1 ;;
esac
if [ "${TAR_RC}" -eq 1 ]; then
  echo "${SQ_SCRIPT}: aviso — tar saiu 1 (arquivo mudou durante a leitura); a validação por conteúdo decide." >&2
elif [ "${TAR_RC}" -gt 1 ]; then
  echo "${SQ_SCRIPT}: tar/docker exec falhou (exit ${TAR_RC}). Rejeitando backup." >&2
  exit 1
fi

# --- Validação por conteúdo ---
# A listagem vai para arquivo 0600 (no trap), não para variável + pipe: com `grep -q` saindo
# no primeiro match, um `printf | grep -q` de listagem > 64 KiB leva SIGPIPE e, sob
# pipefail, vira vermelho falso justamente na mídia grande.
LISTING="${TMPFILE}.list"
sq_track_tmp "${LISTING}"
if ! gzip -t "${TMPFILE}" 2>/dev/null; then
  echo "${SQ_SCRIPT}: arquivo não é gzip íntegro. Rejeitando backup." >&2
  exit 1
fi
if ! tar tzf "${TMPFILE}" > "${LISTING}" 2>/dev/null; then
  echo "${SQ_SCRIPT}: tar ilegível (tar tzf falhou). Rejeitando backup." >&2
  exit 1
fi
REL="${MEDIA_PATH#/}"
if ! grep -q -x -E "${REL}/?" "${LISTING}"; then
  echo "${SQ_SCRIPT}: o tar não contém ${REL}/ — volume de mídia errado ou ausente. Rejeitando backup." >&2
  exit 1
fi
ENTRIES="$(grep -c -E "^${REL}/.+" "${LISTING}" || true)"
if [ "${ENTRIES}" -eq 0 ]; then
  if [ "${MEDIA_ALLOW_EMPTY}" = "1" ]; then
    echo "${SQ_SCRIPT}: mídia VAZIA (aceita por MEDIA_ALLOW_EMPTY=1)." >&2
  else
    echo "${SQ_SCRIPT}: ${REL}/ está vazio — defina MEDIA_ALLOW_EMPTY=1 se isso for esperado. Rejeitando backup." >&2
    exit 1
  fi
fi

chmod 600 "${TMPFILE}"
mv "${TMPFILE}" "${FINAL}"

BYTES="$(wc -c < "${FINAL}" | tr -d ' ')"
sq_write_status "${BACKUP_DIR}/media_last_success" \
  "timestamp=$(sq_now_iso)" \
  "file=$(basename -- "${FINAL}")" \
  "bytes=${BYTES}" \
  "entries=${ENTRIES}"

sq_prune "${BACKUP_DIR}" 'media_*.tar.gz' "${BACKUP_RETENTION_DAYS}" "${FINAL}"

echo "${SQ_SCRIPT}: ok — $(basename -- "${FINAL}") (${BYTES} bytes, ${ENTRIES} entradas)" >&2
