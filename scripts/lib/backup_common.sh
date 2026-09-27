# shellcheck shell=bash
# Funções comuns aos scripts de backup (backup_db.sh, backup_media.sh, backup_key.sh,
# restore_check.sh). Não é executável sozinho: é carregado com `source`.
#
# Contrato do chamador: `set -euo pipefail`, `umask 077` ANTES de carregar isto, as
# variáveis DOCKER e SQ_SCRIPT (nome do script, usado nas mensagens) definidas, e
# `trap sq_cleanup EXIT INT TERM` com todo temporário registrado via sq_track_tmp.

# Sonda se o docker está USÁVEL (daemon respondendo, permissão ok) ANTES de perguntar se o
# container existe. Sem isso, "docker inspect" falhando por PERMISSÃO seria lido como
# "container não existe" e o script cairia para o compose, que falha pelo mesmo motivo com
# uma mensagem que fala de compose quando o problema real é acesso ao docker.
sq_require_docker() {
  if ! ${DOCKER} info >/dev/null 2>&1; then
    echo "${SQ_SCRIPT}: docker inacessível via '${DOCKER}' (permissão negada, daemon fora do ar, ou binário ausente)." >&2
    echo "${SQ_SCRIPT}: o usuário está no grupo 'docker'? tente DOCKER=\"sudo docker\" ou rode como root (units systemd em ops/systemd/)." >&2
    exit 1
  fi
}

# Imprime running | stopped | absent. Só "running" serve para exec: um container parado
# existe para o `inspect`, mas um `exec` nele falha — e não pode ser confundido com
# "ausente" (o que mandaria o script para o compose, que não é a produção).
sq_container_state() {
  local state
  if ! state="$(${DOCKER} inspect -f '{{.State.Running}}' "$1" 2>/dev/null)"; then
    printf 'absent'
    return 0
  fi
  if [ "${state}" = "true" ]; then
    printf 'running'
  else
    printf 'stopped'
  fi
}

# Recusa retenção que não seja inteiro >= 0 (0 desliga a poda).
sq_check_retention() {
  if ! [[ "${1}" =~ ^[0-9]+$ ]]; then
    echo "${SQ_SCRIPT}: BACKUP_RETENTION_DAYS inválido: '${1}' (use inteiro >= 0; 0 desliga a poda)." >&2
    exit 1
  fi
}

# sq_prune DIR PADRAO DIAS ARQUIVO_NOVO
# Poda arquivos PADRAO mais velhos que DIAS em DIR. Só é chamada DEPOIS de um backup novo
# validado, e nunca apaga ARQUIVO_NOVO (o último válido), mesmo com relógio torto.
sq_prune() {
  local dir="$1" pattern="$2" days="$3" keep="$4" f
  [ "${days}" -gt 0 ] || return 0
  while IFS= read -r -d '' f; do
    [ "${f}" = "${keep}" ] && continue
    rm -f -- "${f}"
    echo "${SQ_SCRIPT}: retenção ${days}d — removido $(basename -- "${f}")" >&2
  done < <(find "${dir}" -maxdepth 1 -type f -name "${pattern}" -mtime +"${days}" -print0)
}

# Temporários do script: tudo que entra aqui é apagado por sq_cleanup, que cada script
# instala no trap (EXIT INT TERM). Um temporário fora desta lista sobrevive a um kill.
SQ_TMPS=()

sq_track_tmp() {
  SQ_TMPS+=("$@")
}

sq_cleanup() {
  if [ "${#SQ_TMPS[@]}" -gt 0 ]; then
    rm -rf -- "${SQ_TMPS[@]}"
  fi
}

# sq_prune_orphan_tmp DIR
# Remove temporários órfãos (*.tmp, *.tmp.<pid>) com mais de 1 dia em DIR — sobra de um
# SIGKILL/queda de energia, que nenhum trap pega. Os de menos de 1 dia ficam: podem ser de
# uma execução que ainda está rodando.
sq_prune_orphan_tmp() {
  local f
  [ -d "$1" ] || return 0
  while IFS= read -r -d '' f; do
    rm -f -- "${f}"
    echo "${SQ_SCRIPT}: temporário órfão removido: $(basename -- "${f}")" >&2
  done < <(find "$1" -maxdepth 1 -type f \( -name '*.tmp' -o -name '*.tmp.*' \) -mtime +0 -print0)
}

# sq_write_status ARQUIVO LINHA...
# Grava um arquivo de status de forma atômica (tmp + mv), modo 0600 pelo umask. O tmp é
# registrado no trap antes de existir.
sq_write_status() {
  local target="$1" tmp
  shift
  tmp="${target}.tmp.$$"
  sq_track_tmp "${tmp}"
  printf '%s\n' "$@" > "${tmp}"
  chmod 600 "${tmp}"
  mv -f -- "${tmp}" "${target}"
}

sq_now_iso() {
  date --iso-8601=seconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z
}
