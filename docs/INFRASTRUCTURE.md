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
covers:
  - docker-compose.yml
  - docker-compose.prod.yml
  - backend/Dockerfile
  - backend/entrypoint.sh
  - scripts/backup_db.sh
  - scripts/backup_media.sh
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
| Backup | Ver §6: o script não roda contra a produção atual; sem cifra, sem off-site, sem drill | `scripts/backup_db.sh`, HANDOFF §4 |
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
| `ops-tests` | Contrato de `backup_db.sh`/`backup_media.sh`, volume de media, storage de proposals, lockfiles. `test_backup_script` e `test_media_backup` **leem este doc** (cron com `set -a`, `media_data`) |
| `pip-audit` | CVEs em `base.lock` e `ci.lock`, sem re-resolver a árvore |
| `django-check` | `manage.py check` + `makemigrations --check` |
| `django-test` | `manage.py test apps` contra `postgres:16-alpine`, com WeasyPrint obrigatório |
| `docker-build` | `docker build -f backend/Dockerfile` (só em `main`/PR para `main`, depois do `django-test`) |

O desenho de deploy da v1.0 (registry, Trivy, staging, aprovação manual, cobertura ≥ 80%,
regressão PVElite) não existe; PVElite como gate está fora de escopo (INTENT).

---

## 6. Backup e Recuperação

### O que o backup faz de fato

| Peça | Faz | Não faz |
|---|---|---|
| `scripts/backup_db.sh` | `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB \| gzip` → `$BACKUP_DIR/sq_<ts>.sql.gz`, escrita atômica (`.tmp` + `mv`), `set -euo pipefail` | Cifra, off-site, retenção/limpeza, validar conteúdo, avisar falha, globais (`pg_dumpall`) |
| `scripts/backup_media.sh` | `tar czf` de `/app/backend/media` (volume `media_data`) via `exec -T web` → `media_<ts>.tar.gz` | Idem |
| Produção atual | **Nenhum dos dois roda contra ela**: ambos exigem o compose, e a produção é de containers avulsos (HANDOFF §4). O backup de produção que existe é manual | — |

**Restore testado:** o único registrado é o dump pré-Prancha de 28/07/2026
(`~/backups/sq/pre_prancha_20260728_143633.sql.gz`, "verificado" no HANDOFF §4), sem duração
nem procedimento anotados. **Não há drill** de restore periódico, cronometrado e registrado, e o
runbook de restore abaixo nunca foi executado (ele restaura um `.sql.age` que nenhum script do
repo produz). Lição já paga: `pg_dumpall` na porta errada gera arquivo de 20 bytes com exit 0;
backup se valida pelo **conteúdo** (tamanho, `zcat | head`, restore), nunca pelo exit code.

### Uso de scripts/backup_db.sh (quando a produção subir pelo compose)

```bash
# Uso manual
POSTGRES_USER=sq POSTGRES_DB=smartquotation BACKUP_DIR=/backups/sq ./scripts/backup_db.sh
# ou (usa POSTGRES_BACKUP_DIR do .env.prod):
set -a && source .env.prod && set +a && ./scripts/backup_db.sh
```

> **Atenção:** use `set -a` antes de `source` para que as variáveis do `.env.prod` (sem `export`)
> sejam exportadas e herdadas pelo processo filho (`backup_db.sh`). Sem isso, com `set -u` no
> script, `POSTGRES_USER`/`POSTGRES_DB` ficam "unbound" e o script aborta.

**Agendamento via cron do host** (crontab do usuário de deploy):

```
# Backup diário às 3h
0 3 * * * bash -c 'set -a && source /opt/smartquotation/.env.prod && set +a && /opt/smartquotation/scripts/backup_db.sh' >> /var/log/sq_backup.log 2>&1
```

Para editar: `crontab -e`

> A variável `POSTGRES_BACKUP_DIR` (padrão `/backups/sq`) é definida em `.env.prod.example`.
> O script cria o diretório automaticamente se não existir.

### Estratégia de backup (desenho-alvo, `scripts/backup.sh` não existe)

```bash
#!/bin/bash
# /opt/smartquotation/scripts/backup.sh — executa via cron a cada 6h

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

# 1. Dump completo do PostgreSQL
docker compose -f docker-compose.prod.yml exec -T db pg_dumpall -U ${POSTGRES_USER} \
  | age --encrypt --recipient "${BACKUP_PUBLIC_KEY}" \
  > "${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.age"

# 2. Snapshot do volume de mídia (media_data: PDFs/DOCX de propostas em /app/backend/media)
BACKUP_DIR="${BACKUP_DIR}" COMPOSE_FILE=docker-compose.prod.yml \
  ./scripts/backup_media.sh
# Ou equivalente inline:
# docker compose -f docker-compose.prod.yml exec -T web \
#   tar czf - /app/backend/media > "${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"

# 3. Atualiza symlink de backup mais recente
ln -sfn "${BACKUP_DIR}" /backups/latest

# 4. Sync off-site
rclone sync /backups/ "${RCLONE_REMOTE}/" \
  --min-age 1m \
  --log-file /var/log/backup-rclone.log

# 5. Limpeza local (mantém 7 dias)
find /backups -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +

# 6. Notificação
curl -s -X POST "${HEALTHCHECK_URL}/backup-complete"
```

### Política de retenção de backup (desenho-alvo)

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

### Restore procedure (runbook, nunca executado)

```bash
# Restore completo de produção em novo VPS
# 1. Provisionar VPS + instalar Docker
# 2. Clonar repositório + configurar .env.prod
# 3. Baixar backup mais recente do S3-compatible
rclone copy "${RCLONE_REMOTE}/latest/" /backups/latest/

# 4. Iniciar apenas o PostgreSQL
docker compose up -d db

# 5. Descriptografar e restaurar banco
age --decrypt --identity /path/to/private.key \
  /backups/latest/postgres_*.sql.age | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U ${POSTGRES_USER}

# 6. Restaurar mídia (volume media_data → /app/backend/media dentro do container)
docker compose -f docker-compose.prod.yml up -d web
docker compose -f docker-compose.prod.yml exec -T web \
  tar xzf - -C / < /backups/latest/media_*.tar.gz

# 7. Subir todos os serviços
docker compose -f docker-compose.prod.yml up -d

# 8. Validar
curl -f https://novo-vps.smartquotation.com.br/health/
```

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
| F1-15 | Backup PITR (base + WAL) com drill mensal que afirma número; `age` com dois destinatários (a chave de um host não basta) | Drill verde com RPO medido ≤ 5 min e RTO registrado; artefato adulterado reprova | **previsto (F1-15)**; hoje há só `pg_dump` sem cifra e sem drill (§6) |
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

