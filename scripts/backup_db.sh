#!/usr/bin/env bash
# Dump do PostgreSQL e comprime com gzip. Detecta o modo de execução automaticamente:
#
#   - "container": docker exec num container avulso (é como a PRODUÇÃO REAL roda hoje:
#     `sq-prod-db`, sem docker-compose, Postgres na porta 5436). Usa pg_dumpall, que
#     inclui roles + todos os bancos/schemas (schema-per-tenant do django-tenants).
#   - "compose":   docker compose exec num serviço "db" de docker-compose.prod.yml
#     (dump de um único banco via pg_dump). Fallback para ambientes que de fato usam
#     compose (ex.: staging local com este arquivo).
#
# Detecção automática (BACKUP_MODE=auto, default): se o container ${DB_CONTAINER} existir,
# usa o modo "container" — é o caminho comprovado em produção. Senão, cai para "compose".
# Force explícito: BACKUP_MODE=container ou BACKUP_MODE=compose.
# Antes de detectar, o script sonda se o docker está USÁVEL e, se não estiver, FALHA na hora
# citando permissão/daemon em vez de cair para compose (que falharia pelo mesmo motivo, com
# mensagem enganosa). Em modo auto, o modo escolhido é anunciado no stderr.
#
# Uso:
#   POSTGRES_USER=sq POSTGRES_DB=smartquotation BACKUP_DIR=/backups/sq ./scripts/backup_db.sh
#
# Variáveis (todas com default sensato para produção):
#   BACKUP_MODE          auto (default) | container | compose
#   DB_CONTAINER          nome do container avulso (default: sq-prod-db)
#   DB_CONTAINER_HOST     host do Postgres visto de dentro do container (default: 127.0.0.1)
#   DB_CONTAINER_PORT     porta do Postgres dentro do container (default: 5436 — NÃO é a
#                         POSTGRES_PORT=5432 usada pelo Django via rede interna do compose;
#                         são coisas diferentes, por isso variável própria)
#   COMPOSE_FILE          arquivo compose para o modo "compose" (default: docker-compose.prod.yml)
#   DB_SERVICE            nome do serviço db no compose (default: db)
#   DOCKER                binário docker a usar (default: docker; ex.: DOCKER="sudo docker"
#                         nesta VPS o usuário de deploy não está no grupo docker)
#
# Validação por conteúdo (o coração do fix — GOTCHA conhecido: pg_dumpall apontado para a
# porta errada falha em silêncio, sai com exit code 0 e produz um .sql.gz de ~20 bytes; um
# backup que não roda é pior que nenhum backup porque engana quem confia nele):
#   BACKUP_MIN_BYTES      tamanho mínimo do dump JÁ DESCOMPRIMIDO, em bytes (default: 1024)
#   BACKUP_MIN_LINES      linhas mínimas do dump descomprimido (default: 20)
#   BACKUP_EXPECT_SCHEMA  se não-vazio, dump deve conter ao menos 1 ocorrência desta string
#                         (default: engematex — tenant real de produção). Defina "" para
#                         desligar esta checagem específica (ex.: ambiente sem esse tenant).
# Se qualquer checagem falhar, o script sai com código != 0 e NÃO deixa nenhum .sql.gz.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_CONTAINER="${DB_CONTAINER:-sq-prod-db}"
DB_CONTAINER_HOST="${DB_CONTAINER_HOST:-127.0.0.1}"
DB_CONTAINER_PORT="${DB_CONTAINER_PORT:-5436}"
DOCKER="${DOCKER:-docker}"
BACKUP_MODE="${BACKUP_MODE:-auto}"

BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
BACKUP_MIN_LINES="${BACKUP_MIN_LINES:-20}"
BACKUP_EXPECT_SCHEMA="${BACKUP_EXPECT_SCHEMA:-engematex}"

mkdir -p "${BACKUP_DIR}"

FINAL="${BACKUP_DIR}/sq_$(date +%Y%m%d_%H%M%S).sql.gz"
TMPFILE="${FINAL}.tmp"

trap 'rm -f "${TMPFILE}"' EXIT INT TERM

# Sonda se o docker está USÁVEL (daemon respondendo, permissão ok) ANTES de perguntar
# se o container existe. Sem isso, "docker inspect" falhando por PERMISSÃO (não por
# container ausente) seria mal-interpretado como "container não existe" e o script se
# auto-roteia para "compose" — que vai falhar pelo MESMO motivo (docker inacessível),
# só que com uma mensagem de erro que fala de compose quando o problema real é acesso
# ao docker. Um script cujo propósito é não mentir sobre o backup não pode mentir sobre
# qual modo escolheu.
if ! ${DOCKER} info >/dev/null 2>&1; then
  echo "backup_db.sh: docker inacessível via '${DOCKER}' (permissão negada, daemon fora do ar, ou binário ausente)." >&2
  echo "backup_db.sh: o usuário está no grupo 'docker'? tente DOCKER=\"sudo docker\" (é o caso desta VPS de produção)." >&2
  exit 1
fi

detect_mode() {
  if [ "${BACKUP_MODE}" != "auto" ]; then
    printf '%s' "${BACKUP_MODE}"
    return 0
  fi
  # Produção roda como container avulso (sq-prod-db), sem docker-compose (ver
  # docs/HANDOFF_MIGRACAO.md §4 e docs/INFRASTRUCTURE.md). Se o container existir,
  # prefira-o: é o caminho comprovado em produção. Neste ponto o docker já foi
  # confirmado usável acima, então um "inspect" falhando aqui significa mesmo
  # "container não existe" — não "docker inacessível".
  if ${DOCKER} inspect "${DB_CONTAINER}" >/dev/null 2>&1; then
    printf 'container'
  else
    printf 'compose'
  fi
}

MODE="$(detect_mode)"

if [ "${BACKUP_MODE}" = "auto" ]; then
  if [ "${MODE}" = "container" ]; then
    echo "backup_db.sh: modo=container (auto-detectado — container '${DB_CONTAINER}' encontrado)" >&2
  else
    echo "backup_db.sh: modo=compose (auto-detectado — container '${DB_CONTAINER}' não encontrado;" \
         "usando docker compose -f ${COMPOSE_FILE}, serviço '${DB_SERVICE}')" >&2
  fi
else
  echo "backup_db.sh: modo=${MODE} (forçado via BACKUP_MODE)" >&2
fi

dump_container() {
  # A senha vem do próprio ambiente do container (POSTGRES_PASSWORD já está lá porque
  # é assim que o Postgres do container foi iniciado) — não passa em argv, não vaza
  # em `ps`/histórico do shell.
  ${DOCKER} exec "${DB_CONTAINER}" sh -c \
    "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_dumpall -U \"${POSTGRES_USER}\" -h \"${DB_CONTAINER_HOST}\" -p \"${DB_CONTAINER_PORT}\""
}

dump_compose() {
  ${DOCKER} compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
    pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}"
}

case "${MODE}" in
  container) dump_container | gzip > "${TMPFILE}" ;;
  compose) dump_compose | gzip > "${TMPFILE}" ;;
  *)
    echo "backup_db.sh: BACKUP_MODE inválido: '${MODE}' (use auto|container|compose)" >&2
    exit 1
    ;;
esac

# --- Validação por conteúdo: exit code 0 não é suficiente (é exatamente o que engana). ---
validate_dump() {
  local file="$1"
  local size lines hits

  size="$(zcat "${file}" | wc -c)"
  if [ "${size}" -lt "${BACKUP_MIN_BYTES}" ]; then
    echo "backup_db.sh: dump suspeito — apenas ${size} bytes descomprimidos (mínimo ${BACKUP_MIN_BYTES}). Rejeitando backup." >&2
    return 1
  fi

  lines="$(zcat "${file}" | wc -l)"
  if [ "${lines}" -lt "${BACKUP_MIN_LINES}" ]; then
    echo "backup_db.sh: dump suspeito — apenas ${lines} linhas (mínimo ${BACKUP_MIN_LINES}). Rejeitando backup." >&2
    return 1
  fi

  if [ -n "${BACKUP_EXPECT_SCHEMA}" ]; then
    hits="$(zcat "${file}" | grep -c "${BACKUP_EXPECT_SCHEMA}" || true)"
    if [ "${hits}" -eq 0 ]; then
      echo "backup_db.sh: dump não contém nenhuma referência a '${BACKUP_EXPECT_SCHEMA}' — schema esperado ausente. Rejeitando backup." >&2
      return 1
    fi
  fi

  return 0
}

if ! validate_dump "${TMPFILE}"; then
  exit 1
fi

mv "${TMPFILE}" "${FINAL}"
