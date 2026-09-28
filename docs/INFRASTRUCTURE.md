---
# Contrato de documentação (Maestro E16).
#
# Como o SQ roda, faz backup, restaura e prova o que está no repo. O cover é o que, se
# mudar, torna este doc mentiroso: compose de dev e de produção, imagem, entrypoint,
# scripts de backup e o exemplo de ambiente de produção. `.github/` fica fora de propósito
# (a §5 descreve o CI, mas o contrato do CI é o próprio ci.yml).
#
# Emenda de 27/09/2026 (Conformador, INTENT v2 carimbado), conferida contra o código em
# 288a8ca: §0 nova (realidade), §5 trocada pelo CI que existe, §6 separa o que o script
# faz do que é desenho, §10 (SQ na F1 do Core) e §11 (prova headless) novas. §2–§4, §7–§9
# ficam como desenho-alvo, marcadas como tal.
#
# Emenda da ordem 002 (27/09/2026): §6 reescrita — backup diário via systemd (dump + mídia +
# chave com prova de decifra), drill semanal de restore, runbook de restore para containers
# avulsos; covers ganham os scripts novos e as units de ops/systemd/.
#
# Emenda da ordem 003 (27/09/2026): off-site cifrado com age (offsite_push.sh, dump + mídia
# para dois destinatários) e custódia off-site da chave em remote próprio
# (offsite_key_push.sh); drill trimestral a partir do off-site; covers ganham os dois scripts
# e a lib. Revisão da 003: runner backup_run.sh (segue depois de falha), backfill, conferência
# do off-site no drill semanal, separação de credencial lida do rclone.conf, custódia MANUAL
# do .env.prod.
#
# Emenda da ordem 009 (28/09/2026): achado do Conformador ("produção roda Postgres 15, dev e
# CI rodam 16") apurado contra o repo — não provado (a fonte é docker-compose.prod.yml, que a
# produção não usa; o indício mais forte do repo, o incidente de catálogo de 18/07/2026,
# aponta para 16, com ressalva). Dossiê completo e leitura decisiva para o Capitão em
# docs/ship/ORDEM_009_POSTGRES.md. §0 ganha a linha "Postgres (major)"; §2 nota a divergência
# do compose.prod; §5 registra a matriz de CI pendente (docs/patches/009-ci-postgres-matrix.patch)
# e o teste local (scripts/ci/suite_local_pg.sh); §6 registra que restore_check.sh deriva a
# imagem do cabeçalho do dump em vez de fixar postgres:15; §11 registra os nomes de job da
# matriz.
covers:
  - docker-compose.yml
  - docker-compose.prod.yml
  - backend/Dockerfile
  - backend/entrypoint.sh
  - scripts/backup_db.sh
  - scripts/backup_media.sh
  - scripts/backup_key.sh
  - scripts/restore_check.sh
  - scripts/lib/backup_common.sh
  - scripts/offsite_push.sh
  - scripts/backup_run.sh
  - scripts/offsite_key_push.sh
  - scripts/lib/offsite_common.sh
  - ops/systemd/sq-backup.service
  - ops/systemd/sq-backup.timer
  - ops/systemd/sq-restore-check.service
  - ops/systemd/sq-restore-check.timer
  - ops/systemd/backup.env.example
  - .env.prod.example
reviewed: 2026-09-28
---
# INFRASTRUCTURE.md — SmartQuotation

> **Status:** v1.1, emendada em 27/09/2026 contra o repo e a direção carimbada
> (`.maestro/INTENT.md` v2). **Referência:** ARCHITECTURE.md, SECURITY.md,
> HANDOFF_MIGRACAO.md, `cognitive-core/docs/FASES.md` §4 e §10.
>
> **Como ler:** a §0 é a realidade de hoje. As §2–§4 e §7–§9 são o **desenho-alvo** da v1.0
> (registry, Caddy, staging, domínio `smartquotation.com.br`) e **não existem** na produção
> atual; ficam como referência, não como procedimento.

---

## 0. Realidade em 27/09/2026

| Item | Como está | Fonte |
|---|---|---|
| Produção | `quotation.qtec.me`, VPS atrás de `cloudflared`; containers avulsos `sq-web-proto`, `sq-prod-db`, `sq-prod-redis`, imagem `smartquotation:proto`, volumes nomeados | HANDOFF_MIGRACAO §2.2 e §4 |
| Deploy | **Manual**, sem pipeline (último: 28/07/2026). Merge em `main` não sobe nada | HANDOFF §4 |
| Compose de produção | `docker-compose.prod.yml` existe no repo, mas a produção **não** sobe por ele | HANDOFF §4 |
| Porta do app | O compose de produção publica `8000:8000` em todas as interfaces; ir para loopback é a F1-04 (§10) | `docker-compose.prod.yml:21-22` |
| Rollback | Imagem `smartquotation:rollback-20260718` + dump `~/backups/sq/pre_prancha_20260728_143633.sql.gz` | HANDOFF §4 |
| Staging | Não existe | — |
| Backup | Ver §6: scripts e units prontos para os containers avulsos (dump + mídia + chave com prova de decifra, drill semanal, off-site cifrado com `age` e chave em custódia off-site separada), **não instalados** (gate do Capitão) | `scripts/backup_*.sh`, `scripts/offsite_*.sh`, `ops/systemd/`, HANDOFF §4 |
| CI | `.github/workflows/ci.yml`, seis jobs de prova, nenhum de deploy (§5) | ci.yml |
| Monitoramento | Só o `/health/` e o `HEALTHCHECK` da imagem; nada externo avisa se cair (§7 é alvo) | `backend/Dockerfile:53-54` |
| Postgres (major) | **Não registrada no repo.** `docker-compose.prod.yml` declara `postgres:15`, mas produção não roda por ele (linha acima); o indício mais forte do repo (incidente de catálogo de 18/07/2026) aponta para 16, com ressalva. Leitura decisiva (`docker exec sq-prod-db cat PG_VERSION`, etc.) para o Capitão em `docs/ship/ORDEM_009_POSTGRES.md` | ordem 009, `docs/ship/ORDEM_009_POSTGRES.md` |

A migração da produção para outro host **não está em curso**: é decisão futura do Capitão.

---

## 1. Ambientes

| Ambiente | Propósito | URL | Hospedagem |
|---|---|---|---|
| `dev` | Desenvolvimento local | `localhost:8000` (venv) ou `:8001` (compose) | `docker-compose.yml` (db 5436, redis 6380) |
| `staging` | *Alvo, não existe* | — | — |
| `production` | Clientes reais | `quotation.qtec.me` | VPS + `cloudflared` (§0) |

**Regra-alvo:** nenhum deploy vai direto para `production` — sempre passa por `staging` primeiro.
Hoje não há staging; até existir, o gate é a CI verde no commit que vai para a imagem.
**Dados:** nenhum dump de produção sai da instância (INTENT, Limites); fixture é sintética.

---

## 2. Docker Compose — Produção (desenho-alvo)

> **Não é o `docker-compose.prod.yml` do repo.** O versionado builda a imagem local, sobe
> `web`/`worker`/`beat` + `postgres:15` + `redis:7-alpine` em `sq_net`, com `media_data` em
> `/app/backend/media` e sem Caddy, registry nem job de backup. E a produção atual nem usa
> esse compose (§0). O bloco abaixo é o alvo da v1.0.
>
> **Nota da ordem 009:** o `postgres:15` do compose versionado (linha acima) é a origem da
> premissa "produção roda 15" — mas como esse compose nunca é usado pela produção real, ele
> não prova a major do cluster de fato. Dossiê de evidência e leitura decisiva em
> `docs/ship/ORDEM_009_POSTGRES.md`.

```yaml
# docker-compose.prod.yml
version: "3.9"

services:

  web:
    image: registry.smartquotation.com.br/app:${IMAGE_TAG}
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - uploads:/data/uploads
      - static:/data/static
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 1G

  worker:
    image: registry.smartquotation.com.br/app:${IMAGE_TAG}
    command: celery -A smartquotation worker -l info -Q default,documents,calculations --concurrency=4
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      - redis
      - db
    volumes:
      - uploads:/data/uploads
    deploy:
      resources:
        limits:
          memory: 1G

  beat:
    image: registry.smartquotation.com.br/app:${IMAGE_TAG}
    command: celery -A smartquotation beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      - redis
      - db

> Observação operacional (H2.5.2): o conector Protheus usa **um beat global único** no app Celery.
> A agenda recorrente do pull fica definida no app (`integrations.protheus.dispatch_recurring_pulls`)
> e usa `PROTHEUS_PULL_INTERVAL_MINUTES` para definir a cadência sem editar código.
> O dispatcher só enfileira tenants ativos com integração Protheus habilitada.
> Não é necessário um beat por tenant.

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file: .env.prod
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./config/postgres/postgresql.conf:/etc/postgresql/postgresql.conf
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
      - static:/data/static:ro
    depends_on:
      - web

  backup:
    image: registry.smartquotation.com.br/backup:latest
    restart: unless-stopped
    env_file: .env.prod
    volumes:
      - postgres_data:/var/lib/postgresql/data:ro
      - uploads:/data/uploads:ro
      - backups:/backups
    # roda pg_dump + rclone sync a cada 6h

volumes:
  postgres_data:
  redis_data:
  uploads:
  static:
  caddy_data:
  caddy_config:
  backups:
```

---

## 3. Caddyfile (desenho-alvo)

> Não há Caddy no repo nem na produção: a entrada hoje é o `cloudflared` (§0), e na F1 é o
> túnel por instância (F1-14, §10).

```caddyfile
{
  email ops@smartquotation.com.br
  admin off
}

# Multi-tenant: todos os subdomínios → mesmo backend
*.smartquotation.com.br {
  tls {
    dns cloudflare {env.CF_API_TOKEN}   # wildcard cert via DNS challenge
  }

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Frame-Options "DENY"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "strict-origin-when-cross-origin"
    Permissions-Policy "geolocation=(), camera=(), microphone=()"
    -Server
  }

  # Static files servidos diretamente pelo Caddy
  handle /static/* {
    root * /data/static
    file_server
  }

  # Tudo mais vai para o Django
  reverse_proxy web:8000 {
    header_up X-Forwarded-For {remote_host}
    header_up X-Forwarded-Proto {scheme}
    header_up X-Tenant-Slug {labels.1}    # extrai o slug do subdomínio
  }

  # Rate limiting básico no nível do proxy
  rate_limit {
    zone login_zone {
      match path /api/v1/auth/login
      key {remote_host}
      events 5
      window 60s
    }
  }

  log {
    output file /var/log/caddy/access.log {
      roll_size 100mb
      roll_keep 10
    }
    format json
  }
}
```

---

## 4. Variáveis de Ambiente (`.env.prod`) (desenho-alvo)

> O contrato real é `.env.prod.example`: `DJANGO_*`, `FIELD_ENCRYPTION_KEY`, `POSTGRES_*`,
> `REDIS_URL`, `USE_S3`, `PROTHEUS_PULL_INTERVAL_MINUTES`, `POSTGRES_BACKUP_DIR`,
> `MEDIA_BACKUP_DIR`. Não há `REDIS_PASSWORD`, Sentry, SMTP, `CF_API_TOKEN` nem chave `age`.
> `FIELD_ENCRYPTION_KEY` cifra o `MaterialPrice`: perdê-la torna o backup do banco ilegível
> nessa parte, então ela precisa de cópia fora do host (ver §10, F1-15).

```bash
# Django
DJANGO_SECRET_KEY=<gerado com: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_SETTINGS_MODULE=smartquotation.settings.production
DJANGO_ALLOWED_HOSTS=*.smartquotation.com.br
DJANGO_DEBUG=False

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=smartquotation
POSTGRES_USER=sq_app
POSTGRES_PASSWORD=<gerado>
DATABASE_URL=postgresql://sq_app:<pass>@db:5432/smartquotation

# Redis
REDIS_PASSWORD=<gerado>
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}

# Storage
UPLOADS_ROOT=/data/uploads
STATIC_ROOT=/data/static

# Email
EMAIL_HOST=smtp.seu-provedor.com.br
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@smartquotation.com.br
EMAIL_HOST_PASSWORD=<senha>
DEFAULT_FROM_EMAIL=SmartQuotation <noreply@smartquotation.com.br>

# Sentry
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production

# Backup
BACKUP_ENCRYPTION_PUBLIC_KEY=<age public key>
RCLONE_REMOTE=b2:smartquotation-backups

# Caddy
CF_API_TOKEN=<Cloudflare DNS API token para wildcard cert>
```

---

## 5. CI — o que existe

Um workflow só, `.github/workflows/ci.yml`. Dispara em push para `main` e `feat/**` e em PR
para `main`; **não faz deploy**. Branch `conform/*` só roda CI via PR.

| Job | O que prova |
|---|---|
| `pricing-engine` | Os quatro gates stdlib do motor (§11) |
| `ops-tests` | Contrato de `backup_db.sh`/`backup_media.sh`, volume de media, storage de proposals, lockfiles. `test_backup_script` também roda `test_backup_db_hardening`, `test_atomic_backup`, `test_backup_key`, `test_restore_check`, `test_backup_units`, os de off-site e runner (ordem 003) e, desde a ordem 009, `test_restore_image_major`, `test_suite_receipt` e `test_suite_local_pg` (docker, `gh` e `git` falsos). `test_backup_script` e `test_media_backup` **leem este doc** (cron com `set -a`, `media_data`) |
| `pip-audit` | CVEs em `base.lock` e `ci.lock`, sem re-resolver a árvore |
| `django-check` | `manage.py check` + `makemigrations --check` |
| `django-test` | `manage.py test apps` contra `postgres:16-alpine`, com WeasyPrint obrigatório |
| `docker-build` | `docker build -f backend/Dockerfile` (só em `main`/PR para `main`, depois do `django-test`) |

O desenho de deploy da v1.0 (registry, Trivy, staging, aprovação manual, cobertura ≥ 80%,
regressão PVElite) não existe; PVElite como gate está fora de escopo (INTENT).

**Ordem 009 — matriz de major do Postgres (pendente do Capitão):** `django-test` hoje só
prova `postgres:16-alpine`, que não é comprovadamente a major da produção (§0). O patch
`docs/patches/009-ci-postgres-matrix.patch` troca esse job único por uma matriz Postgres 15 e
16 (`Testes Django (multi-tenant) — Postgres 15` / `— Postgres 16`); até o Capitão aplicá-lo,
a prova local contra uma major específica é `scripts/ci/suite_local_pg.sh <major>` (suíte
Django contra Postgres efêmero em `127.0.0.1`, `--rm`). Dossiê completo em
`docs/ship/ORDEM_009_POSTGRES.md`.

---

## 6. Backup e Recuperação

> Emendas das ordens 002 e 003 (27/09/2026). Tudo abaixo está no repo e **provado com docker,
> age e rclone falsos** (`tests/test_backup_*`, `tests/test_restore_check.py`,
> `tests/test_media_backup.py`, `tests/test_offsite_*`); nada disso foi instalado nem executado
> contra a produção. Instalar as units no host de produção
> é **gate ship do Capitão**.

### O que roda, onde

| Peça | Faz | Não faz |
|---|---|---|
| `scripts/backup_db.sh` | `pg_dumpall` no container avulso `sq-prod-db` (porta 5436, senha do env do próprio container), ou `pg_dump` via compose onde houver compose. Detecta o modo por `.State.Running`; container parado **falha** (não cai para compose); docker inacessível falha na hora. `umask 077`, escrita atômica (`.tmp` + `mv`). **Valida pelo conteúdo**: gzip íntegro, tamanho e linhas mínimos, schema `engematex` presente e o **rodapé** `-- PostgreSQL database cluster dump complete` (ou `... database dump complete` no compose) — dump truncado é rejeitado. Usuário/host/porta vão ao `sh` do container como argv posicional e passam por lista branca. Grava `last_success`; poda `sq_*.sql.gz` > `BACKUP_RETENTION_DAYS` (14) só depois de um backup novo validado | PITR (cifra e off-site: `offsite_push.sh`) |
| `scripts/backup_media.sh` | `tar czf - -C / app/backend/media` no `sq-web-proto` (volume `media_data` montado em `/app/backend/media`), mesma detecção/fail-fast. Valida com `tar tzf`: exige `app/backend/media/` e ≥1 entrada sob ele (ou `MEDIA_ALLOW_EMPTY=1`). Grava `media_last_success`; retenção igual | Idem |
| `scripts/backup_key.sh` | Copia a `FIELD_ENCRYPTION_KEY` do env do `sq-web-proto` para `${KEY_BACKUP_DIR}/field_encryption_key` (0600), com fingerprint `sha256` truncado ao lado; preserva a anterior se a chave mudou. **Prova de decifra**: tira um `preco_brl_kg` de `engematex.materials_materialprice` do dump mais recente e roda Fernet **dentro** do container, com chave e token por **stdin**. A prova imprime só `ok`, `falha` ou `sem amostra` (exit 0 / 2 / 3); saída inesperada do container é descartada | Custódia fora do host (`offsite_key_push.sh`) |
| `scripts/restore_check.sh` | Drill: sobe um Postgres efêmero (`--network none`, `--rm`, nome único), aplica o dump mais recente, confere schema `engematex`, tabelas `quotations_quotation`, `quotations_quotationitem`, `materials_material`, `materials_materialprice` e cotações ≥ `RESTORE_MIN_QUOTATIONS`; valida o tar de mídia mais recente. **Ordem 009:** sem `RESTORE_IMAGE`, a imagem passa a ser derivada do cabeçalho `-- Dumped from database version` do próprio dump (`postgres:<major>`), em vez de fixar `postgres:15` (que nunca foi comprovadamente a major da produção — dossiê em `docs/ship/ORDEM_009_POSTGRES.md`); `RESTORE_IMAGE` numa major menor que a do dump reprova, e `restore_last_success` grava `source_major=`/`image=`. Com `OFFSITE_REMOTE` definido, confere **sem baixar** que o dump mais novo confirmado no `offsite_manifest` é o dump local mais novo, tem menos de `OFFSITE_MAX_AGE_HOURS` e está no remote com o hash registrado (`rclone hashsum`); com `OFFSITE_HASH_DOWNLOAD=1` **não baixa**: confere só presença e tamanho (`rclone lsjson`), avisa no journal ("hash indisponível sem download") e grava `offsite_check=tamanho`. Remote mudo, objeto ausente ou diferente = falha. Container sempre removido (trap). Saída só com contagens e nomes de tabela. Grava `restore_last_success` com a duração | Restore em produção; medir RPO |
| `scripts/offsite_key_push.sh` | Se o fingerprint da chave mudou desde o último envio (`offsite_key_fingerprint`), cifra a `FIELD_ENCRYPTION_KEY` com `age` **só** para a chave de recuperação da Quantum (lida do arquivo 0600 por stdin) e envia `field_encryption_key.<fpr>.<UTC>.age` para `OFFSITE_KEY_REMOTE`, com hash remoto conferido. Chave igual: confere (`hashsum`) que o objeto dela continua lá | Enviar a chave para o remote do dump (recusa se for o mesmo, um dentro do outro ou a mesma seção do `rclone.conf`) |
| `scripts/offsite_push.sh` | Cifra, com backfill (todo dump e tar local ainda não confirmado, do mais antigo para o mais novo), com `age` para **dois** destinatários (instância + recuperação), confere no cabeçalho uma stanza por destinatário, do tipo dele (`X25519` ou `piv-p256`), envia com `rclone copyto --immutable` para `OFFSITE_REMOTE`, confere o hash remoto e grava `offsite_last_success` | Apagar no remoto; sobrescrever objeto remoto; escolher provedor |
| `scripts/backup_run.sh` | Runner da unit: `backup_db.sh` → `backup_media.sh` → `backup_key.sh` → `offsite_key_push.sh` → `offsite_push.sh`, **seguindo depois de falha** (o off-site do dump tem valor sem a chave); registra cada exit em `backup_run_last` e sai != 0 no fim se alguma etapa falhou. INT/TERM (`systemctl stop`, timeout): mata a etapa em curso, **não** segue, sai 130/143 e registra `interrupted=<etapa>` | — |
| `ops/systemd/sq-backup.{service,timer}` | Todo dia 03:00 (`Persistent=true`, `RandomizedDelaySec=5min`): `backup_run.sh`, `Type=oneshot`; qualquer etapa com erro deixa a unit `failed` | — |
| `ops/systemd/sq-restore-check.{service,timer}` | Toda segunda 05:00: `restore_check.sh` | — |

As units rodam como `root` (o usuário de deploy não está no grupo docker, e dar o grupo a ele
seria root permanente só para o backup), com `ProtectSystem=strict` + `ReadWritePaths` só nos
diretórios de backup, `PrivateTmp`, `NoNewPrivileges`, `UMask=0077`, e
`EnvironmentFile=/etc/smartquotation/backup.env` — um env file **dedicado** (root, 0600) só com
variáveis `BACKUP_*`, `KEY_*`, `RESTORE_*`, `MEDIA_*`, `OFFSITE_*`, `RCLONE_CONFIG`,
`RCLONE_CACHE_DIR`, `DB_CONTAINER*` e afins (modelo:
`ops/systemd/backup.env.example`). As units **não** carregam o `.env.prod`: ele poria
`FIELD_ENCRYPTION_KEY`, `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` e `AWS_*` no ambiente de todo
processo da unit, e nenhum script precisa deles (senha e chave são lidas de dentro dos
containers). `POSTGRES_USER` fica fora de propósito: no modo container vale o do próprio
`sq-prod-db`. Falha = unit `failed`, visível em `systemctl --failed` e no journal.

**A `FIELD_ENCRYPTION_KEY` NUNCA viaja junto com o dump no off-site (ordem 003): vai para
custódia separada.** Por isso ela mora em `KEY_BACKUP_DIR` (default
`/var/lib/smartquotation/key-backup`), fora do `BACKUP_DIR`: o `backup_key.sh` recusa rodar se
um diretório estiver dentro do outro, e nenhum log, status ou arquivo do `BACKUP_DIR` contém a
chave (testado com chave sintética). Sem a chave, o dump restaura com preços ilegíveis; sem o
dump, a chave não serve para nada — os dois juntos no mesmo destino é que não podem estar.

**O `/opt/smartquotation/.env.prod` também é material de chave**: ele contém a
`FIELD_ENCRYPTION_KEY` (e as demais senhas da aplicação). Segue **custódia separada** da chave —
e essa custódia é **MANUAL e offline, do Capitão**: nenhum script copia, cifra nem envia o
`.env.prod` (o `offsite_key_push.sh` leva só a `FIELD_ENCRYPTION_KEY`). Ele **nunca** vai no
pacote do dump da ordem 003 — nem inteiro, nem como "config para subir o host novo". A cópia é
passo do checklist do ship e de cada troca de segredo (subseção "Off-site cifrado").

**Restore testado:** o único registrado em produção é o dump pré-Prancha de 28/07/2026
(`~/backups/sq/pre_prancha_20260728_143633.sql.gz`, "verificado" no HANDOFF §4). A partir da
instalação das units, o drill semanal é o registro (`restore_last_success`). Lição já paga:
`pg_dumpall` na porta errada gera arquivo de 20 bytes com exit 0; backup se valida pelo
**conteúdo** (tamanho, rodapé, restore), nunca pelo exit code.

### Instalar as units (gate ship do Capitão — NÃO executado)

Pré-requisitos a conferir no host: o repo (com `scripts/`, `scripts/lib/` e `ops/systemd/`)
em `/opt/smartquotation`, e o `RESTORE_DB` do `backup.env` igual ao `POSTGRES_DB` do
`sq-prod-db`. O `backup.env` **não** leva `DOCKER` com sudo (o `NoNewPrivileges` bloqueia).

```bash
# como root no host de produção
install -d -m 0700 /backups/sq /var/lib/smartquotation/key-backup /etc/smartquotation \
                   /var/lib/smartquotation/offsite-cache
install -m 0600 -o root -g root /opt/smartquotation/ops/systemd/backup.env.example \
                /etc/smartquotation/backup.env      # revise os valores; nenhum segredo vai aqui
install -m 0644 /opt/smartquotation/ops/systemd/sq-backup.service \
                /opt/smartquotation/ops/systemd/sq-backup.timer \
                /opt/smartquotation/ops/systemd/sq-restore-check.service \
                /opt/smartquotation/ops/systemd/sq-restore-check.timer /etc/systemd/system/
docker pull postgres:<major da produção>    # o drill roda sem rede: a imagem tem que estar local.
                                             # restore_check.sh sobe postgres:<major lida do
                                             # cabeçalho do dump>; puxe essa major. Qual é: a
                                             # leitura do host na §3 de docs/ship/ORDEM_009_POSTGRES.md
                                             # (não é necessariamente 15).
systemctl daemon-reload
systemctl start sq-backup.service           # 1ª execução assistida
journalctl -u sq-backup.service -n 50 --no-pager
systemctl start sq-restore-check.service    # 1º drill assistido
systemctl enable --now sq-backup.timer sq-restore-check.timer
systemctl list-timers 'sq-*'
```

Antes do `systemctl start sq-backup.service`, faça o preparo do off-site (subseção
"Off-site cifrado", passos do ship): sem `rclone.conf` e sem as chaves públicas reais no
`backup.env`, a unit falha no `offsite_key_push.sh` (de propósito).

Se mudar `BACKUP_DIR`, `KEY_BACKUP_DIR` ou `RCLONE_CACHE_DIR` no `backup.env`, mude o
`ReadWritePaths` das units junto (o teste `test_backup_units` confere o par no `backup.env.example` e que nenhuma unit
referencia o `.env.prod`).

### Como ler o resultado

| Arquivo | Escrito por | Conteúdo |
|---|---|---|
| `/backups/sq/last_success` | `backup_db.sh`, só no sucesso | `timestamp=`, `file=`, `bytes=` |
| `/backups/sq/media_last_success` | `backup_media.sh`, só no sucesso | `timestamp=`, `file=`, `bytes=`, `entries=` |
| `/var/lib/smartquotation/key-backup/last_success` | `backup_key.sh`, só com prova `ok` | `timestamp=`, `result=ok`, `dump=`, `key_sha256_16=` |
| `/var/lib/smartquotation/key-backup/last_proof` | `backup_key.sh`, toda prova | `result=ok\|falha\|sem amostra`, `dump=`, `key_sha256_16=` |
| `/backups/sq/restore_last_success` | `restore_check.sh`, só no sucesso | `dump=`, `schema=`, `quotations=`, `tables=`, `psql_errors=`, `media_entries=`, `duration_s=` |
| `/backups/sq/offsite_last_success` | `offsite_push.sh`, só com hash e cabeçalho conferidos | `timestamp=`, `remote=`, `dump=`, `dump_result=enviado\|já presente`, `dump_bytes=`, `dump_hash=`, idem `media_*` |
| `/backups/sq/offsite_manifest` | `offsite_push.sh` | objeto, hash, bytes e estado (`pendente` antes do envio, `ok` depois do hash conferido) de cada `.age` — é o que reconhece no remoto o que este host enviou e o que o backfill ainda deve |
| `/backups/sq/backup_run_last` | `backup_run.sh`, toda execução | `timestamp=`, `<etapa>=<exit>` de cada etapa, `failed=` (lista ou `-`) |
| `/var/lib/smartquotation/key-backup/offsite_key_last_success` | `offsite_key_push.sh`, só quando envia | `remote=`, `object=`, `bytes=`, `hash=`, `key_sha256_16=` |
| `/var/lib/smartquotation/key-backup/offsite_key_fingerprint` | `offsite_key_push.sh` | `sha256_16=` e `object=` da última chave que chegou à custódia off-site |
| `/backups/sq/restore_file_last_success` | `restore_check.sh` com `RESTORE_DUMP_FILE` (drill trimestral) | mesmos campos do `restore_last_success` |

Falha **não** toca nos `*last_success`: a **idade** deles é o sinal. Backup diário saudável
tem `last_success` com menos de ~26 h; drill saudável, `restore_last_success` com menos de 8
dias. Checagem rápida:

```bash
systemctl --failed; systemctl list-timers 'sq-*'
cat /backups/sq/last_success /backups/sq/restore_last_success
find /backups/sq -maxdepth 1 -name last_success -mmin -1560 | grep -q . || echo "BACKUP ATRASADO"
find /backups/sq -maxdepth 1 -name offsite_last_success -mmin -1560 | grep -q . || echo "OFF-SITE ATRASADO"
```

`key_sha256_16` é o fingerprint (sha256 truncado) da chave — serve para conferir a cópia em
custódia com `sha256sum < arquivo_da_chave | cut -c1-16`; não é a chave. `sem amostra` (dump
sem `MaterialPrice`) falha a unit por padrão: a chave não foi provada, e isso não é verde.

### Execução manual (sem systemd)

```bash
# Uso manual, como root, com o MESMO env file das units (não o .env.prod):
set -a && source /etc/smartquotation/backup.env && set +a && ./scripts/backup_db.sh
# (o backup.env é root 0600: o usuário de deploy não o lê, e não deve rodar o backup)
```

> **Atenção:** use `set -a` antes de `source` para que as variáveis do env file (sem `export`)
> sejam exportadas e herdadas pelo processo filho (`backup_db.sh`). Sem isso, com `set -u` no
> script, variáveis obrigatórias ficam "unbound".

Alternativa às units, se o host não tiver systemd (crontab do **root**, mesma cadeia):

```
0 3 * * * bash -c 'set -a && source /etc/smartquotation/backup.env && set +a && /opt/smartquotation/scripts/backup_run.sh' >> /var/log/sq_backup.log 2>&1
```

### Restore em produção (runbook, containers avulsos — nunca executado em produção)

O caminho de dados é o mesmo que o drill semanal exercita em container efêmero; a troca em
produção nunca foi feita. Antes de qualquer passo destrutivo, rode `backup_db.sh` (o estado
atual vira o dump mais novo) e guarde o nome do arquivo.

```bash
# 0. Escolha o dump e confira que ele passa no drill
ls -1 /backups/sq/sq_*.sql.gz | tail -n 3
/opt/smartquotation/scripts/restore_check.sh          # usa o mais recente

# 1. Pare a app (ninguém escreve durante o restore)
docker stop sq-web-proto

# 2. Recrie o banco a partir do dump (pg_dumpall recria o database; "role já existe" é esperado)
docker exec sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d postgres -c "DROP DATABASE smartquotation WITH (FORCE)"'
zcat /backups/sq/sq_<ts>.sql.gz | docker exec -i sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d postgres'

# 3. Chave: o container da app tem que ter a MESMA FIELD_ENCRYPTION_KEY do dump.
#    Compare o fingerprint da cópia com o do dump restaurado (last_proof/last_success).
sha256sum < /var/lib/smartquotation/key-backup/field_encryption_key | cut -c1-16
#    Se o sq-web-proto for recriado, passe a chave por --env-file 0600 (nunca na linha de comando).

# 4. Suba a app e restaure a mídia (volume media_data → /app/backend/media)
docker start sq-web-proto
docker exec -i sq-web-proto tar xzf - -C / < /backups/sq/media_<ts>.tar.gz

# 5. Valide
curl -fsS https://quotation.qtec.me/health/
/opt/smartquotation/scripts/backup_key.sh              # prova de decifra contra o banco novo
```

Em host novo: Docker, repo em `/opt/smartquotation`, `.env.prod` (da custódia manual do
Capitão), containers `sq-prod-db` e `sq-web-proto` recriados (HANDOFF §4), a chave **da
custódia** no env do `sq-web-proto`, e então os passos 2–5. Dois efeitos esperados no off-site
do host novo: o `offsite_key_push.sh` não tem `offsite_key_fingerprint` nem manifesto e envia a
MESMA chave como objeto **novo** (`field_encryption_key.<fpr>.<UTC>.age` — o nome leva o
timestamp, então isso é append, nunca conflito nem sobrescrita); e dumps baixados do off-site
para o restore **não** vão para o `BACKUP_DIR` (o backfill os reenviaria e esbarraria nos
objetos que já existem) — use um diretório à parte.

### Off-site cifrado (ordem 003 — no repo, NÃO instalado)

Sem off-site, perder o host é perder os backups. A ordem 003 leva o **dump e a mídia** para
fora, cifrados, e a **chave vai por outro caminho, para custódia separada** — nunca no mesmo
destino nem no mesmo pacote do dump. O **`/opt/smartquotation/.env.prod`** contém a
`FIELD_ENCRYPTION_KEY`: é material de chave, segue custódia separada — **MANUAL e offline, do
Capitão** (nenhum script o envia; é passo do checklist do ship abaixo) — e **nunca** entra no
pacote do dump da 003 (o `offsite_push.sh` só leva `sq_*.sql.gz` e `media_*.tar.gz`; o teste
varre tudo que o remote do dump recebe atrás da chave e do `.env.prod`). O `/etc/smartquotation/backup.env` não tem segredo e pode ir com a configuração.

**O que roda** (pelo `backup_run.sh` da `sq-backup.service`, depois de dump, mídia e chave —
e **mesmo que alguma etapa anterior tenha falhado**: o off-site do dump tem valor sem a chave;
a unit fica `failed` no fim e o `backup_run_last` diz qual etapa falhou):

1. `offsite_key_push.sh` — quando o fingerprint da chave muda: cifra a `FIELD_ENCRYPTION_KEY`
   com `age` **só** para `OFFSITE_AGE_RECIPIENT_RECOVERY` e envia
   `field_encryption_key.<fingerprint>.<UTC>.age` para `OFFSITE_KEY_REMOTE` (nome único: host
   novo com a mesma chave faz append, não conflito). Chave igual: não reenvia, mas confere
   (`hashsum`) que o objeto registrado continua lá — sumiu ou mudou, falha.
2. `offsite_push.sh` — primeiro o dump e o tar **mais novos**; depois o **backfill**: todo
   dump e tar local ainda não confirmado no `offsite_manifest`, do mais antigo para o mais
   novo (um dia sem envio não deixa buraco), até `OFFSITE_BACKFILL_MAX` por execução (default
   6, além dos mais novos; o resto sai nas próximas — o primeiro dia não estoura o
   `TimeoutStartSec`). Tudo cifrado para **dois** destinatários e enviado como `<arquivo>.age`
   para `OFFSITE_REMOTE`. Um objeto antigo com problema **não bloqueia o de hoje**: as falhas
   se acumulam, o script segue e sai != 0 no fim nomeando cada uma. O `offsite_last_success`
   só renova sem falha e com o dump mais novo abaixo de `OFFSITE_MAX_AGE_HOURS` (default 26):
   com o `backup_db` parado, o off-site roda, mas não fica verde.

Os dois cifram por stdin (a chave nunca passa por argv, env nem log), conferem o cabeçalho
`age` (uma stanza por destinatário, do tipo esperado: `X25519` para `age1…`, `piv-p256` para
`age1yubikey1…`; duas no dump, uma na chave), enviam com `rclone copyto --immutable` e
conferem o hash remoto (`rclone hashsum`, `OFFSITE_HASH`, default `sha1`) contra o local antes
de gravar qualquer `*_last_success`. Objeto remoto que já existe com o hash que este host
registrou (`offsite_manifest`) é pulado; com outro hash, é **falha** — nunca sobrescreve.
Qualquer falha deixa a unit `failed`.

**Dois destinatários, só chaves públicas no host.** `OFFSITE_AGE_RECIPIENT_INSTANCE` é a chave
pública de um par gerado no ship para esta instância (a privada vai para guarda offline, fora
do host); `OFFSITE_AGE_RECIPIENT_RECOVERY` é a chave de recuperação da Quantum, raiz offline no
YubiKey (DP-41). Qualquer uma das duas privadas abre o dump; a chave de campo só abre com a de
recuperação. Cada destinatário pode ser **X25519** (`age1…`, de `age-keygen -y`) ou **YubiKey**
(`age1yubikey1…`, de `age-plugin-yubikey --list`): a forma do destinatário de recuperação é
**decisão de instalação** (DP-41). Com YubiKey, o host precisa do `age-plugin-yubikey` no PATH
da unit (`/usr/local/bin` ou `/usr/bin`; a unit fixa `Environment=PATH` só com diretórios do
sistema) **só para cifrar** — a identidade fica no token e nunca passa pelo host; sem o plugin,
os scripts falham na hora, antes de tocar em `age` ou `rclone`. Os scripts recusam destinatário
ausente, repetido (um só, na prática), com cara de chave privada (`AGE-SECRET-KEY-…`) ou de
identidade de plugin (`AGE-PLUGIN-YUBIKEY-…`) — sem exibir o valor — ou com o valor fictício do
exemplo.

**Dois remotes, duas credenciais.** `OFFSITE_REMOTE` (dump e mídia) e `OFFSITE_KEY_REMOTE` (a
chave) são `secao:bucket/prefixo` de seções **diferentes** do `rclone.conf`
(`RCLONE_CONFIG=/etc/smartquotation/rclone.conf`, root 0600 — o script recusa se grupo ou
outros lerem). O que o código confere, lendo o `rclone.conf` sem imprimir valor nenhum: mesmo
remote, um dentro do outro ou mesma seção; `type` fora da **allowlist de armazenamento direto**
(`s3`, `b2`, `gcs`, `azureblob`, `swift`, `oos`, `sftp`; `local` para teste) — allowlist, e não
lista de wrappers, porque todo backend que aponta para outro remote (`alias`, `crypt`, `union`,
`combine`, `chunker`, `compress`, `hasher`, `cache` e os que vierem) tornaria a separação
inverificável; o **mesmo bucket** em **qualquer** tipo (B2 nativo e o S3 da Backblaze chegam ao
mesmo bucket por dois caminhos); **qualquer valor de credencial em comum** entre as duas seções,
sem olhar o nome do campo (a mesma chave vira `account=` no `b2` e `access_key_id=` no `s3`);
e variável `RCLONE_CONFIG_<SEÇÃO>_*` no ambiente para qualquer das duas (ela sobrepõe o
`rclone.conf`). Tudo isso é recusado, assim como a sintaxe de backend na hora
(`:b2,account=…:`), que poria credencial em argv (a mensagem não repete o valor). O código não
escolhe provedor. **O que o código não consegue ver, e é do Capitão no ship:** que as duas
credenciais são de **contas diferentes de verdade** (duas application keys da mesma conta B2
passam na checagem), e que cada uma tem permissão **só de escrita** (sem delete) no seu bucket.

**Destino estrangeiro:** permitido já pela DP-29 aprovada (decisão (a) do Diretor); o parecer
J-29 pode mudar o destino — se apontar risco, troca-se o remote e a série é reenviada.

**Sem poda remota.** Enquanto a DP-27 (retenção NR-13) estiver aberta, nada é apagado no remoto
por rotina: os scripts não chamam `delete`, `purge`, `sync` nem `move` (o teste falha se o
rclone receber um deles). Versões antigas da chave ficam na custódia: são elas que abrem os
dumps antigos. A poda local do `BACKUP_RETENTION_DAYS` continua valendo só para o disco do host.

**No ship (Capitão — NÃO executado):**

```bash
umask 077
# 1. Dois buckets, em contas/credenciais separadas: um para a série (dump + mídia), outro para
#    a chave. Credencial SÓ DE ESCRITA onde o provedor permitir (B2: application key restrita
#    ao bucket com writeFiles + listFiles, SEM deleteFiles; S3: PutObject + ListBucket, sem
#    DeleteObject). Leitura (readFiles/GetObject) só se usar OFFSITE_HASH_DOWNLOAD=1. Com
#    versionamento/object lock, melhor ainda. A credencial de LEITURA do drill fica offline.
# 2. Par age da instância, gerado FORA do host de produção (estação do Capitão):
age-keygen -o sq-instancia.agekey          # a privada: guarda offline (cofre/YubiKey/papel)
age-keygen -y sq-instancia.agekey          # a pública: vai para o backup.env
#    e o destinatário de recuperação da Quantum (DP-41), fornecido pela Quantum: age1… ou,
#    se a raiz estiver no YubiKey, age1yubikey1… (age-plugin-yubikey --list).
# 3. No host, como root:
install -m 0600 -o root -g root /dev/null /etc/smartquotation/rclone.conf
rclone config --config /etc/smartquotation/rclone.conf   # seções sq-offsite e sq-offsite-key
apt-get install -y age rclone
#    se algum destinatário for YubiKey (age1yubikey1…): age-plugin-yubikey em /usr/local/bin
#    (ou pacote em /usr/bin). Só cifra; token, pcscd e identidade NÃO vão para o host.
#    edite /etc/smartquotation/backup.env: OFFSITE_REMOTE, OFFSITE_KEY_REMOTE e as duas
#    chaves PÚBLICAS reais (os valores do exemplo são fictícios e recusados)
# 4. As identidades abrem o que o host cifra? Na estação (nunca no host), confira que cada
#    identidade corresponde ao destinatário do backup.env:
age-keygen -y sq-instancia.agekey          # == OFFSITE_AGE_RECIPIENT_INSTANCE
#    recuperação X25519: age-keygen -y <identidade> == OFFSITE_AGE_RECIPIENT_RECOVERY
#    recuperação YubiKey: age-plugin-yubikey --list (token conectado) == OFFSITE_AGE_RECIPIENT_RECOVERY
# 5. Primeira execução assistida e conferência:
systemctl start sq-backup.service && journalctl -u sq-backup.service -n 80 --no-pager
cat /backups/sq/backup_run_last /backups/sq/offsite_last_success \
    /var/lib/smartquotation/key-backup/offsite_key_last_success
# 6. Prova de decifra ANTES do primeiro drill trimestral: baixe o primeiro .age do dump e
#    decifre com CADA identidade (instância e recuperação); o da chave, com a de recuperação.
#    Tudo numa estação, sem gravar o texto claro em disco:
rclone cat sq-offsite:<bucket>/<prefixo>/sq_<ts>.sql.gz.age > sq.age
age -d -i sq-instancia.agekey sq.age | gzip -t && echo "instância abre"
age -d -i <identidade-de-recuperação> sq.age | gzip -t && echo "recuperação abre"
rclone cat sq-offsite-key:<bucket>/<prefixo>/field_encryption_key.<fpr>.<UTC>.age \
  | age -d -i <identidade-de-recuperação> | sha256sum | cut -c1-16   # == key_sha256_16
# 7. .env.prod: custódia MANUAL e offline do Capitão (nenhum script o envia). Copie
#    /opt/smartquotation/.env.prod para a mídia offline da custódia (a mesma guarda das
#    identidades, nunca o bucket), e repita a cada troca de segredo da aplicação.
```

O host nunca guarda chave privada age: se uma já esteve lá, gere outro par e reenvie a série.

### Drill trimestral a partir do off-site (manual)

O drill semanal prova o dump **local**; o trimestral prova que a cópia **off-site** restaura
com as chaves offline. Roda numa estação com docker, **fora** do host de produção:

```bash
umask 077                                  # tudo que o drill grava já nasce 0600
# 1. Baixar (credencial de leitura) o dump, a mídia e a chave do trimestre
rclone copyto sq-offsite:<bucket>/<prefixo>/sq_<ts>.sql.gz.age ./sq_<ts>.sql.gz.age
rclone copyto sq-offsite:<bucket>/<prefixo>/media_<ts>.tar.gz.age ./media_<ts>.tar.gz.age
rclone copyto sq-offsite-key:<bucket>/<prefixo>/field_encryption_key.<fpr>.<UTC>.age ./fek.age
# 2. Decifrar com a chave privada offline (alterne a cada trimestre: a da instância e a de
#    recuperação; a chave de campo só abre com a de recuperação). Com YubiKey: token
#    conectado, age-plugin-yubikey na estação e -i com o arquivo de identidade
#    (age-plugin-yubikey --identity)
age -d -i <identidade> -o sq_<ts>.sql.gz sq_<ts>.sql.gz.age
age -d -i <identidade> -o media_<ts>.tar.gz media_<ts>.tar.gz.age
age -d -i <identidade-de-recuperação> -o fek fek.age
# 3. Restore verificado do arquivo baixado (Postgres efêmero, sem rede — a major é derivada
#    do cabeçalho do dump desde a ordem 009, ver docs/ship/ORDEM_009_POSTGRES.md)
BACKUP_DIR="$PWD/drill" RESTORE_DUMP_FILE="$PWD/sq_<ts>.sql.gz" \
  RESTORE_MEDIA_FILE="$PWD/media_<ts>.tar.gz" /opt/smartquotation/scripts/restore_check.sh
# 4. A chave é a do dump? fingerprint igual ao key_sha256_16 do last_proof daquele dia
sha256sum < fek | cut -c1-16
# 5. Apague o que foi decifrado (dump, mídia e fek) e registre data, objetos e resultado
```

`RESTORE_DUMP_FILE` desliga a checagem de idade e grava `restore_file_last_success` no
`BACKUP_DIR` do drill, sem tocar no sinal do drill semanal. Ele e o `RESTORE_MEDIA_FILE` são
recusados dentro das units de backup (marcador explícito `Environment=SQ_BACKUP_UNIT=1` na
`sq-backup.service` e na `sq-restore-check.service`) e para arquivo dentro do `BACKUP_DIR`: são
do drill manual e não vão no `backup.env`. A prova de decifra com a chave
(Fernet) só roda com o container da app: a conferência do drill é o fingerprint.

### Política de retenção de backup (desenho-alvo)

> Hoje: `BACKUP_RETENTION_DAYS` local (default 14) para dump e mídia; no off-site, **nada é
> apagado** (sem poda remota enquanto a DP-27 estiver aberta). O resto é alvo.
> A linha de 15 anos (NR-13) espera a DP-27 (jurídico), conforme o INTENT.

| Frequência | Retenção | Storage estimado |
|---|---|---|
| A cada 6h (diário) | 7 dias | ~4 × 7 = 28 dumps |
| Diário (snapshot) | 30 dias | 30 dumps |
| Semanal | 90 dias | 13 dumps |
| Mensal | 365 dias | 12 dumps |
| Anual | 15 anos | 15 dumps (arquivamento frio) |

### RTO / RPO estimados (metas da v1.0, nunca medidas)

| Cenário | RPO (dados perdidos) | RTO (tempo até restauração) |
|---|---|---|
| Corrupção de banco | ≤ 6 horas | ≤ 2 horas |
| VPS inacessível | ≤ 6 horas | ≤ 4 horas (novo VPS + restore) |
| Exclusão acidental de tenant | ≤ 6 horas | ≤ 1 hora |
| Desastre total (datacenter) | ≤ 6 horas | ≤ 8 horas (off-site restore) |

---

## 7. Observabilidade (desenho-alvo, exceto 7.1)

> Existe hoje: `GET /health/` (`apps.health`) e o `HEALTHCHECK` da imagem. Sentry, Uptime Kuma,
> Flower e alertas não estão configurados.

### 7.1 Health Check endpoint

```
GET /health/
Response 200: { "status": "ok", "db": "ok", "redis": "ok", "version": "1.2.3" }
Response 503: { "status": "degraded", "db": "error", "redis": "ok" }
```

### 7.2 Stack de observabilidade

| Ferramenta | Propósito | Fase |
|---|---|---|
| **Sentry** | Erros de runtime com stack trace e contexto de usuário/tenant | MVP |
| **Uptime Kuma** | Uptime, latência, alertas por Telegram/email | MVP |
| **Django logging** | Structured JSON logs para stdout → journald → logrotate | MVP |
| **Celery Flower** | Monitoramento de filas e workers Celery (porta interna, não exposta) | MVP |
| **Prometheus + Grafana** | Métricas de infra (CPU, memória, disco, conexões DB) | H2 |
| **Loki** | Aggregação e busca de logs | H2 |
| **OpenTelemetry** | Tracing distribuído (útil quando virar microserviços em H3) | H3 |

### 7.3 Alertas críticos (Uptime Kuma → Telegram)

| Condição | Severidade | Ação |
|---|---|---|
| Health check falha por > 2min | 🔴 Crítico | Notificação imediata |
| Disk > 80% | 🟡 Alerta | Notificação em 1h |
| Disk > 95% | 🔴 Crítico | Notificação imediata |
| Backup não executado em 12h | 🔴 Crítico | Notificação imediata |
| Celery queue > 100 tarefas pendentes | 🟡 Alerta | Notificação em 30min |
| Sentry: novo error type | 🟡 Alerta | Notificação em 5min |
| TLS cert expira em < 14 dias | 🟡 Alerta | Notificação diária |

---

## 8. Sizing de Infraestrutura (MVP) (desenho-alvo)

### VPS Produção

| Recurso | Mínimo MVP | Recomendado |
|---|---|---|
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Disco | 50 GB SSD | 100 GB SSD |
| Banda | 1 Gbps compartilhado | — |
| Região | Brasil (São Paulo) | Brasil (São Paulo) |

**Provedores sugeridos (Brasil, custo-benefício):**
- Magalu Cloud (KingHost) — São Paulo
- Locaweb Cloud
- Oracle Cloud Free Tier (4 OCPUs ARM + 24GB RAM — excelente para MVP gratuito)
- AWS São Paulo (t3.medium como baseline)

### VPS Staging
- 2 vCPU, 2 GB RAM, 20 GB SSD — pode ser Oracle Free Tier

### Storage off-site (backup)
- Backblaze B2: ~$0,006/GB/mês — muito mais barato que AWS S3
- Wasabi: $0,0059/GB/mês, sem egress fee

---

## 9. Provisionamento (bootstrap do servidor) (desenho-alvo, nunca executado)

```bash
#!/bin/bash
# setup-server.sh — executa uma vez no VPS limpo Ubuntu 24.04

set -euo pipefail

# 1. Updates e dependências
apt-get update && apt-get upgrade -y
apt-get install -y curl git docker.io docker-compose-v2 fail2ban ufw age rclone

# 2. Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw enable

# 3. fail2ban (brute force SSH)
systemctl enable fail2ban
systemctl start fail2ban

# 4. Usuário de deploy (sem senha, só chave SSH)
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh
# Copiar authorized_keys do GitHub Actions

# 5. Diretórios
mkdir -p /opt/smartquotation
mkdir -p /data/uploads /data/static /data/backups /data/logs
chown -R deploy:deploy /opt/smartquotation /data

# 6. Cron de backup
echo "0 */6 * * * deploy /opt/smartquotation/scripts/backup.sh >> /var/log/backup.log 2>&1" \
  >> /etc/crontab

# 7. Limite de arquivos abertos (Postgres + Gunicorn)
echo "deploy soft nofile 65536" >> /etc/security/limits.conf
echo "deploy hard nofile 65536" >> /etc/security/limits.conf

echo "✅ Servidor provisionado. Clone o repositório em /opt/smartquotation e configure .env.prod"
```

---

## 10. SQ na F1 do Core

Duas coisas separadas, que não se misturam na F1 (DP-02):

| | Produção atual | Instância do Core para o SQ |
|---|---|---|
| Onde | VPS + `cloudflared`, `quotation.qtec.me` (§0) | VM `borda-1` do R640 (DP-02, FASES §10) |
| Guarda | Os tenants do SQ (ENGEMATEX): banco multi-schema, `media_data` (propostas), `FIELD_ENCRYPTION_KEY` | Estado do Core para o SQ: ledger de envio, trilha/`trace_id`, fatos e decisões do Diretor da instância. Dado de cliente só o que a capability entrega, e ele não sai da instância (INTENT, Limites) |
| Muda na F1 | Só a F1-04; migrar de host é decisão futura do Capitão | Nasce na F1 |

O que a F1 exige da infra, tudo **previsto**:

| Ordem | Exige | Prova (FASES §4) | Estado |
|---|---|---|---|
| F1-04 | Porta `8000` em loopback no `docker-compose.prod.yml` (`127.0.0.1:8000:8000`) | Varredura externa: 0 portas do SQ fora do túnel | **previsto (F1-04)**; hoje `docker-compose.prod.yml:22` publica em `0.0.0.0` |
| F1-14 | Túnel por instância para o socket, Access por instância | Varredura externa: 0 portas; sem sessão → 302/403 em 100% | **previsto (F1-14)** |
| F1-15 | Backup PITR (base + WAL) com drill mensal que afirma número; `age` com dois destinatários (a chave de um host não basta) | Drill verde com RPO medido ≤ 5 min e RTO registrado; artefato adulterado reprova | **previsto (F1-15)**; hoje há dump diário validado + drill semanal em container efêmero, sem cifra, sem PITR e ainda não instalados (§6) |
| F1-16 | Operação sem córtex | 72 h com córtex desligado: 0 execução essencial falhada | **previsto (F1-16)** |

O RTO medido no drill da F1-15 é o número que alimenta os gatilhos C-6 e C-8 (FASES §10).
Nenhuma compra ou mudança de host sai daqui sem gatilho medido e decisão do Capitão.

---

## 11. Prova headless

Esta forge não tem Docker nem Postgres para o SQ; não se sobe produção nem banco aqui. O que se
prova sem lab:

**1. Motor, local (stdlib pura, sem Django, sem banco).** Os mesmos quatro gates do job
`pricing-engine` da CI, a partir da raiz do repo:

```bash
python3 -m tests.validate_feixe_completo       # feixe vs referencial (−2,9%; falha >10%)
python3 -m tests.validate_permutador_completo  # BEU+BEM (0,0%; ±10% + geometria)
python3 -m tests.test_cost_chain_knobs         # contrato dos knobs da TenantCostChain
python3 -m tests.test_solda_fisica             # régua de solda por primeiros princípios
```

`scripts/prova_motor.sh` (a criar pelo Conformador) roda os quatro e falha no primeiro vermelho.

**2. Suíte Django, por recibo da CI.** `manage.py test apps` precisa de Postgres (TenantTestCase),
então a prova é o run verde do job `django-test` **no SHA exato do HEAD**, lido via `gh`:

```bash
gh run list --workflow ci.yml --commit "$(git rev-parse HEAD)" --json databaseId,conclusion
gh run view <id> --json jobs --jq '.jobs[] | [.name, .conclusion] | @tsv'
```

`scripts/ci/suite_receipt.sh` (a criar pelo Conformador) faz isso e falha se não houver run no
HEAD ou se `Testes Django (multi-tenant)` não for `success`. Run de outro SHA não vale como recibo.
Como `conform/*` não dispara CI em push (§5), o recibo sai do PR para `main`.

**Ordem 009:** com o patch `docs/patches/009-ci-postgres-matrix.patch` aplicado, o job vira
matriz (`Testes Django (multi-tenant) — Postgres 15` e `— Postgres 16`, §5); o
`suite_receipt.sh` aceita tanto o nome antigo (runs anteriores ao patch) quanto a matriz — e,
na matriz, exige as duas majors (15 e 16) presentes e `success`: matriz incompleta reprova.

