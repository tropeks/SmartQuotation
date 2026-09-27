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
# Detecção automática (BACKUP_MODE=auto, default): se o container ${DB_CONTAINER} estiver
# RODANDO (inspect .State.Running), usa o modo "container" — é o caminho comprovado em
# produção. Se ele não existir, cai para "compose". Se existir mas estiver PARADO, falha:
# cair para compose nesse caso esconderia o problema real (o banco de produção parado).
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
#   POSTGRES_USER         usuário do dump. Modo compose: OBRIGATÓRIO (junto de POSTGRES_DB).
#                         Modo container: opcional — vazio usa o POSTGRES_USER do próprio
#                         container. Aceita só [A-Za-z0-9_.-] (recusa qualquer outra coisa).
#   BACKUP_RETENTION_DAYS poda sq_*.sql.gz com mais de N dias (default: 14; 0 desliga). A poda
#                         só roda DEPOIS de um backup novo validado e nunca apaga o novo.
#
# Sucesso grava ${BACKUP_DIR}/last_success (timestamp ISO, arquivo, bytes). Falha não toca nele:
# a idade desse arquivo é o sinal de que o backup parou de rodar.
#
# Validação por conteúdo (o coração do fix — GOTCHA conhecido: pg_dumpall apontado para a
# porta errada falha em silêncio, sai com exit code 0 e produz um .sql.gz de ~20 bytes; um
# backup que não roda é pior que nenhum backup porque engana quem confia nele):
#   BACKUP_MIN_BYTES      tamanho mínimo do dump JÁ DESCOMPRIMIDO, em bytes (default: 1024)
#   BACKUP_MIN_LINES      linhas mínimas do dump descomprimido (default: 20)
#   BACKUP_EXPECT_SCHEMA  se não-vazio, dump deve conter ao menos 1 ocorrência desta string
#                         (default: engematex — tenant real de produção). Defina "" para
#                         desligar esta checagem específica (ex.: ambiente sem esse tenant).
#   Rodapé obrigatório    o dump tem que TERMINAR com o rodapé que o Postgres só escreve ao
#                         concluir: "-- PostgreSQL database cluster dump complete" (pg_dumpall,
#                         modo container) ou "-- PostgreSQL database dump complete" (pg_dump,
#                         modo compose). Pega dump truncado que já passou do tamanho mínimo.
# Se qualquer checagem falhar, o script sai com código != 0 e NÃO deixa nenhum .sql.gz.
#
# Permissões: umask 077 antes de qualquer arquivo — o dump tem preço cifrado, mas também
# hashes de senha dos roles e todo o resto em claro. Diretório 0700, arquivos 0600.

set -euo pipefail
umask 077

SQ_SCRIPT="backup_db.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR source=lib/backup_common.sh
. "${SCRIPT_DIR}/lib/backup_common.sh"

BACKUP_DIR="${BACKUP_DIR:-${POSTGRES_BACKUP_DIR:-/backups/sq}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_CONTAINER="${DB_CONTAINER:-sq-prod-db}"
DB_CONTAINER_HOST="${DB_CONTAINER_HOST:-127.0.0.1}"
DB_CONTAINER_PORT="${DB_CONTAINER_PORT:-5436}"
DOCKER="${DOCKER:-docker}"
BACKUP_MODE="${BACKUP_MODE:-auto}"
POSTGRES_USER="${POSTGRES_USER:-}"
POSTGRES_DB="${POSTGRES_DB:-}"

BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
BACKUP_MIN_LINES="${BACKUP_MIN_LINES:-20}"
BACKUP_EXPECT_SCHEMA="${BACKUP_EXPECT_SCHEMA-engematex}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

FOOTER_CLUSTER="-- PostgreSQL database cluster dump complete"
FOOTER_DB="-- PostgreSQL database dump complete"

# --- Entradas que vão parar num comando dentro do container: lista branca, sem exceção. ---
# O dump roda via `sh -c` no container; os valores seguem como argv posicional ("$1"...),
# nunca interpolados no texto do comando. A lista branca é a segunda camada: um valor com
# aspas, `;`, `$` ou espaço não tem uso legítimo aqui e é recusado antes de tocar o docker.
if [ -n "${POSTGRES_USER}" ] && ! [[ "${POSTGRES_USER}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]]; then
  echo "${SQ_SCRIPT}: POSTGRES_USER inválido (aceito: letras, dígitos, _ . -). Recusando." >&2
  exit 1
fi
if ! [[ "${DB_CONTAINER_HOST}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.:-]*$ ]]; then
  echo "${SQ_SCRIPT}: DB_CONTAINER_HOST inválido (aceito: hostname ou IP). Recusando." >&2
  exit 1
fi
if ! [[ "${DB_CONTAINER_PORT}" =~ ^[0-9]{1,5}$ ]]; then
  echo "${SQ_SCRIPT}: DB_CONTAINER_PORT inválido (aceito: número de porta). Recusando." >&2
  exit 1
fi
sq_check_retention "${BACKUP_RETENTION_DAYS}"

mkdir -p "${BACKUP_DIR}"

FINAL="${BACKUP_DIR}/sq_$(date +%Y%m%d_%H%M%S).sql.gz"
TMPFILE="${FINAL}.tmp"

trap 'rm -f "${TMPFILE}"' EXIT INT TERM

sq_require_docker

detect_mode() {
  if [ "${BACKUP_MODE}" != "auto" ]; then
    printf '%s' "${BACKUP_MODE}"
    return 0
  fi
  # Produção roda como container avulso (sq-prod-db), sem docker-compose (ver
  # docs/HANDOFF_MIGRACAO.md §4 e docs/INFRASTRUCTURE.md). Neste ponto o docker já foi
  # confirmado usável, então "absent" significa mesmo "container não existe".
  case "$(sq_container_state "${DB_CONTAINER}")" in
    running) printf 'container' ;;
    stopped) printf 'stopped' ;;
    *) printf 'compose' ;;
  esac
}

MODE="$(detect_mode)"

if [ "${MODE}" = "stopped" ]; then
  echo "${SQ_SCRIPT}: container '${DB_CONTAINER}' existe mas está PARADO — não há de onde tirar o dump." >&2
  echo "${SQ_SCRIPT}: não caio para o compose: a produção é o container avulso. Suba-o ou force BACKUP_MODE." >&2
  exit 1
fi

if [ "${BACKUP_MODE}" = "auto" ]; then
  if [ "${MODE}" = "container" ]; then
    echo "${SQ_SCRIPT}: modo=container (auto-detectado — container '${DB_CONTAINER}' rodando)" >&2
  else
    echo "${SQ_SCRIPT}: modo=compose (auto-detectado — container '${DB_CONTAINER}' não encontrado;" \
         "usando docker compose -f ${COMPOSE_FILE}, serviço '${DB_SERVICE}')" >&2
  fi
else
  echo "${SQ_SCRIPT}: modo=${MODE} (forçado via BACKUP_MODE)" >&2
fi

if [ "${MODE}" = "compose" ] && { [ -z "${POSTGRES_USER}" ] || [ -z "${POSTGRES_DB}" ]; }; then
  echo "${SQ_SCRIPT}: modo compose exige POSTGRES_USER e POSTGRES_DB (vazios ou não definidos)." >&2
  echo "${SQ_SCRIPT}: carregue o .env.prod com 'set -a && source .env.prod && set +a' ou use a unit systemd." >&2
  exit 1
fi

dump_container() {
  # A senha vem do próprio ambiente do container (POSTGRES_PASSWORD já está lá porque é
  # assim que o Postgres do container foi iniciado) — não passa em argv, não vaza em `ps`.
  # Usuário/host/porta entram como argv POSICIONAL do sh ($1 $2 $3): o texto do comando é
  # constante, nada do host é re-parseado pelo shell do container. POSTGRES_USER vazio →
  # usa o do próprio container.
  # shellcheck disable=SC2016  # as expansões são para o sh DO CONTAINER, de propósito
  ${DOCKER} exec "${DB_CONTAINER}" sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dumpall -U "${1:-$POSTGRES_USER}" -h "$2" -p "$3"' \
    sh "${POSTGRES_USER}" "${DB_CONTAINER_HOST}" "${DB_CONTAINER_PORT}"
}

dump_compose() {
  ${DOCKER} compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
    pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}"
}

case "${MODE}" in
  container) dump_container | gzip > "${TMPFILE}"; EXPECTED_FOOTER="${FOOTER_CLUSTER}" ;;
  compose) dump_compose | gzip > "${TMPFILE}"; EXPECTED_FOOTER="${FOOTER_DB}" ;;
  *)
    echo "${SQ_SCRIPT}: BACKUP_MODE inválido: '${MODE}' (use auto|container|compose)" >&2
    exit 1
    ;;
esac

# --- Validação por conteúdo: exit code 0 não é suficiente (é exatamente o que engana). ---
validate_dump() {
  local file="$1"
  local size lines hits

  if ! gzip -t "${file}" 2>/dev/null; then
    echo "${SQ_SCRIPT}: gzip corrompido. Rejeitando backup." >&2
    return 1
  fi

  size="$(zcat "${file}" | wc -c)"
  if [ "${size}" -lt "${BACKUP_MIN_BYTES}" ]; then
    echo "${SQ_SCRIPT}: dump suspeito — apenas ${size} bytes descomprimidos (mínimo ${BACKUP_MIN_BYTES}). Rejeitando backup." >&2
    return 1
  fi

  lines="$(zcat "${file}" | wc -l)"
  if [ "${lines}" -lt "${BACKUP_MIN_LINES}" ]; then
    echo "${SQ_SCRIPT}: dump suspeito — apenas ${lines} linhas (mínimo ${BACKUP_MIN_LINES}). Rejeitando backup." >&2
    return 1
  fi

  if [ -n "${BACKUP_EXPECT_SCHEMA}" ]; then
    hits="$(zcat "${file}" | grep -c -F -- "${BACKUP_EXPECT_SCHEMA}" || true)"
    if [ "${hits}" -eq 0 ]; then
      echo "${SQ_SCRIPT}: dump não contém nenhuma referência a '${BACKUP_EXPECT_SCHEMA}' — schema esperado ausente. Rejeitando backup." >&2
      return 1
    fi
  fi

  # Rodapé nas últimas linhas: o Postgres só o escreve ao terminar. Últimas 20 (e não a
  # última) porque versões com \restrict/\unrestrict fecham o arquivo depois do rodapé.
  if ! zcat "${file}" | tail -n 20 | grep -q -x -F -- "${EXPECTED_FOOTER}"; then
    echo "${SQ_SCRIPT}: dump sem o rodapé '${EXPECTED_FOOTER}' — truncado ou interrompido. Rejeitando backup." >&2
    return 1
  fi

  return 0
}

if ! validate_dump "${TMPFILE}"; then
  exit 1
fi

chmod 600 "${TMPFILE}"
mv "${TMPFILE}" "${FINAL}"

BYTES="$(wc -c < "${FINAL}" | tr -d ' ')"
sq_write_status "${BACKUP_DIR}/last_success" \
  "timestamp=$(sq_now_iso)" \
  "file=$(basename -- "${FINAL}")" \
  "bytes=${BYTES}"

sq_prune "${BACKUP_DIR}" 'sq_*.sql.gz' "${BACKUP_RETENTION_DAYS}" "${FINAL}"

echo "${SQ_SCRIPT}: ok — $(basename -- "${FINAL}") (${BYTES} bytes)" >&2
