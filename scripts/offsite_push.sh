#!/usr/bin/env bash
# Cópia OFF-SITE cifrada da série de backup (ordem 003): dumps e tars de mídia, cifrados com
# age, enviados com rclone. Roda pelo backup_run.sh (sq-backup.service) depois de
# backup_db.sh, backup_media.sh, backup_key.sh e offsite_key_push.sh — e roda mesmo que algum
# deles tenha falhado: o off-site do dump tem valor sem a chave.
#
# O que faz, primeiro para o dump (${BACKUP_DIR}/sq_*.sql.gz) e o tar de mídia
# (media_*.tar.gz) MAIS NOVOS, e depois para cada um ainda não confirmado no offsite_manifest
# (backfill, do mais antigo para o mais novo, até OFFSITE_BACKFILL_MAX por execução — um dia
# sem envio não deixa buraco na série). Um objeto antigo com problema não bloqueia o de hoje:
# as falhas se acumulam e o script sai != 0 no fim, nomeando-as:
#   1. Cifra com age para DOIS destinatários: a chave pública da instância
#      (OFFSITE_AGE_RECIPIENT_INSTANCE) e a de recuperação da Quantum
#      (OFFSITE_AGE_RECIPIENT_RECOVERY, raiz offline no YubiKey, DP-41). O arquivo sai por
#      stdin para o age, e o .age vai para um temporário 0600 no próprio BACKUP_DIR,
#      apagado pelo trap.
#   2. Confere o cabeçalho age: exatamente uma stanza por destinatário, do tipo dele
#      ("-> X25519" para age1…, "-> piv-p256" para age1yubikey1…). Senão, não envia.
#   3. Envia com `rclone copyto --immutable` para ${OFFSITE_REMOTE}/<arquivo>.age.
#   4. Confere o hash remoto (rclone hashsum ${OFFSITE_HASH}) contra o hash local do .age.
#   5. Só com tudo conferido, e com o dump mais novo mais recente que OFFSITE_MAX_AGE_HOURS
#      (default 26; 0 desliga), grava ${BACKUP_DIR}/offsite_last_success (atômico, 0600).
#      Dump velho = backup_db parado: o off-site roda, mas o status não fica verde.
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
# (AGE-SECRET-KEY-…) ou de identidade de plugin (AGE-PLUGIN-YUBIKEY-…), ausente, repetido ou
# com o valor fictício do exemplo: recusado. Destinatário YubiKey (age1yubikey1…, DP-41)
# exige age-plugin-yubikey no PATH — só para cifrar; a identidade fica no token.
#
# Variáveis:
#   BACKUP_DIR / POSTGRES_BACKUP_DIR   onde estão dump e mídia (default /backups/sq)
#   KEY_BACKUP_DIR                     só para conferir que não se sobrepõe ao BACKUP_DIR
#   OFFSITE_REMOTE                     destino do dump e da mídia (obrigatório)
#   OFFSITE_KEY_REMOTE                 se definido, conferido como distinto do OFFSITE_REMOTE
#   OFFSITE_AGE_RECIPIENT_INSTANCE     destinatário age da instância (obrigatório)
#   OFFSITE_AGE_RECIPIENT_RECOVERY     destinatário de recuperação da Quantum (obrigatório);
#                                      age1… (X25519) ou age1yubikey1… (YubiKey)
#   OFFSITE_MEDIA                      1 envia também a mídia (default 1)
#   OFFSITE_MAX_AGE_HOURS              idade máxima do dump mais novo para renovar o status
#                                      (default 26; 0 desliga)
#   OFFSITE_BACKFILL_MAX               arquivos antigos pendentes enviados por execução, além
#                                      dos mais novos (default 6; o resto sai nas próximas)
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
OFFSITE_MAX_AGE_HOURS="${OFFSITE_MAX_AGE_HOURS:-26}"
OFFSITE_BACKFILL_MAX="${OFFSITE_BACKFILL_MAX:-6}"
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
[[ "${OFFSITE_BACKFILL_MAX}" =~ ^[0-9]+$ ]] \
  || sq_die "OFFSITE_BACKFILL_MAX='${OFFSITE_BACKFILL_MAX}' inválido (inteiro >= 0). Recusando."
[[ "${OFFSITE_MAX_AGE_HOURS}" =~ ^[0-9]+$ ]] \
  || sq_die "OFFSITE_MAX_AGE_HOURS='${OFFSITE_MAX_AGE_HOURS}' inválido (inteiro >= 0; 0 desliga). Recusando."
sq_check_dirs_disjoint "${KEY_BACKUP_DIR}" "${BACKUP_DIR}"
sq_offsite_check_rclone_config
if [ -n "${OFFSITE_KEY_REMOTE}" ]; then
  sq_offsite_check_conf_separation "${OFFSITE_REMOTE}" "${OFFSITE_KEY_REMOTE}"
fi
sq_offsite_check_tools
sq_offsite_check_plugins "${OFFSITE_AGE_RECIPIENT_INSTANCE}" "${OFFSITE_AGE_RECIPIENT_RECOVERY}"

trap sq_cleanup EXIT INT TERM
sq_prune_orphan_tmp "${BACKUP_DIR}"

# Todos os arquivos PADRAO do BACKUP_DIR, do mais antigo para o mais novo (o nome carrega o
# timestamp, então a ordem lexical é a cronológica).
all_of() {
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name "$1" 2>/dev/null | LC_ALL=C sort
}

MANIFEST="${BACKUP_DIR}/offsite_manifest"
RECIPIENTS=("${OFFSITE_AGE_RECIPIENT_INSTANCE}" "${OFFSITE_AGE_RECIPIENT_RECOVERY}")
STATUS=("timestamp=PLACEHOLDER" "remote=${OFFSITE_REMOTE%/}")
BACKFILLED=0
PENDING_LEFT=0
FAILURES=()
RESULT_FILE="$(mktemp)" || sq_die "mktemp falhou."
sq_track_tmp "${RESULT_FILE}"

# try_push ARQUIVO — um envio isolado: falha de UM objeto (ex.: antigo divergente) não aborta
# os outros. Roda num subshell com set -e LIGADO (set +e fora, para capturar o exit sem
# desligar o errexit lá dentro) e com o próprio trap de limpeza. Sucesso: PUSH_* preenchidos.
try_push() {
  local rc
  set +e
  (
    set -e
    trap sq_cleanup EXIT
    SQ_TMPS=()
    sq_offsite_push "$1" "${OFFSITE_REMOTE}" "$(basename -- "$1").age" "${MANIFEST}" "${BACKUP_DIR}" "${RECIPIENTS[@]}"
    printf '%s\t%s\t%s\n' "${PUSH_RESULT}" "${PUSH_HASH}" "${PUSH_BYTES}" > "${RESULT_FILE}"
  )
  rc=$?
  set -e
  if [ "${rc}" -ne 0 ]; then
    FAILURES+=("$(basename -- "$1").age")
    return 1
  fi
  IFS=$'\t' read -r PUSH_RESULT PUSH_HASH PUSH_BYTES < "${RESULT_FILE}"
}

# push_series ROTULO PADRAO
#   1. o MAIS NOVO primeiro (sempre passa pelo sq_offsite_push, que confere o hash remoto
#      mesmo quando já foi enviado): um objeto antigo com problema nunca bloqueia o de hoje;
#   2. depois o backfill: todo arquivo ainda não CONFIRMADO no manifesto, do mais antigo para
#      o mais novo, até OFFSITE_BACKFILL_MAX por execução (somado entre as séries; o resto
#      sai nas próximas). Falhas se acumulam em FAILURES e são nomeadas no fim.
# Define NEWEST (o mais novo) e NEWEST_OK (1 se ele foi confirmado).
push_series() {
  local label="$1" f last=""
  local -a files=()
  mapfile -t files < <(all_of "$2")
  [ "${#files[@]}" -gt 0 ] || sq_die "nenhum $2 em ${BACKUP_DIR}: nada a enviar."
  last="${files[${#files[@]}-1]}"
  NEWEST="${last}"
  NEWEST_OK=0
  if try_push "${last}"; then
    NEWEST_OK=1
    STATUS+=("${label}=$(basename -- "${last}").age" "${label}_result=${PUSH_RESULT}"
             "${label}_bytes=${PUSH_BYTES}" "${label}_hash=${PUSH_HASH}")
  fi
  for f in "${files[@]}"; do
    [ "${f}" = "${last}" ] && break
    sq_manifest_confirmed "${MANIFEST}" "$(basename -- "${f}").age" && continue
    if [ "${BACKFILLED}" -ge "${OFFSITE_BACKFILL_MAX}" ]; then
      PENDING_LEFT=$((PENDING_LEFT + 1))
      continue
    fi
    BACKFILLED=$((BACKFILLED + 1))
    try_push "${f}" || true
  done
}

push_series dump 'sq_*.sql.gz'
DUMP="${NEWEST}"
DUMP_OK="${NEWEST_OK}"
MEDIA=""
if [ "${OFFSITE_MEDIA}" = "1" ]; then
  push_series media 'media_*.tar.gz'
  MEDIA="${NEWEST}"
fi

if [ "${PENDING_LEFT}" -gt 0 ]; then
  echo "${SQ_SCRIPT}: backfill: ${PENDING_LEFT} arquivo(s) ainda pendente(s) — saem nas próximas execuções (OFFSITE_BACKFILL_MAX=${OFFSITE_BACKFILL_MAX})." >&2
fi
if [ "${#FAILURES[@]}" -gt 0 ]; then
  sq_die "FALHA — ${#FAILURES[@]} objeto(s) não enviados/conferidos: ${FAILURES[*]}. O que deu certo ficou no off-site; offsite_last_success NÃO foi renovado.$( [ "${DUMP_OK}" = 1 ] && printf ' O dump mais novo (%s) está confirmado.' "$(basename -- "${DUMP}")" )"
fi

# Verde só sobre dump recente: com o backup_db parado, o off-site continua conferindo o que
# há, mas o offsite_last_success NÃO renova e o script sai != 0.
if [ "${OFFSITE_MAX_AGE_HOURS}" -gt 0 ] \
    && [ -n "$(find "${DUMP}" -mmin +$((OFFSITE_MAX_AGE_HOURS * 60)) -print)" ]; then
  sq_die "FALHA — o dump mais novo ($(basename -- "${DUMP}")) tem mais de ${OFFSITE_MAX_AGE_HOURS}h: está no off-site, mas offsite_last_success NÃO foi renovado. O backup diário parou?"
fi

STATUS[0]="timestamp=$(sq_now_iso)"
STATUS+=("backfill=${BACKFILLED}" "backfill_pending=${PENDING_LEFT}")
sq_write_status "${BACKUP_DIR}/offsite_last_success" "${STATUS[@]}"
echo "${SQ_SCRIPT}: ok — $(basename -- "${DUMP}")${MEDIA:+ e $(basename -- "${MEDIA}")} conferidos em ${OFFSITE_REMOTE%/} (${BACKFILLED} do backfill, ${PENDING_LEFT} pendente(s))" >&2
