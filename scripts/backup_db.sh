#!/usr/bin/env bash
# Dump do PostgreSQL via docker compose exec e comprime com gzip.
# Uso: POSTGRES_USER=sq POSTGRES_DB=smartquotation BACKUP_DIR=/backups/sq ./scripts/backup_db.sh
# COMPOSE_FILE pode ser sobreposto via env (default: docker-compose.prod.yml).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
mkdir -p "${BACKUP_DIR}"

FINAL="${BACKUP_DIR}/sq_$(date +%Y%m%d_%H%M%S).sql.gz"
TMPFILE="${FINAL}.tmp"

trap 'rm -f "${TMPFILE}"' EXIT INT TERM

docker compose -f "${COMPOSE_FILE}" exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "${TMPFILE}"

mv "${TMPFILE}" "${FINAL}"
