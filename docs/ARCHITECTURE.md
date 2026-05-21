# ARCHITECTURE.md — SmartQuotation

> **Status:** Aprovado | **Versão:** 1.0 | **Referência:** PROJECT_BRIEF.md

---

## 1. Visão Geral

SmartQuotation é uma aplicação web multi-tenant monolítica modular (Modular Monolith),
com separação física de responsabilidades entre domínio de engenharia, domínio comercial,
infraestrutura e apresentação. A arquitetura é desenhada para:

1. **Sobreviver à auditoria NR-13/ISO 9001** — rastreabilidade e reprodução histórica de cálculos.
2. **Crescer para ERP** sem reescrita — o modelo de dados e os módulos são a fundação do H2/H3.
3. **Isolar tenants com evidência auditável** — schema-per-tenant no PostgreSQL.
4. **Manter o motor de cálculo independente do framework** — testável, versionável, auditável isoladamente.

---

## 2. Architecture Decision Records (ADRs)

### ADR-001 — Backend Framework
**Status:** Aprovado
**Contexto:** Sistema com cálculos normativos pesados, multi-tenant, RBAC, audit trail, geração de documentos, APIs para ERP, ciclo de vida 10+ anos.
**Decisão:** Python 3.12 + Django 5.x + Django REST Framework (DRF)
**Justificativa:**
- Django entrega de fábrica: ORM + migrations versionadas, admin, permissions, signals (audit), middleware de logging
- DRF gera API REST + OpenAPI automaticamente — canal direto para conectores ERP
- `django-tenants` resolve multi-tenancy com schema-per-tenant
- `django-simple-history` entrega audit trail por modelo (diff por campo, usuário, timestamp) sem código adicional
- Mesmo ecossistema do Vitali — sem curva de aprendizado para o time
- Módulo de cálculo fica em Python puro (`engineering/`) desacoplado do framework

**Alternativas rejeitadas:**
- Streamlit + SQLite: filesystem efêmero, sem multi-tenant real, auth frágil, sem caminho para ERP
- FastAPI + frontend SPA: sem admin gerado, sem batteries-included para CRUD pesado, overhead de SPA desnecessário para app interno
- Go (stack RemediX): domínio é regra-de-negócio-intensivo, não throughput-intensivo; time não é Go-first

**Consequências aceitas:** Django tem mais "magia" que FastAPI; mitigado por boas práticas de separação de camadas.

---

### ADR-002 — Banco de Dados
**Status:** Aprovado
**Contexto:** Transações ACID, multi-tenancy, audit trail, JSONB para parâmetros variáveis, retenção 15 anos, relatórios analíticos futuros.
**Decisão:** PostgreSQL 16+ com extensões `pgcrypto`, `pg_stat_statements`; `pgaudit` opcional
**Justificativa:**
- ACID forte: não-negociável para cotação→pedido (BOM parcial é inaceitável)
- Schemas múltiplos: multi-tenancy via `django-tenants` com isolamento físico auditável
- JSONB: parâmetros de cálculo como snapshot sem perder integridade dos campos estruturados
- `pgcrypto`: hash/cifragem em colunas sensíveis
- `pgaudit`: audit log no nível do banco (exigido por algumas auditorias 27001)
- Row-Level Security: segunda barreira além do schema-per-tenant
- Compatível com TimescaleDB para telemetria futura de chão de fábrica (H3)

**Alternativas rejeitadas:**
- SQLite: sem concorrência real, sem schemas, sem RLS, sem extensões de auditoria
- MySQL/MariaDB: sem JSONB performático, sem schemas-como-tenant, sem pgaudit

**Consequências aceitas:** Operação mais complexa que SQLite — resolvida com managed service quando necessário.

---

### ADR-003 — Frontend
**Status:** Aprovado
**Contexto:** UI predominantemente de formulários complexos (data sheet ASME/TEMA), tabelas editáveis (BOM, roteiro), cálculo reativo. Usuário interno. Time pequeno.
**Decisão:** Django Templates + HTMX + Alpine.js + Tailwind CSS
**Justificativa:**
- HTMX entrega interatividade tipo SPA (recalcular peso ao trocar material, atualizar tabela) sem build pipeline de SPA
- Alpine.js cobre client-side puro (show/hide, máscaras) sem trazer React
- Toda lógica de cálculo permanece no servidor — centraliza logs, elimina risco de manipulação client-side
- Velocidade de desenvolvimento maior que Next.js para formulários pesados internos
- Backend continua API REST (DRF) — frontend React pode ser plugado depois se necessário (portal cliente H3)

**Alternativas rejeitadas:**
- Next.js + React: overhead de SPA sem ganho funcional para app interno de formulários; reservado para portal cliente H3
- Streamlit: já tratado em ADR-001

**Consequências aceitas:** Menos "moderno" — mitigado pelo fato de o backend ser API REST plugável.

---

### ADR-004 — Multi-tenancy
**Status:** Aprovado
**Contexto:** Produto SaaS com múltiplos clientes desde o dia um. Isolamento físico auditável exigido.
**Decisão:** `django-tenants` com schema-per-tenant no PostgreSQL
**Justificativa:**
- Isolamento físico de dados por schema — cada tenant é um namespace Postgres separado
- Demonstrável em auditoria 27001 (não é apenas lógico via WHERE tenant_id = X)
- Migrations por tenant com `migrate_schemas`
- Schema `public` para tabelas compartilhadas (Tenant, Domain, planos SaaS)

**Alternativas rejeitadas:**
- Row-per-tenant (tenant_id em todas as tabelas): isolamento apenas lógico, risco de vazamento por bug de query
- Database-per-tenant: operação excessiva para PMEs com dezenas de tenants

**Consequências aceitas:** Migrations mais cuidadosas — mitigado por CI que roda migrate_schemas em staging antes de produção.

---

### ADR-005 — Motor de Cálculo Normativo
**Status:** Aprovado
**Contexto:** Cálculo ASME/TEMA é o produto principal. Sujeito a auditoria. Precisa de versionamento, reprodução histórica, validação contra PVElite.
**Decisão:** Módulo Python puro `engineering/` desacoplado do Django, com Pydantic v2 + `pint` para unidades
**Estrutura:**
```
engineering/
  asme/
    viii_div1/
      shell.py          # UG-27 — espessura de casco cilíndrico
      heads.py          # UG-32 — tampos
      nozzles.py        # UG-37 — reforço de bocais
      allowable_stress.py
    viii_div2/          # H2
  tema/
    shell_side.py
    tube_side.py
    tubesheets.py
  api/
    tank_650.py         # H2
  b31/                  # H2
  units.py              # pint unit registry
  versioning.py         # decorator @calculation(version, standard)
  snapshot.py           # serialização de inputs/outputs para gravação
```
**Justificativa:**
- Funções puras (input dataclass → output dataclass): testáveis isoladamente, sem efeitos colaterais
- Decorator `@calculation(version="1.0.0", standard="ASME VIII Div.1 UG-27")` versiona cada função
- Cada cotação grava snapshot de inputs + versão da função → reprodução histórica trivial
- `pint` elimina bugs de conversão SI/imperial (caldeiraria mistura mm/in, MPa/psi, kg/lb)
- Pytest com casos canônicos do PVElite como suite de regressão — gate obrigatório de CI
- Separação física: auditoria pode examinar o módulo `engineering/` isoladamente

**Consequências aceitas:** Disciplina de versionamento exige rigor do dev — mitigado por code review e CI gate.

---

### ADR-006 — Geração de Documentos
**Status:** Aprovado
**Decisão:** `docxtpl` (Jinja2 em template Word) para DOCX + WeasyPrint para PDF; LibreOffice headless como fallback
**Justificativa:**
- Templates DOCX editáveis no Word pelo setor comercial sem depender de dev
- WeasyPrint dá controle CSS preciso para PDF
- LibreOffice headless para paridade visual DOCX→PDF quando exigido
- Geração assíncrona via Celery (não bloqueia request)

---

### ADR-007 — Autenticação, Autorização e Auditoria
**Status:** Aprovado
**Decisão:**
- Auth: `django-allauth` + MFA via TOTP (`django-otp`) obrigatório para roles privilegiados
- Autz: RBAC nativo Django com `Groups` mapeando perfis do produto
- Senhas: Argon2 (default Django moderno)
- Audit trail: `django-simple-history` em entidades de domínio + middleware `AccessLog` append-only
- Assinatura técnica: tabela `TechnicalApproval` com user_id, crea_number, art_number, timestamp, hash do snapshot de cálculo
- Caminho previsto: SSO/SAML (`django-saml2-auth`) para H2

---

### ADR-008 — Infraestrutura
**Status:** Aprovado
**Decisão:** VPS BR + Docker Compose (Gunicorn + PostgreSQL + Redis + Caddy + Celery) + GitHub Actions CI/CD
**Justificativa:**
- Soberania de dados em BR (exigência setorial implícita)
- Docker Compose: simples, auditável, reproduzível — escala para Kubernetes em H2 sem reescrita de aplicação
- Caddy: TLS automático (Let's Encrypt), zero config de SSL
- Redis: cache + sessions + rate limiting + fila Celery
- Backup: `pg_dump` cifrado com age/gpg → rclone para S3-compatible off-site; retenção 30/90/365 dias
- CI/CD: GitHub Actions com gate de regressão PVElite (deploy bloqueado se regressão falhar)

---

## 3. Diagrama de Arquitetura

```
[Browser: Orçamentista / Engenheiro / Gestor / PCP]
        │ HTTPS TLS 1.3
        ▼
[Caddy] ── reverse proxy + ACME/Let's Encrypt + HTTP security headers
        │
        ▼
[Django 5 + Gunicorn]
   ├─ django-tenants ── schema routing por subdomain/header
   ├─ DRF ── API REST v1 + OpenAPI spec
   ├─ HTMX Templates ── UI server-rendered
   ├─ django-allauth + django-otp ── auth + MFA
   ├─ django-simple-history ── audit trail por modelo
   ├─ RBAC (Groups + Permissions)
   │
   ├─── engineering/ ── módulo puro de cálculo normativo
   │      ├─ asme/viii_div1/ ── UG-27, UG-32, UG-37
   │      ├─ tema/ ── trocadores
   │      ├─ units.py (pint)
   │      └─ versioning.py + snapshot.py
   │
   ├─── pricing/ ── formação de preço
   │      ├─ material_cost.py
   │      ├─ labor_cost.py (hierarquia 3 camadas)
   │      ├─ overhead.py
   │      └─ price_formation.py
   │
   └─── documents/ ── geração de proposta
          ├─ docx_renderer.py (docxtpl)
          └─ pdf_renderer.py (WeasyPrint)
        │
        ├──► [PostgreSQL 16]
        │      ├─ schema: public (Tenant, Domain, Plan)
        │      ├─ schema: tenant_acme (Equipment, Quotation, ...)
        │      └─ schema: tenant_xyz (Equipment, Quotation, ...)
        │
        ├──► [Redis]
        │      ├─ Django cache (query cache, session store)
        │      ├─ Rate limiting (django-ratelimit)
        │      └─ Celery broker
        │
        └──► [Celery Worker]
               ├─ task: generate_proposal_docx
               ├─ task: generate_proposal_pdf
               ├─ task: send_email_notification
               └─ task: run_pvélite_regression (CI only)

[Volume Docker: /data/uploads/] ── data sheets, desenhos, laudos de terceiros
[Volume Docker: /data/backups/] ── pg_dump cifrado local

[GitHub Actions CI/CD]
   ├─ lint (ruff, black)
   ├─ test (pytest unit + integration)
   ├─ regressão PVElite (gate: falhou = deploy bloqueado)
   ├─ security scan (bandit, pip-audit, trivy)
   ├─ build Docker image
   ├─ push registry
   └─ deploy SSH → docker compose pull && up -d

[Sentry] ◄── erros de runtime
[Uptime Kuma] ◄── uptime e latência
[rclone cron] ──► pg_dump cifrado → S3-compatible off-site (Backblaze B2)
```

---

## 4. Especificação de Componentes

### 4.1 Django Application (Core)
**Responsabilidade:** Orquestrar todos os fluxos de negócio — cotação, cálculo, preço, proposta, audit.
**Inputs:** Requests HTTP (browser via HTMX, API REST via DRF)
**Outputs:** HTML renderizado, JSON (DRF), tarefas Celery, registros no banco
**Dependências:** PostgreSQL, Redis, módulos `engineering/`, `pricing/`, `documents/`
**Scaling:** Horizontal via múltiplos containers Gunicorn atrás do Caddy (H2)
**Failure mode:** Queda derruba UI e API; Redis e Postgres permanecem; recovery automático via Docker `restart: unless-stopped`

### 4.2 engineering/ (Motor de Cálculo)
**Responsabilidade:** Executar cálculos normativos ASME/TEMA com rastreabilidade e versionamento.
**Inputs:** Dataclasses Pydantic com parâmetros do equipamento (dimensões, material, pressão, temperatura)
**Outputs:** Dataclasses com resultados (espessuras, pesos, áreas, volumes) + metadados (versão da função, norma aplicada)
**Dependências:** `pint` (unidades), `pydantic` (validação), zero dependência de Django
**Scaling:** CPU-bound puro; escala horizontalmente com o processo Django ou extrai para microserviço em H3
**Failure mode:** Exceção propagada ao chamador com mensagem estruturada; nunca retorna resultado silenciosamente errado

### 4.3 pricing/ (Formação de Preço)
**Responsabilidade:** Calcular custo total e preço de venda de uma cotação.
**Inputs:** BOM com quantidades e pesos, roteiro com operações, overhead do tenant, margem desejada
**Outputs:** Breakdown de custo (material, mão-de-obra, overhead, impostos) + preço de venda
**Dependências:** Tabelas de preço de material, `Rate` (3 camadas), configuração fiscal do tenant
**Scaling:** Stateless, escala com Django
**Failure mode:** Retorna erro estruturado se faltarem dados de preço ou índice

### 4.4 documents/ (Geração de Proposta)
**Responsabilidade:** Renderizar proposta técnico-comercial em DOCX e PDF.
**Inputs:** Dados da cotação + dados do tenant (logo, template) + dados do cliente
**Outputs:** Arquivo DOCX e/ou PDF armazenado em volume + URL de download
**Dependências:** `docxtpl`, `WeasyPrint`, Celery (assíncrono), volume de storage
**Scaling:** Celery workers escalam horizontalmente; geração de PDF é CPU-intensive
**Failure mode:** Tarefa Celery com retry (3x, backoff exponencial); usuário notificado por notificação in-app

### 4.5 PostgreSQL
**Responsabilidade:** Armazenamento persistente com isolamento por schema por tenant.
**Scaling:** Read replicas para relatórios em H2; connection pooling via PgBouncer em H2
**Failure mode:** Aplicação entra em modo degradado; dados não são perdidos; recovery via WAL archiving

### 4.6 Redis
**Responsabilidade:** Cache, session store, rate limiting e broker de tarefas Celery.
**Failure mode:** Cache miss degrada performance mas não quebra funcionalidade; sessions caem (re-login); tarefas ficam na fila até Redis voltar

### 4.7 Celery Worker
**Responsabilidade:** Processar tarefas assíncronas (geração de documentos, e-mails, regressões).
**Scaling:** Múltiplos workers com `concurrency` configurável; filas separadas por prioridade
**Failure mode:** Tarefas são re-enfileiradas automaticamente; resultados de tarefas têm TTL configurável

---

## 5. Módulos Django (Apps)

```
smartquotation/
  apps/
    tenants/          # Tenant, Domain, Plan, Subscription
    accounts/         # User, Profile, RBAC, MFA, TechnicalApproval
    materials/        # Material, MaterialProperty, PriceHistory
    equipment/        # Equipment (abstract), PressureVessel, HeatExchanger, Component
    quotations/       # Quotation, QuotationVersion, QuotationItem
    bom/              # BillOfMaterials, BOMItem (H1 estrutura, H2 ativa)
    routing/          # ManufacturingRoute, Operation, Rate (3 camadas)
    pricing/          # CostBreakdown, PriceFormation, TaxConfig
    proposals/        # Proposal, ProposalTemplate, ProposalDocument
    audit/            # AccessLog, TechnicalApproval
    integrations/     # ERP connectors (H2) — plugável por tenant
  engineering/        # Módulo puro de cálculo (fora dos apps Django)
  pricing/            # Módulo puro de formação de preço
  documents/          # Módulo puro de renderização de documentos
```

---

## 6. RBAC — Matriz de Perfis e Permissões

| Permissão | Orçamentista | Engenheiro | Gestor Comercial | PCP | Admin |
|---|---|---|---|---|---|
| Criar/editar cotação | ✅ | ✅ | ❌ | ❌ | ✅ |
| Visualizar cotação | ✅ | ✅ | ✅ | ✅ | ✅ |
| Assinar cálculo (ART) | ❌ | ✅ | ❌ | ❌ | ✅ |
| Aprovar proposta para envio | ❌ | ❌ | ✅ | ❌ | ✅ |
| Converter cotação em OF | ❌ | ❌ | ✅ | ✅ | ✅ |
| Gerenciar materiais/índices | ❌ | ✅ | ❌ | ❌ | ✅ |
| Gerenciar usuários | ❌ | ❌ | ❌ | ❌ | ✅ |
| Ver relatórios de rentabilidade | ❌ | ❌ | ✅ | ❌ | ✅ |
| Configurar tenant | ❌ | ❌ | ❌ | ❌ | ✅ |
| Acessar API externa (ERP) | ❌ | ❌ | ❌ | ❌ | ✅ |
