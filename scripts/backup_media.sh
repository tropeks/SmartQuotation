#!/usr/bin/env bash
# Backup do volume de mídia (PDFs/DOCX de propostas) montado em /app/backend/media.
# Uso: BACKUP_DIR=/backups/sq ./scripts/backup_media.sh
# COMPOSE_FILE pode ser sobreposto via env (default: docker-compose.prod.yml).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${MEDIA_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
mkdir -p "${BACKUP_DIR}"

FINAL="${BACKUP_DIR}/media_$(date +%Y%m%d_%H%M%S).tar.gz"
TMPFILE="${FINAL}.tmp"

trap 'rm -f "${TMPFILE}"' EXIT INT TERM

docker compose -f "${COMPOSE_FILE}" exec -T web \
  tar czf - /app/backend/media \
  > "${TMPFILE}"

mv "${TMPFILE}" "${FINAL}"
