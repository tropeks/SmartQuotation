#!/usr/bin/env bash
# Backup da FIELD_ENCRYPTION_KEY + PROVA DE DECIFRA contra o dump mais recente.
#
# Por quê: preço de material (MaterialPrice.preco_brl_kg) é cifrado com Fernet
# (django-encrypted-model-fields) usando a FIELD_ENCRYPTION_KEY que só existe no env do
# container da app. Dump sem essa chave restaura um banco com preços ILEGÍVEIS. Este script
# guarda a chave SEPARADA do dump e prova, a cada execução, que ela abre o dump de hoje.
#
# O que faz:
#   1. Lê a chave do env do container ${WEB_CONTAINER} (docker inspect, filtrado pelo próprio
#      template para só essa variável cruzar o pipe) e grava em
#      ${KEY_BACKUP_DIR}/field_encryption_key (0600), com o fingerprint (sha256 truncado em
#      16 hex) em field_encryption_key.sha256 ao lado. Se a chave MUDOU desde a última vez,
#      a anterior é preservada como field_encryption_key.prev.<fingerprint> — dumps antigos
#      só abrem com ela.
#   2. Tira do dump mais recente (${BACKUP_DIR}/sq_*.sql.gz) UM valor cifrado de
#      <schema>.materials_materialprice.preco_brl_kg e roda um python DENTRO do container
#      (que tem `cryptography`) recebendo chave e token por STDIN — nunca por argv nem env.
#   3. A prova imprime SÓ `ok`, `falha` ou `sem amostra`. Qualquer outra saída do container é
#      tratada como falha e DESCARTADA sem ser repassada (não confiamos no que volta).
#
# Garantias (testadas em tests/test_backup_key.py):
#   - a chave nunca vai para stdout/stderr, argv, arquivo de status nem para ${BACKUP_DIR};
#   - o valor decifrado nunca sai do python da prova;
#   - KEY_BACKUP_DIR não pode ser, nem estar dentro de, ${BACKUP_DIR} (e vice-versa): a chave
#     NUNCA viaja junto com o dump (off-site da ordem 003 leva só o dump).
#
# Saída / exit code:
#   0  chave salva + prova ok                     → ${KEY_BACKUP_DIR}/last_success
#   2  prova falhou (chave não abre o dump)       → unit falha
#   3  sem amostra (dump sem MaterialPrice)       → unit falha, salvo KEY_PROOF_ALLOW_NO_SAMPLE=1
#   1  erro de ambiente (docker, container, dump ausente, chave ausente/malformada)
#   Toda execução que chega à prova grava ${KEY_BACKUP_DIR}/last_proof (resultado, dump,
#   fingerprint, timestamp).
#
# Variáveis:
#   WEB_CONTAINER             container da app (default: sq-web-proto)
#   KEY_BACKUP_DIR            destino da chave (default: /var/lib/smartquotation/key-backup)
#   BACKUP_DIR / POSTGRES_BACKUP_DIR  onde estão os dumps (default: /backups/sq)
#   KEY_PROOF_SCHEMA          schema do tenant de onde sai a amostra (default: engematex)
#   KEY_PROOF_ALLOW_NO_SAMPLE 1 aceita "sem amostra" com exit 0 (default 0)
#   DOCKER                    binário docker (default: docker)

set -euo pipefail
umask 077

SQ_SCRIPT="backup_key.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"

WEB_CONTAINER="${WEB_CONTAINER:-sq-web-proto}"
KEY_BACKUP_DIR="${KEY_BACKUP_DIR:-/var/lib/smartquotation/key-backup}"
BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
KEY_PROOF_SCHEMA="${KEY_PROOF_SCHEMA:-engematex}"
KEY_PROOF_ALLOW_NO_SAMPLE="${KEY_PROOF_ALLOW_NO_SAMPLE:-0}"
DOCKER="${DOCKER:-docker}"

if ! [[ "${KEY_PROOF_SCHEMA}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  echo "${SQ_SCRIPT}: KEY_PROOF_SCHEMA inválido. Recusando." >&2
  exit 1
fi

# --- A chave não mora com o dump. --------------------------------------------------------
KEY_REAL="$(realpath -m -- "${KEY_BACKUP_DIR}")"
DUMP_REAL="$(realpath -m -- "${BACKUP_DIR}")"
case "${KEY_REAL}/" in
  "${DUMP_REAL}/"*)
    echo "${SQ_SCRIPT}: KEY_BACKUP_DIR (${KEY_REAL}) está dentro de BACKUP_DIR (${DUMP_REAL})." >&2
    echo "${SQ_SCRIPT}: a chave NUNCA fica junto do dump — escolha um diretório fora dele. Recusando." >&2
    exit 1 ;;
esac
case "${DUMP_REAL}/" in
  "${KEY_REAL}/"*)
    echo "${SQ_SCRIPT}: BACKUP_DIR (${DUMP_REAL}) está dentro de KEY_BACKUP_DIR (${KEY_REAL}). Recusando." >&2
    exit 1 ;;
esac

mkdir -p "${KEY_BACKUP_DIR}"
chmod 700 "${KEY_BACKUP_DIR}"

KEY_FILE="${KEY_BACKUP_DIR}/field_encryption_key"
WORK="$(mktemp -d)"
KEY_TMP="${KEY_FILE}.tmp.$$"
trap 'rm -rf "${WORK}"; rm -f "${KEY_TMP}"' EXIT INT TERM

sq_require_docker

if [ "$(sq_container_state "${WEB_CONTAINER}")" = "absent" ]; then
  echo "${SQ_SCRIPT}: container '${WEB_CONTAINER}' não encontrado." >&2
  exit 1
fi

# --- 1. Chave: do env do container direto para o arquivo, só por pipe. -------------------
# O template já filtra para só FIELD_ENCRYPTION_KEY cruzar o pipe (o env do container tem
# outros segredos); o awk é a segunda peneira e escreve SEM newline no arquivo 0600.
# shellcheck disable=SC2016  # template Go, não expansão do shell
KEY_TEMPLATE='{{range .Config.Env}}{{if eq (index (split . "=") 0) "FIELD_ENCRYPTION_KEY"}}{{println .}}{{end}}{{end}}'
if ! ${DOCKER} inspect -f "${KEY_TEMPLATE}" "${WEB_CONTAINER}" 2>/dev/null \
    | awk 'BEGIN { p = "FIELD_ENCRYPTION_KEY=" }
           index($0, p) == 1 { v = substr($0, length(p) + 1); n++ }
           END { if (n) printf "%s", v; exit (n ? 0 : 4) }' > "${KEY_TMP}"; then
  echo "${SQ_SCRIPT}: FIELD_ENCRYPTION_KEY ausente do env do container '${WEB_CONTAINER}' (ou inspect falhou)." >&2
  exit 1
fi
# Formato de chave Fernet: 32 bytes em base64 url-safe = 43 caracteres + "=". Checado no
# arquivo, com grep -q: o valor nunca vira argumento nem mensagem.
if ! grep -q -x -E '[A-Za-z0-9_-]{43}=' "${KEY_TMP}"; then
  echo "${SQ_SCRIPT}: FIELD_ENCRYPTION_KEY do container não tem formato de chave Fernet (valor NÃO exibido)." >&2
  exit 1
fi
chmod 600 "${KEY_TMP}"
FPR="$(sha256sum < "${KEY_TMP}" | cut -c1-16)"

if [ -f "${KEY_FILE}" ] && ! cmp -s "${KEY_FILE}" "${KEY_TMP}"; then
  OLD_FPR="$(sha256sum < "${KEY_FILE}" | cut -c1-16)"
  mv -f -- "${KEY_FILE}" "${KEY_FILE}.prev.${OLD_FPR}"
  echo "${SQ_SCRIPT}: ATENÇÃO — a chave do container MUDOU (sha256 ${OLD_FPR} → ${FPR})." >&2
  echo "${SQ_SCRIPT}: a anterior ficou em $(basename -- "${KEY_FILE}").prev.${OLD_FPR}: dumps antigos só abrem com ela." >&2
fi
mv -f -- "${KEY_TMP}" "${KEY_FILE}"
sq_write_status "${KEY_FILE}.sha256" "sha256_16=${FPR}"

# --- 2. Amostra cifrada do dump mais recente. --------------------------------------------
DUMP="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'sq_*.sql.gz' 2>/dev/null | LC_ALL=C sort | tail -n 1)"
if [ -z "${DUMP}" ]; then
  echo "${SQ_SCRIPT}: chave salva (sha256 ${FPR}), mas não há dump em ${BACKUP_DIR} para a prova de decifra." >&2
  exit 1
fi
DUMP_NAME="$(basename -- "${DUMP}")"

# Primeiro preco_brl_kg não-nulo do COPY de materials_materialprice do schema do tenant. A
# posição da coluna vem do cabeçalho do COPY (não de ordem suposta). O awk lê o dump até o
# fim de propósito: sair cedo mataria o zcat com SIGPIPE e o pipefail acusaria erro.
TOKEN_FILE="${WORK}/token"
zcat "${DUMP}" | awk -F '\t' -v hdr="COPY ${KEY_PROOF_SCHEMA}.materials_materialprice (" '
  !found && index($0, hdr) == 1 {
    cols = substr($0, length(hdr) + 1); sub(/\) FROM stdin;$/, "", cols)
    n = split(cols, c, ", "); idx = 0
    for (i = 1; i <= n; i++) if (c[i] == "preco_brl_kg") idx = i
    incopy = (idx > 0); next
  }
  incopy {
    if ($0 == "\\.") { incopy = 0; next }
    if (!found && $idx != "\\N" && $idx != "") { print $idx; found = 1 }
  }' > "${TOKEN_FILE}"

# --- 3. Prova dentro do container, tudo por stdin. ---------------------------------------
# O python só imprime uma de três palavras. Ele não imprime, não loga e não devolve o valor
# decifrado; exceções viram "falha" sem traceback (o stderr do exec também é descartado).
PROOF_PY='
import sys
def main():
    try:
        key = sys.stdin.readline().strip()
        tok = sys.stdin.readline().strip()
        if not tok:
            return "sem amostra"
        from cryptography.fernet import Fernet
        Fernet(key.encode()).decrypt(tok.encode())
        return "ok"
    except BaseException:
        return "falha"
sys.stdout.write(main() + "\n")
'

if [ ! -s "${TOKEN_FILE}" ]; then
  RESULT="sem amostra"
else
  RAW="$({ cat "${KEY_FILE}"; printf '\n'; cat "${TOKEN_FILE}"; } \
          | ${DOCKER} exec -i "${WEB_CONTAINER}" python -c "${PROOF_PY}" 2>/dev/null || true)"
  case "${RAW}" in
    ok) RESULT="ok" ;;
    "sem amostra") RESULT="sem amostra" ;;
    falha) RESULT="falha" ;;
    *)
      RESULT="falha"
      echo "${SQ_SCRIPT}: a prova devolveu saída inesperada (suprimida, não é repassada)." >&2 ;;
  esac
  RAW=""
fi

NOW="$(sq_now_iso)"
sq_write_status "${KEY_BACKUP_DIR}/last_proof" \
  "timestamp=${NOW}" "result=${RESULT}" "dump=${DUMP_NAME}" "key_sha256_16=${FPR}"

case "${RESULT}" in
  ok)
    sq_write_status "${KEY_BACKUP_DIR}/last_success" \
      "timestamp=${NOW}" "result=ok" "dump=${DUMP_NAME}" "key_sha256_16=${FPR}"
    echo "${SQ_SCRIPT}: chave salva (sha256 ${FPR}) — prova de decifra: ok (${DUMP_NAME})"
    exit 0 ;;
  "sem amostra")
    echo "${SQ_SCRIPT}: chave salva (sha256 ${FPR}) — prova de decifra: sem amostra (${DUMP_NAME} não tem ${KEY_PROOF_SCHEMA}.materials_materialprice com valor)"
    if [ "${KEY_PROOF_ALLOW_NO_SAMPLE}" = "1" ]; then
      exit 0
    fi
    echo "${SQ_SCRIPT}: 'sem amostra' não é verde: a chave não foi provada. KEY_PROOF_ALLOW_NO_SAMPLE=1 aceita." >&2
    exit 3 ;;
  *)
    echo "${SQ_SCRIPT}: chave salva (sha256 ${FPR}) — prova de decifra: falha (${DUMP_NAME})"
    echo "${SQ_SCRIPT}: a chave do container NÃO abre o dump mais recente. Investigue antes de confiar neste backup." >&2
    exit 2 ;;
esac
