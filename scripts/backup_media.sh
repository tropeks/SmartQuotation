#!/usr/bin/env bash
# Backup do volume de mídia (PDFs/DOCX de propostas) montado em /app/backend/media.
# Uso: BACKUP_DIR=/backups/sq ./scripts/backup_media.sh
# COMPOSE_FILE pode ser sobreposto via env (default: docker-compose.prod.yml).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${MEDIA_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
mkdir -p "${BACKUP_DIR}"

docker compose -f "${COMPOSE_FILE}" exec -T web \
  tar czf - /app/backend/media \
  > "${BACKUP_DIR}/media_$(date +%Y%m%d_%H%M%S).tar.gz"
