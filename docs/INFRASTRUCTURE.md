# INFRASTRUCTURE.md — SmartQuotation

> **Status:** Aprovado | **Versão:** 1.0 | **Referência:** ARCHITECTURE.md, SECURITY.md

---

## 1. Ambientes

| Ambiente | Propósito | URL | Hospedagem |
|---|---|---|---|
| `dev` | Desenvolvimento local | `localhost:8000` | Docker Compose local |
| `staging` | Validação antes de produção | `staging.smartquotation.com.br` | VPS BR (menor) |
| `production` | Clientes reais | `{tenant}.smartquotation.com.br` | VPS BR (principal) |

**Regra:** nenhum deploy vai direto para `production` — sempre passa por `staging` primeiro.
**Dados:** staging usa dataset anonimizado, nunca dump de produção.

---

## 2. Docker Compose — Produção

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

## 3. Caddyfile

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

## 4. Variáveis de Ambiente (`.env.prod`)

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

## 5. CI/CD — GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Test, Scan & Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: sq_test
          POSTGRES_USER: sq_test
          POSTGRES_PASSWORD: test
        options: --health-cmd pg_isready --health-interval 10s
      redis:
        image: redis:7-alpine

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements/test.txt

      - name: Lint (ruff + black)
        run: |
          ruff check .
          black --check .

      - name: SAST (bandit)
        run: bandit -r smartquotation/ -ll

      - name: Dependency audit (pip-audit)
        run: pip-audit --strict --vulnerability-service pypi

      - name: Secret scan (detect-secrets)
        run: detect-secrets scan --baseline .secrets.baseline

      - name: Run tests (unit + integration)
        env:
          DATABASE_URL: postgresql://sq_test:test@localhost:5432/sq_test
          REDIS_URL: redis://localhost:6379/0
          DJANGO_SETTINGS_MODULE: smartquotation.settings.test
        run: |
          pytest tests/ -v --cov=smartquotation --cov-report=xml \
            --cov-fail-under=80

      # GATE CRÍTICO: regressão contra PVElite
      - name: PVElite Regression Tests
        env:
          DATABASE_URL: postgresql://sq_test:test@localhost:5432/sq_test
        run: |
          pytest tests/engineering/regression/ -v \
            --tb=short \
            -m "pvélite" \
            --max-pvélite-delta-pct=1.0   # falha se delta > 1% em qualquer caso

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  security-scan:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t app:test .

      - name: Scan image (Trivy)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: app:test
          exit-code: "1"
          severity: CRITICAL,HIGH
          ignore-unfixed: true

  deploy-staging:
    runs-on: ubuntu-latest
    needs: [test, security-scan]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    environment: staging
    steps:
      - name: Build & push image
        run: |
          docker build -t registry.smartquotation.com.br/app:${GITHUB_SHA::8} .
          docker push registry.smartquotation.com.br/app:${GITHUB_SHA::8}

      - name: Deploy to staging
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: deploy
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/smartquotation
            export IMAGE_TAG=${GITHUB_SHA::8}
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml run --rm web \
              python manage.py migrate_schemas --executor=parallel
            docker compose -f docker-compose.prod.yml up -d
            docker compose -f docker-compose.prod.yml run --rm web \
              python manage.py collectstatic --noinput

      - name: Smoke test staging
        run: |
          sleep 15
          curl -f https://staging.smartquotation.com.br/health/ || exit 1

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production   # requer aprovação manual no GitHub
    steps:
      - name: Deploy to production
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: deploy
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/smartquotation
            export IMAGE_TAG=${GITHUB_SHA::8}
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml run --rm web \
              python manage.py migrate_schemas --executor=parallel
            docker compose -f docker-compose.prod.yml up -d --no-deps web worker beat
            docker compose -f docker-compose.prod.yml run --rm web \
              python manage.py collectstatic --noinput
```

---

## 6. Backup e Recuperação

### Estratégia de backup

```bash
#!/bin/bash
# /opt/smartquotation/scripts/backup.sh — executa via cron a cada 6h

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

# 1. Dump completo do PostgreSQL
docker compose exec -T db pg_dumpall -U ${POSTGRES_USER} \
  | age --encrypt --recipient "${BACKUP_PUBLIC_KEY}" \
  > "${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.age"

# 2. Snapshot do volume de uploads (rsync incremental)
rsync -av --link-dest=/backups/latest/uploads/ \
  /data/uploads/ "${BACKUP_DIR}/uploads/"

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

### Política de retenção de backup

| Frequência | Retenção | Storage estimado |
|---|---|---|
| A cada 6h (diário) | 7 dias | ~4 × 7 = 28 dumps |
| Diário (snapshot) | 30 dias | 30 dumps |
| Semanal | 90 dias | 13 dumps |
| Mensal | 365 dias | 12 dumps |
| Anual | 15 anos | 15 dumps (arquivamento frio) |

### RTO / RPO estimados

| Cenário | RPO (dados perdidos) | RTO (tempo até restauração) |
|---|---|---|
| Corrupção de banco | ≤ 6 horas | ≤ 2 horas |
| VPS inacessível | ≤ 6 horas | ≤ 4 horas (novo VPS + restore) |
| Exclusão acidental de tenant | ≤ 6 horas | ≤ 1 hora |
| Desastre total (datacenter) | ≤ 6 horas | ≤ 8 horas (off-site restore) |

### Restore procedure (runbook)

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
  docker compose exec -T db psql -U ${POSTGRES_USER}

# 6. Restaurar uploads
rsync -av /backups/latest/uploads/ /data/uploads/

# 7. Subir todos os serviços
docker compose up -d

# 8. Validar
curl -f https://novo-vps.smartquotation.com.br/health/
```

---

## 7. Observabilidade

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

## 8. Sizing de Infraestrutura (MVP)

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

## 9. Provisionamento (bootstrap do servidor)

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
