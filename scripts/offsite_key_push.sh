#!/usr/bin/env bash
# Custódia off-site da FIELD_ENCRYPTION_KEY (ordem 003, decisão (b) do Diretor): objeto
# SEPARADO do dump, num remote DISTINTO, cifrado SÓ para a chave de recuperação da Quantum.
# Roda na sq-backup.service depois do backup_key.sh e ANTES do offsite_push.sh: se a chave
# nova não chegar à custódia, o dump cifrado com ela também não sai.
#
# O que faz:
#   1. Calcula o fingerprint (sha256 truncado em 16 hex, o mesmo do backup_key.sh) do
#      ${KEY_BACKUP_DIR}/field_encryption_key e compara com
#      ${KEY_BACKUP_DIR}/offsite_key_fingerprint. Igual: nada a enviar (exit 0).
#   2. Mudou (ou é a primeira vez): cifra com age SÓ para OFFSITE_AGE_RECIPIENT_RECOVERY,
#      lendo o arquivo 0600 por stdin, e confere 1 stanza X25519 no cabeçalho.
#   3. Envia para ${OFFSITE_KEY_REMOTE}/field_encryption_key.<fingerprint>.age com
#      `rclone copyto --immutable`, confere o hash remoto e só então grava
#      offsite_key_fingerprint e offsite_key_last_success (atômicos, 0600).
#
# A chave NUNCA passa por argv, env, log nem arquivo que não seja 0600: ela só é lida por
# redirecionamento de stdin para o age. O .age temporário fica no KEY_BACKUP_DIR (0700).
#
# Recusa (exit 1, antes de tocar em age ou rclone):
#   - OFFSITE_KEY_REMOTE igual ao OFFSITE_REMOTE, um dentro do outro, ou na MESMA seção do
#     rclone.conf (a chave tem bucket e credencial próprios);
#   - destinatário de recuperação ausente, privado (AGE-SECRET-KEY-…) ou fictício;
#   - arquivo da chave ausente ou legível por grupo/outros; KEY_BACKUP_DIR sobreposto ao
#     BACKUP_DIR.
# Nada é apagado no remoto (DP-27 aberta): versões antigas da chave ficam lá, e são elas que
# abrem os dumps antigos.
#
# Variáveis: KEY_BACKUP_DIR, BACKUP_DIR, OFFSITE_REMOTE, OFFSITE_KEY_REMOTE,
# OFFSITE_AGE_RECIPIENT_RECOVERY, OFFSITE_HASH, OFFSITE_HASH_DOWNLOAD, RCLONE_CONFIG,
# RCLONE_CACHE_DIR, AGE, RCLONE — mesmos significados do offsite_push.sh.

set -euo pipefail
umask 077

SQ_SCRIPT="offsite_key_push.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"
# shellcheck source-path=SCRIPTDIR source=lib/offsite_common.sh
. "${SCRIPT_DIR}/lib/offsite_common.sh"

KEY_BACKUP_DIR="${KEY_BACKUP_DIR:-/var/lib/smartquotation/key-backup}"
BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
OFFSITE_REMOTE="${OFFSITE_REMOTE:-}"
OFFSITE_KEY_REMOTE="${OFFSITE_KEY_REMOTE:-}"
OFFSITE_AGE_RECIPIENT_RECOVERY="${OFFSITE_AGE_RECIPIENT_RECOVERY:-}"
OFFSITE_HASH="${OFFSITE_HASH:-sha1}"
OFFSITE_HASH_DOWNLOAD="${OFFSITE_HASH_DOWNLOAD:-0}"
AGE="${AGE:-age}"
RCLONE="${RCLONE:-rclone}"

sq_offsite_check_recipient OFFSITE_AGE_RECIPIENT_RECOVERY
sq_offsite_check_remote OFFSITE_KEY_REMOTE
sq_offsite_check_remote OFFSITE_REMOTE
sq_offsite_check_separate "${OFFSITE_REMOTE}" "${OFFSITE_KEY_REMOTE}"
sq_check_dirs_disjoint "${KEY_BACKUP_DIR}" "${BACKUP_DIR}"

KEY_FILE="${KEY_BACKUP_DIR}/field_encryption_key"
if [ ! -f "${KEY_FILE}" ]; then
  sq_die "${KEY_FILE} não existe: o backup_key.sh rodou? Recusando."
fi
KEY_PERM="$(stat -c '%a' -- "${KEY_FILE}")"
if (( 8#${KEY_PERM} & 8#077 )); then
  sq_die "${KEY_FILE} tem modo ${KEY_PERM}: a chave só pode estar em arquivo 0600. Recusando."
fi
sq_offsite_check_rclone_config
sq_offsite_check_tools

trap sq_cleanup EXIT INT TERM
sq_prune_orphan_tmp "${KEY_BACKUP_DIR}"

FPR="$(sha256sum < "${KEY_FILE}" | cut -c1-16)"
FPR_FILE="${KEY_BACKUP_DIR}/offsite_key_fingerprint"
LAST_FPR=""
if [ -f "${FPR_FILE}" ]; then
  LAST_FPR="$(sed -n 's/^sha256_16=//p' "${FPR_FILE}")"
fi
if [ "${LAST_FPR}" = "${FPR}" ]; then
  echo "${SQ_SCRIPT}: chave inalterada (sha256 ${FPR}) — já está na custódia off-site, nada a enviar." >&2
  exit 0
fi

OBJ="field_encryption_key.${FPR}.age"
sq_offsite_push "${KEY_FILE}" "${OFFSITE_KEY_REMOTE}" "${OBJ}" \
  "${KEY_BACKUP_DIR}/offsite_key_manifest" "${KEY_BACKUP_DIR}" "${OFFSITE_AGE_RECIPIENT_RECOVERY}"

NOW="$(sq_now_iso)"
sq_write_status "${KEY_BACKUP_DIR}/offsite_key_last_success" \
  "timestamp=${NOW}" "remote=${OFFSITE_KEY_REMOTE%/}" "object=${OBJ}" \
  "result=${PUSH_RESULT}" "bytes=${PUSH_BYTES}" "hash=${PUSH_HASH}" "key_sha256_16=${FPR}"
sq_write_status "${FPR_FILE}" "sha256_16=${FPR}"
echo "${SQ_SCRIPT}: ok — chave sha256 ${FPR} na custódia off-site (${OFFSITE_KEY_REMOTE%/}/${OBJ})" >&2
