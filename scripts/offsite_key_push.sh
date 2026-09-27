#!/usr/bin/env bash
# Custódia off-site da FIELD_ENCRYPTION_KEY (ordem 003, decisão (b) do Diretor): objeto
# SEPARADO do dump, num remote DISTINTO, cifrado SÓ para a chave de recuperação da Quantum.
# Roda pelo backup_run.sh (sq-backup.service) depois do backup_key.sh e antes do
# offsite_push.sh. Falhar aqui NÃO impede o off-site do dump (o runner segue e a unit fica
# failed no fim): dump off-site tem valor mesmo sem a chave.
#
# O que faz:
#   1. Calcula o fingerprint (sha256 truncado em 16 hex, o mesmo do backup_key.sh) do
#      ${KEY_BACKUP_DIR}/field_encryption_key e compara com
#      ${KEY_BACKUP_DIR}/offsite_key_fingerprint. Igual: não reenvia, mas CONFERE (hashsum,
#      barato) que o objeto registrado ainda está no remote da chave com o hash registrado;
#      sumiu ou mudou = falha.
#   2. Mudou (ou é a primeira vez): cifra com age SÓ para OFFSITE_AGE_RECIPIENT_RECOVERY,
#      lendo o arquivo 0600 por stdin, e confere exatamente 1 stanza no cabeçalho, do tipo
#      do destinatário (X25519 para age1…, piv-p256 para age1yubikey1…; DP-41).
#   3. Envia para ${OFFSITE_KEY_REMOTE}/field_encryption_key.<fingerprint>.<UTC>.age com
#      `rclone copyto --immutable`, confere o hash remoto e só então grava
#      offsite_key_fingerprint e offsite_key_last_success (atômicos, 0600).
#
# A chave NUNCA passa por argv, env, log nem arquivo que não seja 0600: ela só é lida por
# redirecionamento de stdin para o age. O .age temporário fica no KEY_BACKUP_DIR (0700).
#
# Recusa (exit 1, antes de tocar em age ou rclone):
#   - OFFSITE_KEY_REMOTE igual ao OFFSITE_REMOTE, um dentro do outro, ou na MESMA seção do
#     rclone.conf (a chave tem bucket e credencial próprios);
#   - destinatário de recuperação ausente, privado (AGE-SECRET-KEY-…), identidade de plugin
#     (AGE-PLUGIN-YUBIKEY-…) ou fictício; YubiKey sem age-plugin-yubikey no PATH;
#   - arquivo da chave ausente ou legível por grupo/outros; KEY_BACKUP_DIR sobreposto ao
#     BACKUP_DIR.
# Nada é apagado no remoto (DP-27 aberta): versões antigas da chave ficam lá, e são elas que
# abrem os dumps antigos.
#
# Host novo (pós-desastre) com a mesma chave: não há offsite_key_fingerprint nem manifesto,
# e o age cifra com aleatoriedade — por isso o nome leva o timestamp UTC: sai um objeto NOVO
# (append), sem conflito com o antigo e sem sobrescrever nada.
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
sq_offsite_check_conf_separation "${OFFSITE_REMOTE}" "${OFFSITE_KEY_REMOTE}"
sq_offsite_check_tools
sq_offsite_check_plugins "${OFFSITE_AGE_RECIPIENT_RECOVERY}"

trap sq_cleanup EXIT INT TERM
sq_prune_orphan_tmp "${KEY_BACKUP_DIR}"

FPR="$(sha256sum < "${KEY_FILE}" | cut -c1-16)"
FPR_FILE="${KEY_BACKUP_DIR}/offsite_key_fingerprint"
MANIFEST="${KEY_BACKUP_DIR}/offsite_key_manifest"
LAST_FPR=""
LAST_OBJ=""
if [ -f "${FPR_FILE}" ]; then
  LAST_FPR="$(sed -n 's/^sha256_16=//p' "${FPR_FILE}")"
  LAST_OBJ="$(sed -n 's/^object=//p' "${FPR_FILE}")"
fi

if [ "${LAST_FPR}" = "${FPR}" ]; then
  # Chave inalterada: não reenvia, mas confere que a custódia ainda tem o objeto dela.
  [ -n "${LAST_OBJ}" ] || sq_die "offsite_key_fingerprint sem object=: não sei qual objeto conferir. Apague-o para reenviar a chave."
  ENTRY="$(sq_manifest_get "${MANIFEST}" "${LAST_OBJ}")"
  [ -n "${ENTRY}" ] || sq_die "${LAST_OBJ} não está no offsite_key_manifest: não há hash para conferir. Apague o offsite_key_fingerprint para reenviar a chave."
  sq_remote_hash "${OFFSITE_KEY_REMOTE%/}/${LAST_OBJ}" || exit 1
  if [ "${OFFSITE_HASH}:${REMOTE_HASH}" != "${ENTRY%%$'\t'*}" ]; then
    WHAT="sumiu"
    [ -z "${REMOTE_HASH}" ] || WHAT="tem outro hash"
    sq_die "FALHA — a chave atual (sha256 ${FPR}) não está mais na custódia off-site: ${OFFSITE_KEY_REMOTE%/}/${LAST_OBJ} ${WHAT}. Investigue; para reenviar, apague o offsite_key_fingerprint."
  fi
  echo "${SQ_SCRIPT}: chave inalterada (sha256 ${FPR}) — ${LAST_OBJ} conferido na custódia off-site, nada a enviar." >&2
  exit 0
fi

# Nome único: host novo com a mesma chave (sem manifesto) envia um objeto NOVO, nunca
# esbarra no antigo. Nanossegundos: duas execuções no mesmo segundo não colidem.
OBJ="field_encryption_key.${FPR}.$(date -u +%Y%m%dT%H%M%S.%NZ).age"
sq_offsite_push "${KEY_FILE}" "${OFFSITE_KEY_REMOTE}" "${OBJ}" \
  "${MANIFEST}" "${KEY_BACKUP_DIR}" "${OFFSITE_AGE_RECIPIENT_RECOVERY}"

NOW="$(sq_now_iso)"
sq_write_status "${KEY_BACKUP_DIR}/offsite_key_last_success" \
  "timestamp=${NOW}" "remote=${OFFSITE_KEY_REMOTE%/}" "object=${OBJ}" \
  "result=${PUSH_RESULT}" "bytes=${PUSH_BYTES}" "hash=${PUSH_HASH}" "key_sha256_16=${FPR}"
sq_write_status "${FPR_FILE}" "sha256_16=${FPR}" "object=${OBJ}"
echo "${SQ_SCRIPT}: ok — chave sha256 ${FPR} na custódia off-site (${OFFSITE_KEY_REMOTE%/}/${OBJ})" >&2
