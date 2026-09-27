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
  - ops/systemd/sq-backup.service
  - ops/systemd/sq-backup.timer
  - ops/systemd/sq-restore-check.service
  - ops/systemd/sq-restore-check.timer
  - ops/systemd/backup.env.example
  - .env.prod.example
reviewed: 2026-09-27
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
| Backup | Ver §6: scripts e units prontos para os containers avulsos (dump + mídia + chave com prova de decifra, drill semanal), **não instalados** (gate do Capitão); sem cifra, sem off-site | `scripts/backup_*.sh`, `ops/systemd/`, HANDOFF §4 |
| CI | `.github/workflows/ci.yml`, seis jobs de prova, nenhum de deploy (§5) | ci.yml |
| Monitoramento | Só o `/health/` e o `HEALTHCHECK` da imagem; nada externo avisa se cair (§7 é alvo) | `backend/Dockerfile:53-54` |

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
| `ops-tests` | Contrato de `backup_db.sh`/`backup_media.sh`, volume de media, storage de proposals, lockfiles. `test_backup_script` também roda `test_backup_db_hardening`, `test_atomic_backup`, `test_backup_key`, `test_restore_check` e `test_backup_units` (docker falso). `test_backup_script` e `test_media_backup` **leem este doc** (cron com `set -a`, `media_data`) |
| `pip-audit` | CVEs em `base.lock` e `ci.lock`, sem re-resolver a árvore |
| `django-check` | `manage.py check` + `makemigrations --check` |
| `django-test` | `manage.py test apps` contra `postgres:16-alpine`, com WeasyPrint obrigatório |
| `docker-build` | `docker build -f backend/Dockerfile` (só em `main`/PR para `main`, depois do `django-test`) |

O desenho de deploy da v1.0 (registry, Trivy, staging, aprovação manual, cobertura ≥ 80%,
regressão PVElite) não existe; PVElite como gate está fora de escopo (INTENT).

---

## 6. Backup e Recuperação

> Emenda da ordem 002 (27/09/2026). Tudo abaixo está no repo e **provado com docker falso**
> (`tests/test_backup_*`, `tests/test_restore_check.py`, `tests/test_media_backup.py`); nada
> disso foi instalado nem executado contra a produção. Instalar as units no host de produção
> é **gate ship do Capitão**.

### O que roda, onde

| Peça | Faz | Não faz |
|---|---|---|
| `scripts/backup_db.sh` | `pg_dumpall` no container avulso `sq-prod-db` (porta 5436, senha do env do próprio container), ou `pg_dump` via compose onde houver compose. Detecta o modo por `.State.Running`; container parado **falha** (não cai para compose); docker inacessível falha na hora. `umask 077`, escrita atômica (`.tmp` + `mv`). **Valida pelo conteúdo**: gzip íntegro, tamanho e linhas mínimos, schema `engematex` presente e o **rodapé** `-- PostgreSQL database cluster dump complete` (ou `... database dump complete` no compose) — dump truncado é rejeitado. Usuário/host/porta vão ao `sh` do container como argv posicional e passam por lista branca. Grava `last_success`; poda `sq_*.sql.gz` > `BACKUP_RETENTION_DAYS` (14) só depois de um backup novo validado | Cifra, off-site, PITR |
| `scripts/backup_media.sh` | `tar czf - -C / app/backend/media` no `sq-web-proto` (volume `media_data` montado em `/app/backend/media`), mesma detecção/fail-fast. Valida com `tar tzf`: exige `app/backend/media/` e ≥1 entrada sob ele (ou `MEDIA_ALLOW_EMPTY=1`). Grava `media_last_success`; retenção igual | Idem |
| `scripts/backup_key.sh` | Copia a `FIELD_ENCRYPTION_KEY` do env do `sq-web-proto` para `${KEY_BACKUP_DIR}/field_encryption_key` (0600), com fingerprint `sha256` truncado ao lado; preserva a anterior se a chave mudou. **Prova de decifra**: tira um `preco_brl_kg` de `engematex.materials_materialprice` do dump mais recente e roda Fernet **dentro** do container, com chave e token por **stdin**. A prova imprime só `ok`, `falha` ou `sem amostra` (exit 0 / 2 / 3); saída inesperada do container é descartada | Custódia fora do host (ordem 003) |
| `scripts/restore_check.sh` | Drill: sobe `postgres:15` efêmero (`--network none`, `--rm`, nome único), aplica o dump mais recente, confere schema `engematex`, tabelas `quotations_quotation`, `quotations_quotationitem`, `materials_material`, `materials_materialprice` e cotações ≥ `RESTORE_MIN_QUOTATIONS`; valida o tar de mídia mais recente. Container sempre removido (trap). Saída só com contagens e nomes de tabela. Grava `restore_last_success` com a duração | Restore em produção; medir RPO |
| `ops/systemd/sq-backup.{service,timer}` | Todo dia 03:00 (`Persistent=true`, `RandomizedDelaySec=5min`): `backup_db.sh` → `backup_media.sh` → `backup_key.sh`, `Type=oneshot`, para no primeiro que falhar | — |
| `ops/systemd/sq-restore-check.{service,timer}` | Toda segunda 05:00: `restore_check.sh` | — |

As units rodam como `root` (o usuário de deploy não está no grupo docker, e dar o grupo a ele
seria root permanente só para o backup), com `ProtectSystem=strict` + `ReadWritePaths` só nos
diretórios de backup, `PrivateTmp`, `NoNewPrivileges`, `UMask=0077`, e
`EnvironmentFile=/etc/smartquotation/backup.env` — um env file **dedicado** (root, 0600) só com
variáveis `BACKUP_*`, `KEY_*`, `RESTORE_*`, `MEDIA_*`, `DB_CONTAINER*` e afins (modelo:
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
`FIELD_ENCRYPTION_KEY` (e as demais senhas da aplicação). Segue a **mesma custódia separada** da
chave e **nunca** vai no pacote do dump da ordem 003 — nem inteiro, nem como "config para
subir o host novo".

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
install -d -m 0700 /backups/sq /var/lib/smartquotation/key-backup /etc/smartquotation
install -m 0600 -o root -g root /opt/smartquotation/ops/systemd/backup.env.example \
                /etc/smartquotation/backup.env      # revise os valores; nenhum segredo vai aqui
install -m 0644 /opt/smartquotation/ops/systemd/sq-backup.service \
                /opt/smartquotation/ops/systemd/sq-backup.timer \
                /opt/smartquotation/ops/systemd/sq-restore-check.service \
                /opt/smartquotation/ops/systemd/sq-restore-check.timer /etc/systemd/system/
docker pull postgres:15                     # o drill roda sem rede: a imagem tem que estar local
systemctl daemon-reload
systemctl start sq-backup.service           # 1ª execução assistida
journalctl -u sq-backup.service -n 50 --no-pager
systemctl start sq-restore-check.service    # 1º drill assistido
systemctl enable --now sq-backup.timer sq-restore-check.timer
systemctl list-timers 'sq-*'
```

Se mudar `BACKUP_DIR` ou `KEY_BACKUP_DIR` no `backup.env`, mude o `ReadWritePaths` das units
junto (o teste `test_backup_units` confere o par no `backup.env.example` e que nenhuma unit
referencia o `.env.prod`).

### Como ler o resultado

| Arquivo | Escrito por | Conteúdo |
|---|---|---|
| `/backups/sq/last_success` | `backup_db.sh`, só no sucesso | `timestamp=`, `file=`, `bytes=` |
| `/backups/sq/media_last_success` | `backup_media.sh`, só no sucesso | `timestamp=`, `file=`, `bytes=`, `entries=` |
| `/var/lib/smartquotation/key-backup/last_success` | `backup_key.sh`, só com prova `ok` | `timestamp=`, `result=ok`, `dump=`, `key_sha256_16=` |
| `/var/lib/smartquotation/key-backup/last_proof` | `backup_key.sh`, toda prova | `result=ok\|falha\|sem amostra`, `dump=`, `key_sha256_16=` |
| `/backups/sq/restore_last_success` | `restore_check.sh`, só no sucesso | `dump=`, `schema=`, `quotations=`, `tables=`, `psql_errors=`, `media_entries=`, `duration_s=` |

Falha **não** toca nos `*last_success`: a **idade** deles é o sinal. Backup diário saudável
tem `last_success` com menos de ~26 h; drill saudável, `restore_last_success` com menos de 8
dias. Checagem rápida:

```bash
systemctl --failed; systemctl list-timers 'sq-*'
cat /backups/sq/last_success /backups/sq/restore_last_success
find /backups/sq -maxdepth 1 -name last_success -mmin -1560 | grep -q . || echo "BACKUP ATRASADO"
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
0 3 * * * bash -c 'set -a && source /etc/smartquotation/backup.env && set +a && /opt/smartquotation/scripts/backup_db.sh && /opt/smartquotation/scripts/backup_media.sh && /opt/smartquotation/scripts/backup_key.sh' >> /var/log/sq_backup.log 2>&1
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

Em host novo: Docker, repo em `/opt/smartquotation`, `.env.prod`, containers `sq-prod-db` e
`sq-web-proto` recriados (HANDOFF §4), a chave **da custódia** no env do `sq-web-proto`, e então
os passos 2–5.

### Off-site (ordem 003, não existe)

Hoje tudo fica no disco do próprio host: perder o host é perder os backups. A ordem 003 leva o
**dump e a mídia** para fora (cifrados); a **chave vai por outro caminho, para custódia
separada** — nunca no mesmo destino nem no mesmo pacote do dump. O mesmo vale para o
**`/opt/smartquotation/.env.prod`**, que contém a `FIELD_ENCRYPTION_KEY`: é material de chave,
vai para a custódia separada junto com ela e **nunca** entra no pacote do dump da 003. O
`/etc/smartquotation/backup.env` não tem segredo e pode ir com a configuração.

### Política de retenção de backup (desenho-alvo)

> Hoje: `BACKUP_RETENTION_DAYS` local (default 14) para dump e mídia. O resto é alvo.
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

