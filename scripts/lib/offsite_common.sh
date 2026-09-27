# shellcheck shell=bash
# Funções comuns ao off-site (offsite_push.sh, offsite_key_push.sh — ordem 003). Carregado
# com `source` DEPOIS de lib/backup_common.sh, com o mesmo contrato (set -euo pipefail,
# umask 077, SQ_SCRIPT, trap sq_cleanup) e com AGE, RCLONE, OFFSITE_HASH e
# OFFSITE_HASH_DOWNLOAD definidos.
#
# O que NUNCA acontece aqui: nenhuma função chama delete, purge, sync, move nem cleanup do
# rclone. Enquanto a DP-27 (retenção NR-13) estiver aberta, nada é apagado no remoto por
# rotina (tests/test_offsite_push.py falha se o rclone receber qualquer um desses).

# Saídas de sq_offsite_push (lidas pelo script chamador) e de sq_remote_hash.
# shellcheck disable=SC2034
PUSH_RESULT="" PUSH_HASH="" PUSH_BYTES="" REMOTE_HASH="" SQ_HASH_LEN=0

# Destinatário X25519 do age em bech32: "age1" + 58 caracteres do alfabeto bech32.
SQ_AGE_RECIPIENT_RE='^age1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}$'

sq_die() {
  echo "${SQ_SCRIPT}: $*" >&2
  exit 1
}

# sq_offsite_check_recipient NOME_DA_VARIAVEL
# O VALOR nunca aparece em mensagem: se alguém colou a chave privada no lugar da pública,
# repetir o valor no journal seria vazá-la.
sq_offsite_check_recipient() {
  local name="$1" value="${!1:-}" rest
  if [ -z "${value}" ]; then
    sq_die "${name} ausente. O off-site cifra para a chave pública da instância E para a de recuperação da Quantum (DP-41); com um destinatário só, perder aquela chave privada é perder a série. Recusando."
  fi
  if [[ "${value}" == *AGE-SECRET-KEY-* ]]; then
    sq_die "${name} parece uma chave PRIVADA do age (AGE-SECRET-KEY-…; valor NÃO exibido). O host guarda SÓ chaves públicas (age1…): tire a privada do backup.env, guarde-a offline e troque o par se ela já esteve no host. Recusando."
  fi
  if ! [[ "${value}" =~ ${SQ_AGE_RECIPIENT_RE} ]]; then
    sq_die "${name} não tem formato de chave pública X25519 do age (age1 + 58 caracteres bech32; valor NÃO exibido). Recusando."
  fi
  rest="${value#age1}"
  if [ -z "$(printf '%s' "${rest}" | tr -d "${rest:0:1}")" ]; then
    sq_die "${name} é o valor FICTÍCIO do backup.env.example. Ponha a chave pública real (age-keygen -y). Recusando."
  fi
}

# sq_offsite_check_remote NOME_DA_VARIAVEL — "secao:caminho", com seção do rclone.conf.
# Recusa a sintaxe de backend na hora (":b2,account=…:bucket"): ela carrega credencial na
# própria string, que iria para argv e para o log.
sq_offsite_check_remote() {
  local name="$1" value="${!1:-}"
  if [ -z "${value}" ]; then
    sq_die "${name} ausente (ex.: sq-offsite:bucket/prefixo, com a seção sq-offsite no rclone.conf). Recusando."
  fi
  if ! [[ "${value}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*:[^[:space:]]+$ ]] || [[ "${value}" == *:*:* ]]; then
    sq_die "${name}='${value}' inválido: use 'secao:bucket/prefixo', com a seção (e a credencial) no rclone.conf, nunca na string. Recusando."
  fi
}

# sq_offsite_check_separate REMOTE_DO_DUMP REMOTE_DA_CHAVE
# Decisão (b) do Diretor: a chave vai para destino DISTINTO, com credencial própria.
sq_offsite_check_separate() {
  local d="${1%/}" k="${2%/}"
  if [ "${d}" = "${k}" ] || [[ "${k}/" == "${d}/"* ]] || [[ "${d}/" == "${k}/"* ]]; then
    sq_die "OFFSITE_KEY_REMOTE (${k}) é igual ao OFFSITE_REMOTE (${d}) ou um está dentro do outro. A chave NUNCA vai para o destino do dump. Recusando."
  fi
  if [ "${d%%:*}" = "${k%%:*}" ]; then
    sq_die "OFFSITE_KEY_REMOTE e OFFSITE_REMOTE usam a mesma seção do rclone.conf ('${d%%:*}'): a chave precisa de bucket e credencial PRÓPRIOS (outra seção). Recusando."
  fi
}

# rclone.conf tem a credencial do bucket: root, 0600. Legível por grupo/outros é recusado.
sq_offsite_check_rclone_config() {
  local perm
  if [ -z "${RCLONE_CONFIG:-}" ]; then
    sq_die "RCLONE_CONFIG não definido (ex.: /etc/smartquotation/rclone.conf, root 0600). Recusando."
  fi
  if [ ! -f "${RCLONE_CONFIG}" ]; then
    sq_die "RCLONE_CONFIG=${RCLONE_CONFIG} não existe. Recusando."
  fi
  perm="$(stat -c '%a' -- "${RCLONE_CONFIG}")"
  if (( 8#${perm} & 8#077 )); then
    sq_die "RCLONE_CONFIG=${RCLONE_CONFIG} tem modo ${perm}: legível por grupo/outros. Use chmod 600. Recusando."
  fi
}

sq_offsite_check_tools() {
  command -v "${AGE}" >/dev/null 2>&1 || sq_die "age não encontrado ('${AGE}'). Instale o pacote age. Recusando."
  command -v "${RCLONE}" >/dev/null 2>&1 || sq_die "rclone não encontrado ('${RCLONE}'). Instale o pacote rclone. Recusando."
  case "${OFFSITE_HASH}" in
    sha1) SQ_HASH_LEN=40 ;;
    md5) SQ_HASH_LEN=32 ;;
    sha256) SQ_HASH_LEN=64 ;;
    *) sq_die "OFFSITE_HASH='${OFFSITE_HASH}' inválido (sha1 | md5 | sha256). Recusando." ;;
  esac
  case "${OFFSITE_HASH_DOWNLOAD}" in
    0|1) ;;
    *) sq_die "OFFSITE_HASH_DOWNLOAD='${OFFSITE_HASH_DOWNLOAD}' inválido (0 | 1). Recusando." ;;
  esac
  if [ -n "${RCLONE_CACHE_DIR:-}" ]; then
    mkdir -p -- "${RCLONE_CACHE_DIR}"
    chmod 700 -- "${RCLONE_CACHE_DIR}"
  fi
}

# sq_check_dirs_disjoint A B — nenhum dos dois pode ser, nem estar dentro do, outro.
sq_check_dirs_disjoint() {
  local a b
  a="$(realpath -m -- "$1")"
  b="$(realpath -m -- "$2")"
  case "${a}/" in "${b}/"*) sq_die "KEY_BACKUP_DIR e BACKUP_DIR se sobrepõem (${a} / ${b}): a chave NUNCA mora com o dump. Recusando." ;; esac
  case "${b}/" in "${a}/"*) sq_die "KEY_BACKUP_DIR e BACKUP_DIR se sobrepõem (${a} / ${b}): a chave NUNCA mora com o dump. Recusando." ;; esac
}

sq_local_hash() {
  "${OFFSITE_HASH}sum" < "$1" | cut -d ' ' -f 1
}

# sq_remote_hash ALVO — define REMOTE_HASH: "" se o objeto não existe, o hash se existe.
# Erro de rclone (rede, credencial) NÃO vira "ausente": ausente mandaria enviar de novo.
# rclone sai 3 (diretório não encontrado) ou 4 (arquivo não encontrado) para o que não
# existe em backends com diretório; em bucket, lista vazia com exit 0.
sq_remote_hash() {
  local target="$1" leaf="${1##*/}" out rc=0 errf
  errf="$(mktemp)"
  sq_track_tmp "${errf}"
  # shellcheck disable=SC2046  # a flag opcional some quando vazia, de propósito
  out="$("${RCLONE}" hashsum "${OFFSITE_HASH}" $( [ "${OFFSITE_HASH_DOWNLOAD}" = "1" ] && echo --download ) \
          "${target}" 2>"${errf}")" || rc=$?
  if [ "${rc}" -eq 3 ] || [ "${rc}" -eq 4 ]; then
    REMOTE_HASH=""
    return 0
  fi
  if [ "${rc}" -ne 0 ]; then
    echo "${SQ_SCRIPT}: rclone hashsum falhou (exit ${rc}) em ${target}:" >&2
    sed 's/^/  rclone: /' "${errf}" >&2
    return 1
  fi
  # Linha "<hash>  <nome>"; o nome é o do objeto (a listagem pode trazer vizinhos).
  REMOTE_HASH="$(printf '%s\n' "${out}" | LC_ALL=C awk -v leaf="${leaf}" '
    { n = length($0) - length(leaf)
      if (n >= 0 && substr($0, n + 1) == leaf) { h = substr($0, 1, n); gsub(/[[:space:]]/, "", h); print (h == "" ? "-" : h); exit } }')"
  if [ -n "${REMOTE_HASH}" ] && ! [[ "${REMOTE_HASH}" =~ ^[0-9a-f]{${SQ_HASH_LEN}}$ ]]; then
    echo "${SQ_SCRIPT}: o remoto não deu hash ${OFFSITE_HASH} para ${target} (o provedor não guarda esse hash?)." >&2
    echo "${SQ_SCRIPT}: troque OFFSITE_HASH para um que o provedor suporte ou use OFFSITE_HASH_DOWNLOAD=1 (baixa e calcula)." >&2
    return 1
  fi
  return 0
}

# sq_age_header_ok ARQUIVO N — o cabeçalho age tem EXATAMENTE N stanzas, todas X25519.
# Lê o arquivo direto (sem pipe: sair cedo não gera SIGPIPE) e para na linha "--- ".
sq_age_header_ok() {
  local counts total x25519
  counts="$(LC_ALL=C awk '
    NR == 1 { if ($0 != "age-encryption.org/v1") { bad = 1; exit } next }
    /^-> / { t++; if ($2 == "X25519") x++; next }
    /^--- / { done = 1; exit }
    END { if (bad || !done) exit 1; printf "%d %d\n", t, x }' "$1")" || return 1
  read -r total x25519 <<< "${counts}"
  [ "${total}" -eq "$2" ] && [ "${x25519}" -eq "$2" ]
}

# Manifesto local (0600): "<objeto>\t<tipo>:<hash>\t<bytes>" de cada .age cujo cabeçalho foi
# conferido. Como o age cifra com aleatoriedade, recifrar dá outro hash: o manifesto é o que
# permite reconhecer, no remoto, o objeto que ESTE host enviou.
sq_manifest_get() {
  [ -f "$1" ] || return 0
  LC_ALL=C awk -F '\t' -v o="$2" '$1 == o { r = $2 "\t" $3 } END { if (r != "") print r }' "$1"
}

sq_manifest_put() {
  local m="$1" tmp="$1.tmp.$$"
  sq_track_tmp "${tmp}"
  {
    if [ -f "${m}" ]; then LC_ALL=C awk -F '\t' -v o="$2" '$1 != o' "${m}"; fi
    printf '%s\t%s\t%s\n' "$2" "$3" "$4"
  } > "${tmp}"
  chmod 600 "${tmp}"
  mv -f -- "${tmp}" "${m}"
}

# sq_offsite_push ORIGEM REMOTE OBJETO MANIFESTO DIR_TEMP DESTINATARIO...
# Cifra ORIGEM (lida por stdin, nunca por argv) para os destinatários, confere o cabeçalho,
# envia com --immutable e confere o hash remoto. Define PUSH_RESULT (enviado | já presente),
# PUSH_HASH e PUSH_BYTES. Qualquer falha: exit != 0.
sq_offsite_push() {
  local src="$1" remote="${2%/}" obj="$3" manifest="$4" workdir="$5"
  shift 5
  local target="${remote}/${obj}" tmp entry known_hash known_bytes hash bytes r
  local -a rargs=()
  for r in "$@"; do rargs+=(-r "${r}"); done

  sq_remote_hash "${target}" || exit 1
  if [ -n "${REMOTE_HASH}" ]; then
    entry="$(sq_manifest_get "${manifest}" "${obj}")"
    known_hash="${entry%%$'\t'*}"
    known_bytes="${entry#*$'\t'}"
    if [ -n "${entry}" ] && [ "${known_hash}" = "${OFFSITE_HASH}:${REMOTE_HASH}" ]; then
      PUSH_RESULT="já presente"
      PUSH_HASH="${known_hash}"
      PUSH_BYTES="${known_bytes}"
      echo "${SQ_SCRIPT}: ${obj} já está no remoto com o hash registrado — pulado." >&2
      return 0
    fi
    echo "${SQ_SCRIPT}: FALHA — ${target} já existe com conteúdo DIFERENTE do que este host registrou" \
         "(${OFFSITE_HASH} remoto ${REMOTE_HASH}, registrado '${known_hash:-nenhum}')." >&2
    echo "${SQ_SCRIPT}: objeto remoto nunca é sobrescrito. Investigue (outro host no mesmo prefixo? envio anterior corrompido?)." >&2
    exit 1
  fi

  tmp="${workdir}/.offsite.${obj}.tmp.$$"
  sq_track_tmp "${tmp}"
  if ! "${AGE}" -e "${rargs[@]}" -o "${tmp}" < "${src}"; then
    sq_die "age falhou cifrando $(basename -- "${src}")."
  fi
  chmod 600 "${tmp}"
  if ! sq_age_header_ok "${tmp}" "$#"; then
    sq_die "FALHA — o cabeçalho age de ${obj} não tem exatamente $# stanza(s) X25519. Nada foi enviado."
  fi
  hash="${OFFSITE_HASH}:$(sq_local_hash "${tmp}")"
  bytes="$(wc -c < "${tmp}" | tr -d ' ')"
  # Registrado ANTES do envio: se o host cair depois do upload, a próxima execução reconhece
  # o objeto pelo hash em vez de acusá-lo de divergente.
  sq_manifest_put "${manifest}" "${obj}" "${hash}" "${bytes}"

  if ! "${RCLONE}" copyto --immutable "${tmp}" "${target}"; then
    sq_die "rclone copyto falhou para ${target}."
  fi
  sq_remote_hash "${target}" || exit 1
  if [ "${OFFSITE_HASH}:${REMOTE_HASH}" != "${hash}" ]; then
    sq_die "FALHA — hash remoto de ${target} (${REMOTE_HASH:-ausente}) não confere com o local (${hash#*:}) depois do envio."
  fi
  rm -f -- "${tmp}"
  PUSH_RESULT="enviado"
  PUSH_HASH="${hash}"
  PUSH_BYTES="${bytes}"
  echo "${SQ_SCRIPT}: ${obj} enviado e conferido (${bytes} bytes, ${hash})." >&2
}
