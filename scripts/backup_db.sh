#!/usr/bin/env bash
# Dump do PostgreSQL via docker exec e comprime com gzip.
# Uso: POSTGRES_USER=sq POSTGRES_DB=smartquotation BACKUP_DIR=/backups/sq ./scripts/backup_db.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
mkdir -p "${BACKUP_DIR}"

docker exec smartquotation-db-1 pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "${BACKUP_DIR}/sq_$(date +%Y%m%d_%H%M%S).sql.gz"
