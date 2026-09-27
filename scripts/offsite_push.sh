#!/usr/bin/env bash
# Cópia OFF-SITE cifrada da série de backup (ordem 003): o dump e o tar de mídia mais
# recentes, cifrados com age, enviados com rclone. Roda na sq-backup.service DEPOIS de
# backup_db.sh, backup_media.sh, backup_key.sh e offsite_key_push.sh.
#
# O que faz, para o dump (${BACKUP_DIR}/sq_*.sql.gz) e a mídia (media_*.tar.gz) mais novos:
#   1. Cifra com age para DOIS destinatários: a chave pública da instância
#      (OFFSITE_AGE_RECIPIENT_INSTANCE) e a de recuperação da Quantum
#      (OFFSITE_AGE_RECIPIENT_RECOVERY, raiz offline no YubiKey, DP-41). O arquivo sai por
#      stdin para o age, e o .age vai para um temporário 0600 no próprio BACKUP_DIR,
#      apagado pelo trap.
#   2. Confere o cabeçalho age: exatamente 2 stanzas "-> X25519". Senão, não envia.
#   3. Envia com `rclone copyto --immutable` para ${OFFSITE_REMOTE}/<arquivo>.age.
#   4. Confere o hash remoto (rclone hashsum ${OFFSITE_HASH}) contra o hash local do .age.
#   5. Só com os dois conferidos grava ${BACKUP_DIR}/offsite_last_success (atômico, 0600).
#
# Idempotência: o age cifra com aleatoriedade, então recifrar dá outro hash. Cada .age
# conferido entra em ${BACKUP_DIR}/offsite_manifest (objeto, hash, bytes). Objeto remoto que
# já existe com o hash registrado é pulado; com qualquer outro hash, é FALHA: objeto remoto
# nunca é sobrescrito (e o --immutable faz o rclone recusar também).
#
# O que NÃO faz:
#   - não escolhe provedor: OFFSITE_REMOTE é "secao:bucket/prefixo" do rclone.conf;
#   - não apaga nada no remoto (nem delete, nem purge, nem sync): enquanto a DP-27 (retenção
#     NR-13) estiver aberta, não há poda remota por rotina;
#   - não leva a FIELD_ENCRYPTION_KEY nem o .env.prod: só os arquivos sq_*.sql.gz e
#     media_*.tar.gz saem daqui. A chave vai pelo offsite_key_push.sh, para outro remote.
#
# O host guarda SÓ chaves públicas. Destinatário com cara de chave privada
# (AGE-SECRET-KEY-…), ausente, repetido ou com o valor fictício do exemplo: recusado.
#
# Variáveis:
#   BACKUP_DIR / POSTGRES_BACKUP_DIR   onde estão dump e mídia (default /backups/sq)
#   KEY_BACKUP_DIR                     só para conferir que não se sobrepõe ao BACKUP_DIR
#   OFFSITE_REMOTE                     destino do dump e da mídia (obrigatório)
#   OFFSITE_KEY_REMOTE                 se definido, conferido como distinto do OFFSITE_REMOTE
#   OFFSITE_AGE_RECIPIENT_INSTANCE     chave pública age da instância (obrigatória)
#   OFFSITE_AGE_RECIPIENT_RECOVERY     chave pública age de recuperação da Quantum (obrigatória)
#   OFFSITE_MEDIA                      1 envia também a mídia (default 1)
#   OFFSITE_HASH                       sha1 | md5 | sha256 (default sha1: o que o B2 guarda)
#   OFFSITE_HASH_DOWNLOAD              1 baixa o objeto para calcular o hash (provedor que
#                                      não guarda o hash escolhido). Default 0
#   RCLONE_CONFIG                      rclone.conf com a credencial (obrigatório, 0600)
#   RCLONE_CACHE_DIR                   cache do rclone (em diretório gravável pela unit)
#   AGE / RCLONE                       binários (default age / rclone)
#
# Saída: 0 com tudo conferido; 1 em qualquer falha (a unit fica failed).

set -euo pipefail
umask 077

SQ_SCRIPT="offsite_push.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"
# shellcheck source-path=SCRIPTDIR source=lib/offsite_common.sh
. "${SCRIPT_DIR}/lib/offsite_common.sh"

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
KEY_BACKUP_DIR="${KEY_BACKUP_DIR:-/var/lib/smartquotation/key-backup}"
OFFSITE_REMOTE="${OFFSITE_REMOTE:-}"
OFFSITE_KEY_REMOTE="${OFFSITE_KEY_REMOTE:-}"
OFFSITE_AGE_RECIPIENT_INSTANCE="${OFFSITE_AGE_RECIPIENT_INSTANCE:-}"
OFFSITE_AGE_RECIPIENT_RECOVERY="${OFFSITE_AGE_RECIPIENT_RECOVERY:-}"
OFFSITE_MEDIA="${OFFSITE_MEDIA:-1}"
OFFSITE_HASH="${OFFSITE_HASH:-sha1}"
OFFSITE_HASH_DOWNLOAD="${OFFSITE_HASH_DOWNLOAD:-0}"
AGE="${AGE:-age}"
RCLONE="${RCLONE:-rclone}"

# --- Tudo recusado ANTES de tocar em age ou rclone. --------------------------------------
sq_offsite_check_recipient OFFSITE_AGE_RECIPIENT_INSTANCE
sq_offsite_check_recipient OFFSITE_AGE_RECIPIENT_RECOVERY
if [ "${OFFSITE_AGE_RECIPIENT_INSTANCE}" = "${OFFSITE_AGE_RECIPIENT_RECOVERY}" ]; then
  sq_die "OFFSITE_AGE_RECIPIENT_INSTANCE e OFFSITE_AGE_RECIPIENT_RECOVERY são a MESMA chave: isso é um destinatário só. Recusando."
fi
sq_offsite_check_remote OFFSITE_REMOTE
if [ -n "${OFFSITE_KEY_REMOTE}" ]; then
  sq_offsite_check_remote OFFSITE_KEY_REMOTE
  sq_offsite_check_separate "${OFFSITE_REMOTE}" "${OFFSITE_KEY_REMOTE}"
fi
case "${OFFSITE_MEDIA}" in
  0|1) ;;
  *) sq_die "OFFSITE_MEDIA='${OFFSITE_MEDIA}' inválido (0 | 1). Recusando." ;;
esac
sq_check_dirs_disjoint "${KEY_BACKUP_DIR}" "${BACKUP_DIR}"
sq_offsite_check_rclone_config
sq_offsite_check_tools

trap sq_cleanup EXIT INT TERM
sq_prune_orphan_tmp "${BACKUP_DIR}"

newest() {
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name "$1" 2>/dev/null | LC_ALL=C sort | tail -n 1
}

DUMP="$(newest 'sq_*.sql.gz')"
[ -n "${DUMP}" ] || sq_die "nenhum dump sq_*.sql.gz em ${BACKUP_DIR}: nada a enviar."
MEDIA=""
if [ "${OFFSITE_MEDIA}" = "1" ]; then
  MEDIA="$(newest 'media_*.tar.gz')"
  [ -n "${MEDIA}" ] || sq_die "nenhum media_*.tar.gz em ${BACKUP_DIR} (OFFSITE_MEDIA=0 desliga)."
fi

MANIFEST="${BACKUP_DIR}/offsite_manifest"
RECIPIENTS=("${OFFSITE_AGE_RECIPIENT_INSTANCE}" "${OFFSITE_AGE_RECIPIENT_RECOVERY}")
STATUS=("timestamp=PLACEHOLDER" "remote=${OFFSITE_REMOTE%/}")

push_one() {  # ROTULO ARQUIVO
  local obj
  obj="$(basename -- "$2").age"
  sq_offsite_push "$2" "${OFFSITE_REMOTE}" "${obj}" "${MANIFEST}" "${BACKUP_DIR}" "${RECIPIENTS[@]}"
  STATUS+=("$1=${obj}" "$1_result=${PUSH_RESULT}" "$1_bytes=${PUSH_BYTES}" "$1_hash=${PUSH_HASH}")
}

push_one dump "${DUMP}"
if [ -n "${MEDIA}" ]; then
  push_one media "${MEDIA}"
fi

STATUS[0]="timestamp=$(sq_now_iso)"
sq_write_status "${BACKUP_DIR}/offsite_last_success" "${STATUS[@]}"
echo "${SQ_SCRIPT}: ok — $(basename -- "${DUMP}")${MEDIA:+ e $(basename -- "${MEDIA}")} conferidos em ${OFFSITE_REMOTE%/}" >&2
