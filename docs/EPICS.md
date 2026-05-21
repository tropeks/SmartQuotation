# EPICS.md — SmartQuotation

> **Status:** Aprovado | **Versão:** 1.0 | **Referência:** PROJECT_BRIEF.md, DATA_MODEL.md, API_SPEC.md

---

## Grafo de Dependências

```
[E-001] Fundação & Multi-tenant
    └──► [E-002] Autenticação & RBAC
              └──► [E-003] Cadastros Base (Materiais, Operações, Clientes)
                        └──► [E-004] Motor de Cálculo ASME/TEMA
                                  └──► [E-005] Cotação & Equipamentos
                                            ├──► [E-006] Custo & Formação de Preço
                                            │         └──► [E-007] Proposta Comercial (DOCX/PDF)
                                            └──► [E-008] Aprovação Técnica & Audit Trail
```

---

## E-001 — Fundação & Multi-tenant

**Goal:** Infraestrutura base rodando com isolamento por tenant funcional.
**Priority:** P0 | **Sprint:** 0 | **Complexity:** M

### S-001 — Setup do projeto Django + PostgreSQL + django-tenants
**As a** dev, **I want** a base do projeto configurada com multi-tenancy **so that** todos os demais épicos possam ser desenvolvidos sobre uma fundação correta.

**Acceptance Criteria:**
- [ ] Django 5.x + DRF instalados e configurados
- [ ] PostgreSQL 16 rodando via Docker Compose com schema `public`
- [ ] `django-tenants` configurado com `TENANT_MODEL` e `DOMAIN_MODEL`
- [ ] Schema `public` contém: `Tenant`, `Domain`, `Plan`
- [ ] Criação de novo tenant via management command cria schema isolado automaticamente
- [ ] Tenant A não consegue ver dados do Tenant B (teste de isolamento obrigatório)
- [ ] `migrate_schemas` roda sem erros para `public` e para schema de tenant

**Tasks:**
- [ ] Criar repositório, estrutura de apps, settings por ambiente (base/dev/staging/prod)
- [ ] Configurar `django-tenants` + `DATABASES` com schema routing
- [ ] Criar modelos `Tenant`, `Domain`, `Plan` no schema public
- [ ] Escrever `create_tenant` management command
- [ ] Escrever testes de isolamento (pytest-django + schema switching)
- [ ] Configurar Docker Compose dev com Postgres + Redis + Celery

**Story Points:** 8

---

### S-002 — Health check, logging estruturado e Sentry
**Acceptance Criteria:**
- [ ] `GET /health/` retorna JSON com status de db e redis
- [ ] Logs em formato JSON (structlog ou django-structlog)
- [ ] Sentry configurado para staging e produção
- [ ] Variáveis de ambiente validadas no startup (ImproperlyConfigured se faltarem)

**Story Points:** 3

---

## E-002 — Autenticação & RBAC

**Goal:** Usuários podem fazer login seguro com MFA e acessar apenas o que seu papel permite.
**Priority:** P0 | **Sprint:** 0–1 | **Complexity:** M

### S-003 — Login, logout e refresh token
**Acceptance Criteria:**
- [ ] `POST /api/v1/auth/login` com email + senha retorna JWT (access 15min + refresh cookie 7d)
- [ ] Rate limiting: 5 tentativas/min por IP; 10 falhas/hora → account lockout 30min
- [ ] Senhas hasheadas com Argon2id
- [ ] `POST /api/v1/auth/logout` invalida refresh token (blocklist Redis)
- [ ] `POST /api/v1/auth/refresh` emite novo access token; refresh token é rotacionado

**Story Points:** 5

---

### S-004 — MFA via TOTP
**Acceptance Criteria:**
- [ ] Usuário pode ativar TOTP no perfil (`GET /api/v1/users/me/mfa/setup/` retorna QR code)
- [ ] Login de usuário com MFA ativo exige `totp_code`; sem ele retorna 400 `MFA_REQUIRED`
- [ ] Roles `admin` e `gestor_comercial` têm MFA obrigatório (middleware bloqueia acesso sem MFA configurado)
- [ ] Backup codes gerados no setup (10 códigos de uso único)

**Story Points:** 5

---

### S-005 — RBAC: perfis, permissões e middleware de tenant
**Acceptance Criteria:**
- [ ] 5 roles implementadas com `Groups` Django: `orçamentista`, `engenheiro`, `gestor_comercial`, `pcp`, `admin`
- [ ] Matriz de permissões da ARCHITECTURE.md implementada e testada
- [ ] Middleware garante que request está associado ao tenant correto pelo subdomínio
- [ ] Admin pode criar, editar e desativar usuários do próprio tenant
- [ ] Engenheiro sem `crea_number` não pode ser promovido a role `engenheiro` (validação)
- [ ] `GET /api/v1/users/me/` retorna perfil completo incluindo role e permissões

**Story Points:** 8

---

## E-003 — Cadastros Base

**Goal:** Dados mestre de materiais, operações, máquinas e clientes estão cadastrados e disponíveis.
**Priority:** P0 | **Sprint:** 1 | **Complexity:** M

### S-006 — Catálogo de materiais com propriedades e preços
**Acceptance Criteria:**
- [ ] CRUD completo de `Material` (código, nome, norma, propriedades físicas)
- [ ] Tabela de `MaterialAllowableStress` por temperatura (interpolação linear entre pontos)
- [ ] `GET /api/v1/materials/{id}/allowable-stress/?temp_c=250` retorna S correto com flag `interpolated`
- [ ] `MaterialPrice` com forma (chapa/tubo/barra/forjado/fundido), validade e histórico
- [ ] Preço vigente resolvido automaticamente (mais recente válido na data)
- [ ] Seeds com materiais mais comuns: SA-516-70, SA-240-316L, SA-106-B, SA-312-TP304L
- [ ] Admin pode importar lista de materiais via CSV

**Story Points:** 8

---

### S-007 — Catálogo de operações, máquinas e índices (Rate 3-camadas)
**Acceptance Criteria:**
- [ ] CRUD de `Operation` (código, nome, categoria, unidade de medição)
- [ ] CRUD de `Machine` (código, nome, hora-máquina)
- [ ] Seeds com operações padrão: SOLD-MIG, SOLD-TIG, CALAN, CORTE-PLASMA, JATO, PWHT, RX-100, MONT
- [ ] `Rate` com layer `industry_standard` populado com índices padrão da indústria de caldeiraria
- [ ] Admin do tenant pode criar `Rate` com layer `tenant` para sobrescrever padrão
- [ ] Lógica de resolução de rate: `actual` (confidence>70) → `tenant` → `industry_standard`
- [ ] API `GET /api/v1/rates/` lista rates com indicação da camada efetiva

**Story Points:** 8

---

### S-008 — Cadastro de clientes
**Acceptance Criteria:**
- [ ] CRUD de `Customer` (empresa, CNPJ, contato, endereço)
- [ ] Validação de formato de CNPJ (dígitos verificadores)
- [ ] Busca por nome e CNPJ com autocomplete
- [ ] CNPJ único por tenant

**Story Points:** 3

---

## E-004 — Motor de Cálculo ASME/TEMA

**Goal:** Sistema calcula espessuras, pesos e dimensões derivadas com precisão validada contra PVElite.
**Priority:** P0 | **Sprint:** 1–2 | **Complexity:** XL

### S-009 — Estrutura do módulo `engineering/` e decorator de versionamento
**Acceptance Criteria:**
- [ ] Módulo `engineering/` desacoplado do Django (zero import de Django)
- [ ] Decorator `@calculation(version, standard)` implementado
- [ ] `CalculationSnapshot` serializa inputs (Pydantic dataclass) + outputs + versão para JSONB
- [ ] Hash SHA-256 dos inputs calculado e gravado
- [ ] `pint` configurado com unit registry customizado (unidades comuns de caldeiraria)
- [ ] Testes unitários para conversões de unidade SI/imperial

**Story Points:** 5

---

### S-010 — Cálculo de casco cilíndrico (ASME VIII Div.1 UG-27)
**Acceptance Criteria:**
- [ ] `calc_shell_thickness(pressure, radius, allowable_stress, joint_efficiency, corrosion_allowance)` → `required_thickness`, `mawp`
- [ ] Fórmulas UG-27(c)(1) e UG-27(c)(2) implementadas (t/R < 0.5 e ≥ 0.5)
- [ ] Resultados validados contra ≥ 10 casos canônicos do PVElite (delta ≤ 1%)
- [ ] Tratamento de erro para inputs fora de range (ex: pressão negativa, material sem S na temperatura)
- [ ] Peso do casco calculado a partir das dimensões + densidade do material

**Story Points:** 8

---

### S-011 — Cálculo de tampos (ASME VIII Div.1 UG-32)
**Acceptance Criteria:**
- [ ] Toriesférico (UG-32(e)): `calc_toriespherical_head`
- [ ] Elíptico 2:1 (UG-32(d)): `calc_elliptical_head`
- [ ] Hemisférico (UG-32(f)): `calc_hemispherical_head`
- [ ] Cônico (UG-32(g)): `calc_conical_head`
- [ ] Plano (UG-34): `calc_flat_head` (circular e não-circular)
- [ ] Peso de cada tipo calculado
- [ ] Validação contra ≥ 5 casos PVElite por tipo

**Story Points:** 8

---

### S-012 — Cálculo de bocais e reforço (ASME VIII Div.1 UG-37)
**Acceptance Criteria:**
- [ ] `calc_nozzle_reinforcement(nozzle_od, nozzle_thickness, shell_thickness_calc, ...)`
- [ ] Área de reforço necessária vs. disponível (A1 + A2 + A3 + A41 + A42 + A5)
- [ ] Flag `reinforcement_pad_required: bool` no output
- [ ] Suporte a bocais radiais em casco e em tampo
- [ ] Validação contra ≥ 5 casos PVElite

**Story Points:** 8

---

### S-013 — Cálculo de trocadores de calor (TEMA)
**Acceptance Criteria:**
- [ ] Dimensionamento do lado casco: espessura conforme ASME VIII (reutiliza S-010)
- [ ] Espelho (tubesheet) — método TEMA para tubesheets fixos
- [ ] Seleção de pitch e layout de tubos (triangular/quadrado) → número de tubos em função do diâmetro
- [ ] Área de transferência de calor calculada: `A = N_tubes × π × OD × L`
- [ ] Chicanas: espaçamento e número calculados a partir do diâmetro do casco
- [ ] Peso estimado do feixe tubular (tubos + chicanas + tirantes)
- [ ] Validação contra ≥ 5 casos PVElite/HTRI

**Story Points:** 13

---

### S-014 — Suite de regressão PVElite como gate de CI
**Acceptance Criteria:**
- [ ] Pasta `tests/engineering/regression/` com casos de teste em YAML (input + expected output do PVElite)
- [ ] Fixture parametrizado que lê os YAML e roda contra o motor
- [ ] Assert: delta ≤ 1% para espessura calculada; ≤ 2% para peso
- [ ] pytest marker `@pytest.mark.pvélite` para filtrar só esses testes no CI
- [ ] CI job falha se qualquer caso de regressão ultrapassar o delta máximo
- [ ] ≥ 25 casos cobertos no MVP (expansão contínua)

**Story Points:** 5

---

## E-005 — Cotação & Equipamentos

**Goal:** Usuário pode criar uma cotação completa com equipamentos parametrizados e componentes calculados.
**Priority:** P0 | **Sprint:** 2–3 | **Complexity:** L

### S-015 — CRUD de cotações com workflow de status
**Acceptance Criteria:**
- [ ] Criação de cotação gera número sequencial por tenant (COT-{ANO}-{SEQ:03d})
- [ ] Workflow de status implementado (draft → in_review → pending_approval → approved → sent → won/lost)
- [ ] Revisão de cotação cria nova cotação com `revision+1` apontando para original
- [ ] Cotação em status `approved` ou posterior bloqueia edição (HTTP 409)
- [ ] Listagem com filtros por status, cliente, período e busca full-text

**Story Points:** 8

---

### S-016 — Cadastro de equipamentos (Vaso de Pressão)
**Acceptance Criteria:**
- [ ] Formulário HTMX com data sheet de vaso de pressão (todos os campos de `PressureVessel`)
- [ ] Validação em tempo real: campos obrigatórios, ranges numéricos, material compatível com temperatura de design
- [ ] Seleção de material com autocomplete e exibição de propriedades (σ_t, S value na T de design)
- [ ] Múltiplos equipamentos por cotação com drag-and-drop de reordenação

**Story Points:** 8

---

### S-017 — Cadastro de equipamentos (Trocador de Calor)
**Acceptance Criteria:**
- [ ] Formulário HTMX com data sheet de trocador (todos os campos de `HeatExchanger`)
- [ ] Seleção de tipo TEMA (E, F, G, H, J, X, K) com diagrama ilustrativo
- [ ] Campos específicos de cada lado (casco e tubo)
- [ ] Validação de combinações válidas de classe TEMA × tipo

**Story Points:** 8

---

### S-018 — Disparo e visualização de cálculo por equipamento
**Acceptance Criteria:**
- [ ] Botão "Calcular" dispara tarefa Celery e exibe progresso via polling HTMX
- [ ] Após cálculo: exibe resultado por componente (espessura calculada, peso, MAWP)
- [ ] Componente mostra badge "Calculado pelo sistema" ou "Importado" conforme `calculation_mode`
- [ ] Usuário pode ver histórico de snapshots de cálculo por componente
- [ ] Espessura adotada pode ser editada manualmente (≥ calculada — validação)

**Story Points:** 8

---

### S-019 — Importação de cálculo de terceiro (modo Importado)
**Acceptance Criteria:**
- [ ] Upload de arquivo (PDF/DOCX, max 20MB) para um componente específico
- [ ] SHA-256 do arquivo calculado e gravado em `imported_document_hash`
- [ ] Componente muda para `calculation_mode = 'imported'`
- [ ] Arquivo acessível apenas por usuários do tenant com permissão de visualização
- [ ] Auditoria: AccessLog registra upload com user_id e timestamp

**Story Points:** 5

---

## E-006 — Custo & Formação de Preço

**Goal:** Sistema calcula custo detalhado e forma o preço de venda com breakdown completo.
**Priority:** P0 | **Sprint:** 3 | **Complexity:** L

### S-020 — BOM automático a partir dos componentes calculados
**Acceptance Criteria:**
- [ ] BOM gerado automaticamente após cálculo de equipamento
- [ ] Cada `BOMItem` tem: material, forma, peso bruto (com aproveitamento/kerf), peso líquido, preço unitário, custo total
- [ ] Aproveitamento de chapa configurável por material (default 85%)
- [ ] Kerf de corte plasma configurável por espessura
- [ ] BOM editável manualmente com override de quantidade e preço

**Story Points:** 8

---

### S-021 — Roteiro de fabricação automático
**Acceptance Criteria:**
- [ ] Roteiro gerado a partir dos componentes: cada componente gera as operações padrão do seu tipo
- [ ] Quantidade de cada operação calculada a partir da geometria (metros de solda, m² de jateamento, etc.)
- [ ] Horas estimadas calculadas via `Rate` (hierarquia 3-camadas)
- [ ] Roteiro exibe: operation, machine, rate utilizado (com layer indicado), horas estimadas, custo
- [ ] Usuário pode adicionar, remover e reordenar operações manualmente

**Story Points:** 8

---

### S-022 — Formação de preço e breakdown
**Acceptance Criteria:**
- [ ] `POST /api/v1/quotations/{id}/price-formation/` calcula e grava PriceFormation
- [ ] Breakdown por tipo de custo (material, mão-de-obra, overhead, serviços externos)
- [ ] Breakdown por equipamento
- [ ] Aplicação de overhead (% sobre custo direto, configurável por tenant)
- [ ] Aplicação de margem com cálculo de markup e margem líquida
- [ ] Configuração fiscal por tenant (ICMS, PIS/COFINS, ISS) aplicada ao preço de venda
- [ ] KPI `price_per_kg_brl` calculado para benchmarking
- [ ] Gestor pode ajustar margem e recalcular sem perder o breakdown

**Story Points:** 8

---

## E-007 — Proposta Comercial

**Goal:** Sistema gera proposta técnico-comercial em DOCX e PDF com layout profissional.
**Priority:** P1 | **Sprint:** 4 | **Complexity:** M

### S-023 — Template de proposta customizável por tenant
**Acceptance Criteria:**
- [ ] Admin do tenant pode fazer upload de template `.docx` (com tags Jinja `{{variavel}}`)
- [ ] Tags documentadas: `{{company_name}}`, `{{customer_name}}`, `{{quotation_number}}`, `{{equipment_list}}`, `{{total_price}}`, etc.
- [ ] Template padrão do sistema disponível para todos os tenants
- [ ] Prévia do template renderizável com dados de exemplo

**Story Points:** 5

---

### S-024 — Geração assíncrona de DOCX e PDF
**Acceptance Criteria:**
- [ ] `POST /api/v1/quotations/{id}/proposals/` dispara task Celery e retorna `task_id`
- [ ] Tarefa gera DOCX via `docxtpl` + PDF via WeasyPrint
- [ ] Arquivo gravado em `/data/uploads/{tenant}/{quotation_id}/proposals/`
- [ ] SHA-256 do arquivo gravado em `Proposal.docx_hash` / `pdf_hash`
- [ ] Download via endpoint autenticado com verificação de permissão
- [ ] AccessLog registra cada download (user_id, timestamp, IP)
- [ ] Notificação in-app quando proposta está pronta

**Story Points:** 8

---

## E-008 — Aprovação Técnica & Audit Trail

**Goal:** Engenheiro assina digitalmente os cálculos e todo o histórico de auditoria está acessível.
**Priority:** P0 | **Sprint:** 4–5 | **Complexity:** M

### S-025 — Aprovação técnica com vinculação ao snapshot de cálculo
**Acceptance Criteria:**
- [ ] Engenheiro com CREA cadastrado pode aprovar cotação ou componente específico
- [ ] `TechnicalApproval` criado com: `crea_number`, `art_number`, `calculation_snapshot_hash` (SHA-256 do snapshot aprovado), `approved_at`
- [ ] Se componente for recalculado após aprovação → aprovação é automaticamente revogada e engineering é notificado
- [ ] Cotação só pode ir para `in_review` se todos os componentes calculados tiverem aprovação técnica
- [ ] Revogação manual registra `revoked_at`, `revoked_by`, `reason` (append-only)
- [ ] Disclaimer de responsabilidade técnica exibido na primeira aprovação da sessão

**Story Points:** 8

---

### S-026 — Tela de auditoria e histórico
**Acceptance Criteria:**
- [ ] Admin e Gestor podem ver histórico completo de uma cotação (quem editou, o quê, quando)
- [ ] `django-simple-history` habilitado em: Quotation, Equipment, Component, Material, Rate, UserProfile
- [ ] Diff visual por campo (valor anterior → valor atual) na tela de histórico
- [ ] AccessLog pesquisável por usuário, recurso e período
- [ ] Export de AccessLog em CSV para auditorias externas (ISO 9001, NR-13)

**Story Points:** 5

---

### S-027 — Validação PVElite manual e registro de delta
**Acceptance Criteria:**
- [ ] Engenheiro pode registrar resultado do PVElite para um snapshot de cálculo
- [ ] Sistema calcula e exibe delta % entre resultado próprio e PVElite
- [ ] Snapshot marcado como `pvélite_validated = True` com data e responsável
- [ ] Dashboard de qualidade do motor: % de snapshots validados, distribuição de deltas, casos fora de tolerância
- [ ] Alerta automático se delta > 2% (requer investigação antes de aprovação técnica)

**Story Points:** 5

---

## E-009 — Dashboard & Relatórios (P1, Sprint 5)

### S-028 — Dashboard principal por tenant
**Acceptance Criteria:**
- [ ] Cards: cotações do mês (total, aprovadas, ganhas, perdidas), taxa de conversão, ticket médio
- [ ] Gráfico de cotações por status (últimos 90 dias)
- [ ] Cotações em aberto por valor decrescente
- [ ] Rentabilidade média (margem % média das cotações ganhas)
- [ ] Acesso: Gestor e Admin

**Story Points:** 5

---

### S-029 — Relatórios exportáveis
**Acceptance Criteria:**
- [ ] Relatório de cotações por período: CSV e PDF
- [ ] Relatório de rentabilidade por cliente: margem % por cliente
- [ ] Relatório de materiais: consumo e custo por material no período
- [ ] Relatório de operações: horas estimadas vs. reais (quando disponível em H2)

**Story Points:** 5

---

## Resumo de Story Points por Epic

| Epic | Stories | SP Total | Sprint(s) |
|---|---|---|---|
| E-001 Fundação | S-001, S-002 | 11 | 0 |
| E-002 Auth & RBAC | S-003, S-004, S-005 | 18 | 0–1 |
| E-003 Cadastros | S-006, S-007, S-008 | 19 | 1 |
| E-004 Motor de Cálculo | S-009…S-014 | 47 | 1–2 |
| E-005 Cotação & Equip. | S-015…S-019 | 37 | 2–3 |
| E-006 Custo & Preço | S-020, S-021, S-022 | 24 | 3 |
| E-007 Proposta | S-023, S-024 | 13 | 4 |
| E-008 Aprovação & Audit | S-025, S-026, S-027 | 18 | 4–5 |
| E-009 Dashboard | S-028, S-029 | 10 | 5 |
| **Total** | **29 stories** | **197 SP** | **0–5** |
