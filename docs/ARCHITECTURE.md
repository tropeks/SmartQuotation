---
# Contrato de documentação (Maestro E16).
# Arquitetura vigente do SmartQuotation: motor puro, adapter, apps Django, integrações ERP
# e a fronteira com o Cognitive Core (F1). Direção: .maestro/INTENT.md v3.
# Cover ESTREITO de propósito: as fronteiras estruturais (API pública do motor, adapter,
# wiring do projeto Django, registro de apps, compose). O miolo de cada app é governado
# pelo DATA_MODEL (models/migrations), API_SPEC (urls/views) e SECURITY (auth/RBAC).
covers:
  - pricing_engine/__init__.py
  - pricing_engine/feixe_quote.py
  - pricing_engine/permutador_quote.py
  - pricing_engine/rates.py
  - backend/apps/quotations/adapter.py
  - backend/smartquotation/**
  - backend/apps/*/apps.py
  - docker-compose*.yml
  - backend/Dockerfile
reviewed: 2026-09-27
---
# ARCHITECTURE.md — SmartQuotation

> **Status:** Aprovado, emendado em 2026-09-27 | **Versão:** 1.1 | **Referência:** `.maestro/INTENT.md` v2, `docs/PRODUCT_VISION.md` (10/07), PROJECT_BRIEF.md (2025, histórico)
>
> **Emenda 2026-09-27.** As seções 1 a 6 abaixo são o plano de 2025 e ficam como histórico.
> O que vale hoje está na **§0 (arquitetura vigente)** e na **§0.4 (fronteira com o Cognitive
> Core)**. ADRs que não valem mais estão marcadas **Superada**, com o motivo em uma linha.

---

## 0. Arquitetura vigente (medida no código em 2026-09-27)

### 0.1 Visão geral

Monólito modular Django com um motor de custeio em Python puro ao lado. Multi-tenant por
schema (django-tenants), UI server-rendered (templates + HTMX, Alpine pontual), sessão auth.

```
[Browser: orçamentista / engenheiro / gestor / PCP]
        │ HTTPS
        ▼
[cloudflared (túnel)] ── VPS de produção; nenhuma porta pública além do túnel é o alvo (F1-04)
        │
        ▼
[Django 5.2 + Gunicorn]  (docker-compose.prod.yml: web, worker, beat, db, redis)
   ├─ django-tenants ── schema por tenant, roteado pelo subdomínio
   ├─ sessão Django + CSRF + django-axes; TenantMembershipMiddleware; MustChangePassword
   ├─ RBAC configurável: Role (dado por tenant) × capability (registry em código,
   │   apps/access/capabilities.py, fail-closed) em RolePermission
   ├─ templates + HTMX ── UI; DRF só em /api/cotacoes/ (leitura) e /api/permutador/estimate/
   │
   ├─ apps/quotations/adapter.py ── recompute(): monta FeixeInputs + TenantCostChain do banco,
   │      chama o motor e persiste a EAP (Quotation → QuotationItem → ItemMaterial/ItemOperation)
   │      └──► pricing_engine/ (Python puro, zero Django)
   │             quote_feixe · permutador_quote.quote_completo (TEMA BEU/BEM…) · asme.py (UG-27/32,
   │             Ap.2, UG-21) · rates.TenantCostChain · process_params · rt_exposicoes
   ├─ CalculationSnapshot (hash + engine_version) → TechnicalApproval (CREA) → aprovação por
   │   estágios (apps/audit, apps/access) → Proposal/ProposalVersion (DOCX/PDF)
   ├─ production ── OF montada a partir do snapshot assinado, apontamento, ActualRate, ITP
   └─ integrations ── Nomus (prioritário), Protheus, Omie, SAP B1, Bling (Celery, por tenant)
        │
        ├──► PostgreSQL (public: Tenant/Domain/Plan · schema por tenant: o resto)
        ├──► Redis (broker Celery, cache)
        └──► Celery worker + beat (tarefas de integração ERP)
```

### 0.2 Mapa de componentes reais

| Componente | Onde | Responsabilidade | Falha |
|---|---|---|---|
| Motor de custeio | `pricing_engine/` | Custo por peso bruto, MO por driver físico, verificações ASME (alerta, não bloqueia) | Exceção sobe ao chamador; gates `tests/validate_*` no CI |
| Adapter | `backend/apps/quotations/adapter.py` | Único caminho que **persiste** resultado do motor (`recompute`) | Cotação fica sem recompute; nada gravado pela metade |
| Tenancy | `apps/tenants` | Tenant, Domain, Plan (schema public); `provision_tenant` | — |
| Contas e RBAC | `apps/accounts`, `apps/access` | UserProfile, Role como dado (`requires_crea`), matriz papel × capability, workflow de aprovação | Capability ausente do registry = negado |
| Auditoria | `apps/audit` | TechnicalApproval, ApprovalRequest/Case/Task (inbox por papel), AccessLog | — |
| Materiais | `apps/materials` | Material, MaterialPrice (cifrado, por forma), LigaMetalurgica, MaterialStandard | — |
| Parâmetros | `apps/engineering_params` | Rate, ProcessParameter, TenantParamConfig, RateSuggestion, KnobChangeProposal | — |
| Custos | `apps/cost_discovery`, `apps/cost_structure` | Cadeia de custo (seed top-down + back-solve), CostStructure (custo fixo/capacidade) | — |
| Catálogo TEMA | `apps/tema_templates` | ComponentTemplate/ComponentOperation; compor trocador por designação | Sem seed, `/tema/compor/` vazio |
| Propostas | `apps/proposals` | Template editável, DOCX (python-docx) e PDF (WeasyPrint, fallback chrome headless), envio por e-mail | `send_email` sem idempotência hoje (F1-03) |
| Produção | `apps/production` | OrdemFabricacao e filhos, apontamento, ActualRate, ITP | — |
| Integrações | `apps/integrations/{nomus,protheus,omie,sap_b1,bling}` | Conectores por tenant, runs assíncronos, logs/tentativas, healthcheck admin | Retry por run; fiscal fica no ERP do cliente |

### 0.3 Regras que a arquitetura sustenta (do INTENT v3)

- `pricing_engine` é lib pura; a persistência do resultado passa pelo adapter. Gates do feixe
  (−2,9%) e do permutador BEU/BEM (0,0%) nunca regridem.
- Custo é derivado (motor ou roll-up), nunca digitado; preço rotulado `referencial` ou
  `validado_custo` (`Quotation.pricing_basis`).
- Nenhum caminho (admin, API, Core) altera número assinado sem invalidar a assinatura.
- Fiscal e financeiro entram por integração com o ERP do cliente, nunca reconstruídos.
- UI nova nasce na identidade Prancha (`docs/DESIGN_PRANCHA.md`); `design-system-g.css` é legado.
- Sem LLM no produto hoje. IA, quando vier, entra pelo Core (§0.4), nunca decidindo número.

### 0.4 Fronteira com o Quantum Cognitive Core (F1)

O SmartQuotation é a primeira vertical do Core (`cognitive-core/docs/FASES.md` §4). Nada
disto existe no código ainda; é o contrato **previsto** para a F1.

- **`core_bridge`** (app Django novo, F1-02/F1-03): manifesto assinado de capabilities e
  endpoints finos `/api/core/v1/*` que chamam os serviços existentes, nunca o ORM por fora:
  `quotation.read`, `quotation.create_draft`, `quotation.recompute` (via adapter),
  `proposal.render` e `proposal.send` (classe externa, com `preview` e `idempotency_key`).
- **Token delegado por escopo** (F1-01): curto, emitido pelo SQ para um usuário real do
  tenant, com escopo de capability. O Core age como esse usuário; token de `quotation.read`
  recebe 403 em escrita. Não há conta de serviço nem leitura do banco do produto.
- **O SQ mantém a autoridade.** O manifesto declara, não concede: o produto reexecuta RBAC e
  validação em toda chamada. A aprovação CREA continua na esteira do produto.
- **Recálculo antes de efeito externo.** A guarda recalcula pelo motor e confere o hash do
  payload aprovado, o destinatário (cadastro fechado) e os limites antes de qualquer envio;
  envio de versão já `sent` é recusado. Autorização do envio com passkey e step-up (F1-32)
  antes do primeiro envio real.
- **Autonomia:** sombra e depois `act_with_approval`, nunca além, na F1.

### 0.5 Estado das ADRs de 2025

| ADR | Status | Motivo |
|---|---|---|
| ADR-001 Django + DRF | Vigente (emendada) | Django 5.2; DRF é superfície mínima, UI é server-rendered |
| ADR-002 PostgreSQL | Vigente | Sem pgaudit/RLS hoje; isolamento é o schema |
| ADR-003 Templates + HTMX | Vigente (emendada) | Sem Tailwind; identidade visual é a Prancha |
| ADR-004 Schema-per-tenant | Vigente | Implementada com django-tenants |
| ADR-005 `engineering/` + pint | **Superada** | O motor real é `pricing_engine/` (custeio paramétrico + verificações ASME), sem pint/Pydantic |
| ADR-006 docxtpl + WeasyPrint + LibreOffice | **Superada** | python-docx + WeasyPrint com fallback chrome headless, geração síncrona |
| ADR-007 allauth + TOTP | **Superada** | Sessão Django + axes + RBAC como dado; passkey/step-up prevista em F1-32 |
| ADR-008 VPS BR + Caddy + gate PVElite | **Superada** | Produção em VPS + cloudflared; gate de CI é o do motor (feixe/permutador), PVElite fora enquanto não houver casos no repo |

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
**Status:** Aprovado; emendada em 2026-09-27: o módulo de cálculo é `pricing_engine/`, não `engineering/`.
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
**Status:** Aprovado; emendada em 2026-09-27: sem Tailwind, identidade visual Prancha (`docs/DESIGN_PRANCHA.md`).
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
**Status:** **Superada** (2026-09-27): o motor é `pricing_engine/`, Python puro sem pint/Pydantic, e o gate de CI é o dos golden cases, não PVElite. Ver §0.
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
**Status:** **Superada** (2026-09-27): o código usa python-docx + WeasyPrint com fallback chrome headless, síncrono. Ver §0.2.
**Decisão:** `docxtpl` (Jinja2 em template Word) para DOCX + WeasyPrint para PDF; LibreOffice headless como fallback
**Justificativa:**
- Templates DOCX editáveis no Word pelo setor comercial sem depender de dev
- WeasyPrint dá controle CSS preciso para PDF
- LibreOffice headless para paridade visual DOCX→PDF quando exigido
- Geração assíncrona via Celery (não bloqueia request)

---

### ADR-007 — Autenticação, Autorização e Auditoria
**Status:** **Superada** (2026-09-27): sessão Django + axes + RBAC configurável (Role × capability); sem allauth/TOTP nem simple-history; passkey e step-up previstos em F1-32. TechnicalApproval segue vigente.
**Decisão:**
- Auth: `django-allauth` + MFA via TOTP (`django-otp`) obrigatório para roles privilegiados
- Autz: RBAC nativo Django com `Groups` mapeando perfis do produto
- Senhas: Argon2 (default Django moderno)
- Audit trail: `django-simple-history` em entidades de domínio + middleware `AccessLog` append-only
- Assinatura técnica: tabela `TechnicalApproval` com user_id, crea_number, art_number, timestamp, hash do snapshot de cálculo
- Caminho previsto: SSO/SAML (`django-saml2-auth`) para H2

---

### ADR-008 — Infraestrutura
**Status:** **Superada** (2026-09-27): produção roda em VPS + cloudflared, sem Caddy; o gate de CI é o do motor. Ver §0.1.
**Decisão:** VPS BR + Docker Compose (Gunicorn + PostgreSQL + Redis + Caddy + Celery) + GitHub Actions CI/CD
**Justificativa:**
- Soberania de dados em BR (exigência setorial implícita)
- Docker Compose: simples, auditável, reproduzível — escala para Kubernetes em H2 sem reescrita de aplicação
- Caddy: TLS automático (Let's Encrypt), zero config de SSL
- Redis: cache + sessions + rate limiting + fila Celery
- Backup: `pg_dump` cifrado com age/gpg → rclone para S3-compatible off-site; retenção 30/90/365 dias
- CI/CD: GitHub Actions com gate de regressão PVElite (deploy bloqueado se regressão falhar)

---

## 3. Diagrama de Arquitetura (plano 2025, superado pela §0.1)

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

## 4. Especificação de Componentes (plano 2025, superada pela §0.2)

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

## 5. Módulos Django (Apps) (plano 2025, superado pela §0.2)

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

> Emenda 2026-09-27: papéis são dado por tenant (`accounts.Role`) e a matriz é configurável
> (`access.RolePermission` × registry de capabilities). A tabela abaixo é o default de referência.

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

---

## Flags para o orchestrator

- Acoplamento motor↔Django: além do adapter, `tema_templates/services.py`, `engineering_params/simulation.py`, `cost_discovery/services.py`, `quotations/views.py` e `quotations/services.py` chamam `quote_completo`/`quote_feixe` direto (simulação e prévia, sem persistir EAP). Resolvido no INTENT v3 (decisão 01M3J7RNGCM5Y22RHHZSFWJPGR): o limite passa a ser "o único caminho que PERSISTE resultado do motor é o adapter", e essas chamadas de simulação ficam permitidas. A trava por import-linter entra como ordem depois da 002.
