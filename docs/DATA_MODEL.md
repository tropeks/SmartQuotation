---
# Contrato de documentação (Maestro E16).
# Entidades persistidas do SmartQuotation (schema public + schema por tenant).
covers:
  - backend/apps/**/models.py
  - backend/apps/**/migrations/**
reviewed: 2026-09-27
---
# DATA_MODEL.md — SmartQuotation

> **Status:** Aprovado, emendado em 2026-09-27 | **Versão:** 1.1 | **Referência:** ARCHITECTURE.md, `.maestro/INTENT.md` v2

---

## 0. Emenda 2026-09-27 — o que existe no código

As seções 1 a 5 abaixo misturam o que existe com o desenho alvo de 2025. Esta tabela é o
mapa medido em `backend/apps/**/models.py`. Onde ela e o resto do doc divergem, vale ela.
Convenção real: PK `BigAutoField` (não UUID), dinheiro em `DecimalField`, sem soft delete.

| App | Entidades reais |
|---|---|
| `tenants` (public) | Plan, Tenant, Domain |
| `accounts` | Role (papel como dado, `requires_crea`, `is_admin_like`), UserProfile (`role` = `Role.key`, CREA, `must_change_password`) |
| `access` | RolePermission (papel × capability), ApprovalWorkflow, ApprovalStage |
| `audit` | TechnicalApproval, ApprovalRequest, ApprovalCase, ApprovalTask, AccessLog |
| `quotations` | Customer, Quotation (+ `pricing_basis` referencial/validado_custo, `avisos`), CalculationSnapshot, QuotationItem, ItemMaterial, ItemOperation, QuotationPart |
| `materials` | Material, MaterialPrice (cifrado, por forma), LigaMetalurgica, MaterialStandard |
| `engineering_params` | Rate (`operacao`, `rate_hh`, `rate_hm`, vigência), ProcessParameter, TenantParamConfig (singleton; ordem 008 acrescenta `fator_preco_completo`/`impostos_pct_completo` — markup/imposto do PERMUTADOR COMPLETO por tenant, mesmas casas de `Quotation.fator_preco`/`.impostos_pct`, default 1,25/9,0), RateSuggestion, KnobChangeProposal |
| `cost_discovery` / `cost_structure` | CostDiscoverySession / CostStructure |
| `tema_templates` | ComponentTemplate, ComponentOperation |
| `proposals` | ProposalTemplate, Proposal (status draft/ready/sent/superseded, `docx_sha256`/`pdf_sha256`), ProposalVersion (envio: `emailed_at`, `emailed_by`, `email_to`) |
| `production` | OrdemFabricacao, OFItem, OFMaterial, OFOperation, ProductionEntry, ProductionObservation, ActualRate, InspectionPlan, InspectionItem |
| `integrations.*` | Nomus: Config, SyncRun, ExportLog · Protheus: Config, SyncBinding, SyncRun, SyncAttempt, CatalogStaging, Supplier, WorkOrderSnapshot, BOMSnapshot · Omie: Config, FiscalDocument, InvoiceRun, InvoiceAttempt · SAP B1: Config, SyncBinding, SyncRun, ExportLog, SyncAttempt · Bling: Config, ExportLog |

**Não existem** (desenho alvo de 2025, sem data): TenantConfig (§3.1), MaterialCategory e
MaterialAllowableStress (§3.3; S admissível vive em `pricing_engine/asme.py`), Equipment e
componentes (§3.5), Operation, Machine, Rate em 3 camadas, CostBreakdown e PriceFormation
(§3.6), BillOfMaterials, BOMItem, ManufacturingRoute e RouteOperation (§3.7; o papel de lista
de material e roteiro é da OF, em `production`). O campo `pvélite_validation_required` de
TenantConfig está fora de escopo pelo INTENT v2.

**Previsto na F1 do Cognitive Core** (não existe ainda):

| Ordem | Entidade prevista | Para quê |
|---|---|---|
| F1-01 | Token delegado (usuário, escopo de capability, expiração, revogação) | Core age como usuário real do tenant |
| F1-03 | Idempotência do envio em `ProposalVersion` (chave única, estado do envio) | Mesma versão `sent` nunca reenvia |
| F1-09 | Cadastro de destinatários por cliente (origem, data de alteração) | Envio só para destinatário cadastrado |
| F1-17 | Responsável do departamento e retrato imutável da habilitação (CREA) no ato da assinatura | Onboarding da F1 |
| F1-32 | Credencial passkey por usuário | Step-up antes de efeito externo |

Ledger de efeitos, conciliação e registry de capabilities (F1-05 a F1-08) vivem na instância
do Core, não neste banco.

---

## 1. Estratégia de Modelagem

### Schema-per-tenant
- **Schema `public`:** tabelas compartilhadas entre todos os tenants (Tenant, Domain, Plan)
- **Schema `tenant_{slug}`:** todas as entidades de negócio isoladas por cliente

### Soft Delete
Contrato alvo H1.5/H2: entidades de negócio usam `deleted_at TIMESTAMP NULL` e purga física
programada após retenção regulatória. H1 atual ainda usa exclusão padrão em parte dos modelos.

### Audit Trail
H1 atual: `CalculationSnapshot`, `TechnicalApproval` e `AccessLog` cobrem a trilha mínima inicial.
Contrato alvo H1.5/H2: `django-simple-history` em entidades de domínio e hardening append-only no banco.

### Versionamento de Cálculo
No H1, cada cotação grava um snapshot persistido da EAP e do roll-up da cotação inteira, com
inputs, versão da função e output. Isso garante reprodução histórica mesmo após bugfix ou
atualização de norma. O modelo Equipment/Component formal fica para H1.5/H2.

---

## 2. Schema `public` — Infraestrutura Multi-tenant

```
Entity: Tenant
  - id: UUID (PK)
  - name: VARCHAR(255) NOT NULL              -- nome da empresa cliente
  - slug: VARCHAR(100) UNIQUE NOT NULL       -- usado como nome do schema Postgres
  - schema_name: VARCHAR(100) UNIQUE NOT NULL
  - plan_id: FK → Plan
  - is_active: BOOLEAN DEFAULT TRUE
  - trial_ends_at: TIMESTAMP NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
  → has_many: Domain
  → has_many: TenantConfig (schema próprio)

Entity: Domain
  - id: BIGSERIAL (PK)
  - tenant_id: FK → Tenant
  - domain: VARCHAR(253) UNIQUE NOT NULL     -- ex: acme.smartquotation.com.br
  - is_primary: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()

Entity: Plan
  - id: UUID (PK)
  - name: VARCHAR(100) NOT NULL              -- Starter, Professional, Enterprise
  - max_users: INTEGER NOT NULL
  - max_quotations_month: INTEGER NULL       -- NULL = ilimitado
  - features: JSONB DEFAULT '{}'            -- feature flags por plano
  - price_brl_monthly: DECIMAL(10,2)
  - is_active: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()
```

---

## 3. Schema `tenant_{slug}` — Entidades de Negócio

### 3.1 Configuração do Tenant

```
Entity: TenantConfig
  - id: UUID (PK)
  - company_name: VARCHAR(255) NOT NULL
  - cnpj: VARCHAR(18) UNIQUE NOT NULL
  - address: TEXT
  - city: VARCHAR(100)
  - state: CHAR(2)
  - logo_path: VARCHAR(500) NULL
  - default_proposal_template_id: FK → ProposalTemplate NULL
  - tax_regime: ENUM('simples','lucro_presumido','lucro_real') DEFAULT 'lucro_presumido'
  - default_currency: CHAR(3) DEFAULT 'BRL'
  - default_margin_pct: DECIMAL(5,2) DEFAULT 20.00
  - pvélite_validation_required: BOOLEAN DEFAULT FALSE  -- gate obrigatório por tenant
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
```

---

### 3.2 Usuários e Autenticação

```
Entity: UserProfile
  - id: UUID (PK)
  - user_id: INTEGER FK → auth.User (Django)  -- FK para o User do Django
  - full_name: VARCHAR(255) NOT NULL
  - role: ENUM('orçamentista','engenheiro','gestor_comercial','pcp','admin') NOT NULL
  - crea_number: VARCHAR(50) NULL              -- obrigatório para role='engenheiro'
  - crea_state: CHAR(2) NULL
  - phone: VARCHAR(20) NULL
  - is_active: BOOLEAN DEFAULT TRUE
  - mfa_required: BOOLEAN DEFAULT FALSE        -- forçado para admin e gestor
  - last_login_at: TIMESTAMP NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
  INDEX: user_id (unique), role

Entity: TechnicalApproval
  - id: UUID (PK)
  - quotation_id: FK → Quotation
  - component_id: FK → EquipmentComponent NULL  -- NULL = aprovação do equipamento inteiro
  - approved_by_id: FK → UserProfile           -- deve ter role='engenheiro'
  - crea_number: VARCHAR(50) NOT NULL           -- snapshot do CREA no momento da aprovação
  - art_number: VARCHAR(100) NULL               -- ART do projeto
  - calculation_snapshot_hash: CHAR(64) NOT NULL  -- SHA-256 do CalculationSnapshot aprovado
  - notes: TEXT NULL
  - approved_at: TIMESTAMP DEFAULT NOW()
  - revoked_at: TIMESTAMP NULL
  - revoked_by_id: FK → UserProfile NULL
  -- H1: revogação lógica por serviço; trigger append-only fica para H1.5
  INDEX: quotation_id, approved_by_id, approved_at
```

---

### 3.3 Materiais

```
Entity: MaterialCategory
  - id: UUID (PK)
  - name: VARCHAR(100) NOT NULL               -- Aço Carbono, Aço Inoxidável, Ligas Especiais
  - parent_id: FK → MaterialCategory NULL     -- hierarquia de categorias
  - sort_order: SMALLINT DEFAULT 0

Entity: Material
  - id: UUID (PK)
  - category_id: FK → MaterialCategory NOT NULL
  - code: VARCHAR(50) UNIQUE NOT NULL         -- ex: SA-516-70, SA-240-316L
  - name: VARCHAR(255) NOT NULL
  - norm: VARCHAR(50) NOT NULL                -- ASME, ASTM, NBR, EN
  - material_group: VARCHAR(50) NULL          -- P-Number ASME (para PWHT)
  - density_kg_m3: DECIMAL(8,3) NOT NULL
  - yield_strength_mpa: DECIMAL(8,2) NOT NULL
  - tensile_strength_mpa: DECIMAL(8,2) NOT NULL
  - allowable_stress_mpa: DECIMAL(8,2) NULL   -- S value ASME — pode variar por temperatura
  - hardness_hb: DECIMAL(6,1) NULL
  - elongation_pct: DECIMAL(5,2) NULL
  - thermal_conductivity_w_mk: DECIMAL(8,3) NULL
  - max_temp_c: DECIMAL(6,1) NULL
  - min_temp_c: DECIMAL(6,1) NULL
  - machinability_index: DECIMAL(5,2) NULL    -- relativo ao AISI 1212 = 100%
  - notes: TEXT NULL
  - is_active: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
  INDEX: code, category_id, norm

Entity: MaterialAllowableStress
  - id: UUID (PK)
  - material_id: FK → Material NOT NULL
  - temp_c: DECIMAL(6,1) NOT NULL             -- temperatura de design
  - allowable_stress_mpa: DECIMAL(8,2) NOT NULL  -- S value nessa temperatura
  - standard_edition: VARCHAR(20) DEFAULT '2021'  -- edição da norma ASME
  UNIQUE: (material_id, temp_c, standard_edition)

Entity: MaterialPrice
  - id: UUID (PK)
  - material_id: FK → Material NOT NULL
  - form: ENUM('chapa','tubo','barra','forjado','fundido') NOT NULL
  - thickness_min_mm: DECIMAL(8,2) NULL       -- faixa de espessura para chapas
  - thickness_max_mm: DECIMAL(8,2) NULL
  - price_brl_kg: DECIMAL(10,4) NOT NULL
  - supplier: VARCHAR(255) NULL
  - valid_from: DATE NOT NULL
  - valid_until: DATE NULL
  - source: ENUM('manual','importado_erp','cotação_fornecedor') DEFAULT 'manual'
  - created_by_id: FK → UserProfile
  - created_at: TIMESTAMP DEFAULT NOW()
  INDEX: material_id, form, valid_from DESC
  -- Preço vigente = registro mais recente com valid_from <= TODAY e valid_until IS NULL ou >= TODAY
```

---

### 3.4 Cotações, EAP e Snapshot (H1 real)

O H1 atual não usa ainda o modelo polimórfico `Equipment/Component`. A espinha persistida é
`Quotation -> QuotationItem -> ItemMaterial/ItemOperation`, que funciona como snapshot de EAP da
cotação. O modelo formal de equipamento fica para H1.5/H2.

```
Entity: Customer
  - id: BIGSERIAL (PK)
  - company_name: VARCHAR(255) NOT NULL
  - cnpj: VARCHAR(18) NULL
  - contact_name: VARCHAR(255) NULL
  - email: VARCHAR(255) NULL
  - city: VARCHAR(100) NULL
  - state: CHAR(2) NULL
  - created_at: TIMESTAMP DEFAULT NOW()
```

```
Entity: Quotation
  - id: BIGSERIAL (PK)
  - number: VARCHAR(50) NOT NULL, db_index    -- COT-{ANO}-{SEQ}; ordem 007: revisão MANTÉM
                                               -- o número e sobe `revision` — a identidade
                                               -- passa a ser o PAR (number, revision), não
                                               -- `number` sozinho (era UNIQUE até a 0009)
  - revision: SMALLINT DEFAULT 0
  - UNIQUE(number, revision)                  -- uniq_quotation_number_revision (migração 0010)
  - customer_id: FK -> Customer NOT NULL
  - title: VARCHAR(500) NOT NULL
  - scope: ENUM(tube_bundle,complete) DEFAULT tube_bundle
  - status: ENUM(draft,in_review,approved,sent,won,lost) DEFAULT draft
  - inputs: JSONB NOT NULL                    -- FeixeInputs ou dados do TEMA
  - fator_preco: DECIMAL(8,5) NOT NULL
  - impostos_pct: DECIMAL(6,3) NOT NULL
  - custo_material: DECIMAL(14,2) NOT NULL
  - custo_mo: DECIMAL(14,2) NOT NULL
  - custo_total: DECIMAL(14,2) NOT NULL
  - preco_sem_impostos: DECIMAL(14,2) NOT NULL
  - preco_com_impostos: DECIMAL(14,2) NOT NULL
  - peso_bruto_kg: DECIMAL(12,2) NOT NULL
  - peso_liquido_kg: DECIMAL(12,2) NOT NULL
  - created_by_id: FK -> auth.User NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
  - computed_at: TIMESTAMP NULL
  -> has_many: QuotationItem
  -> has_many: CalculationSnapshot
```

```
Entity: QuotationItem
  - id: BIGSERIAL (PK)
  - quotation_id: FK -> Quotation NOT NULL
  - codigo_item: VARCHAR(30) NOT NULL
  - descricao: VARCHAR(255) NOT NULL
  - custo_material: DECIMAL(14,2) NOT NULL
  - custo_mo: DECIMAL(14,2) NOT NULL
  - sort_order: SMALLINT DEFAULT 0
  -> has_many: ItemMaterial
  -> has_many: ItemOperation
```

```
Entity: ItemMaterial
  - id: BIGSERIAL (PK)
  - item_id: FK -> QuotationItem NOT NULL
  - codigo_mp: VARCHAR(30) NOT NULL
  - descricao: VARCHAR(255) NOT NULL
  - material: VARCHAR(50) NOT NULL
  - forma: VARCHAR(20) NOT NULL
  - peso_bruto_kg: DECIMAL(12,3) NOT NULL
  - peso_liquido_kg: DECIMAL(12,3) NOT NULL
  - preco_kgf: DECIMAL(10,4) NOT NULL
  - custo: DECIMAL(14,2) NOT NULL
```

```
Entity: ItemOperation
  - id: BIGSERIAL (PK)
  - item_id: FK -> QuotationItem NOT NULL
  - codigo_op: VARCHAR(40) NOT NULL
  - descricao: VARCHAR(255) NOT NULL
  - metodo: VARCHAR(20) NULL
  - custo: DECIMAL(14,2) NOT NULL
  - aplicavel: BOOLEAN DEFAULT TRUE
```

```
Entity: CalculationSnapshot
  - id: BIGSERIAL (PK)
  - quotation_id: FK -> Quotation NOT NULL
  - snapshot_hash: CHAR(64) NOT NULL
  - inputs: JSONB NOT NULL                    -- metadados da cotação + inputs + preço
  - outputs: JSONB NOT NULL                   -- totais, EAP e memorial quando aplicável
  - engine_version: VARCHAR(50) NOT NULL
  - standard_refs: JSONB DEFAULT []           -- normas/fontes extraídas do memorial
  - created_at: TIMESTAMP DEFAULT NOW()
  -- H1: append-only por serviço; hardening por trigger fica para H1.5.
```

### 3.5 Equipamentos — Modelo Polimórfico (alvo, não implementado)

O desenho `Equipment`, `PressureVessel`, `HeatExchanger` e `EquipmentComponent` continua sendo a
direção de evolução para vasos, PVElite amplo, múltiplos equipamentos por cotação e BOM/roteiro
formal. Ele não é pré-condição para o H1 auditável de feixe + BEU/BEM.

### 3.6 Formação de Custo e Preço (alvo 2025, não implementado — ver §0)

```
Entity: Operation
  -- Catálogo de operações produtivas (global por tenant)
  - id: UUID (PK)
  - code: VARCHAR(50) UNIQUE NOT NULL         -- ex: SOLD-MIG, CALAN, JATO, PWHT
  - name: VARCHAR(255) NOT NULL
  - category: ENUM('welding','forming','machining','heat_treatment','ndt','surface','assembly','other') NOT NULL
  - unit: ENUM('hora','metro','kg','m2','un','pct_peso') NOT NULL  -- unidade de medição
  - notes: TEXT NULL
  - is_active: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()

Entity: Machine
  - id: UUID (PK)
  - code: VARCHAR(50) UNIQUE NOT NULL
  - name: VARCHAR(255) NOT NULL               -- Calandra CNC, Puncionadeira, Torno
  - hour_rate_brl: DECIMAL(10,2) NOT NULL     -- custo hora-máquina
  - setup_time_hours: DECIMAL(6,2) DEFAULT 1.00
  - is_active: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP

Entity: Rate
  -- Hierarquia 3 camadas: Industry Standard → Tenant → Actual
  - id: UUID (PK)
  - operation_id: FK → Operation NOT NULL
  - material_id: FK → Material NULL           -- NULL = aplica a qualquer material
  - thickness_min_mm: DECIMAL(8,2) NULL       -- faixa de espessura NULL = qualquer
  - thickness_max_mm: DECIMAL(8,2) NULL
  - layer: ENUM('industry_standard','tenant','actual') NOT NULL
  - value: DECIMAL(12,4) NOT NULL             -- ex: horas/metro de solda
  - unit_denominator: VARCHAR(50) NOT NULL    -- ex: 'h/m', 'h/kg', 'h/m2', 'h/un'
  - confidence_level: DECIMAL(5,2) NULL       -- 0-100, calculado para layer='actual'
  - sample_count: INTEGER NULL                -- N de ordens que geraram este actual rate
  - valid_from: DATE NOT NULL DEFAULT NOW()
  - valid_until: DATE NULL
  - source_of_id: FK → Rate NULL             -- para actual: qual tenant rate gerou
  - created_by_id: FK → UserProfile NOT NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  UNIQUE: (operation_id, material_id, thickness_min_mm, layer, valid_from)
  INDEX: operation_id, layer, valid_from DESC
  -- Lógica de resolução: actual (confidence>70) → tenant → industry_standard

Entity: CostBreakdown
  -- Breakdown de custo por componente da cotação
  - id: UUID (PK)
  - quotation_id: FK → Quotation NOT NULL
  - component_id: FK → EquipmentComponent NULL  -- NULL = custo do equipamento inteiro
  - cost_type: ENUM('material','labor','overhead','external_service','other') NOT NULL
  - operation_id: FK → Operation NULL
  - machine_id: FK → Machine NULL
  - rate_id: FK → Rate NULL                   -- rate utilizado (com layer)
  - quantity: DECIMAL(12,4) NOT NULL          -- ex: metros de solda
  - unit_cost_brl: DECIMAL(12,4) NOT NULL
  - total_cost_brl: DECIMAL(14,2) NOT NULL
  - is_manual_override: BOOLEAN DEFAULT FALSE
  - override_reason: TEXT NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP
  INDEX: quotation_id, cost_type

Entity: PriceFormation
  -- Formação do preço de venda da cotação
  - id: UUID (PK, 1:1 com Quotation)
  - quotation_id: FK → Quotation UNIQUE NOT NULL
  - total_direct_cost_brl: DECIMAL(14,2) NOT NULL
  - overhead_pct: DECIMAL(5,2) NOT NULL
  - overhead_brl: DECIMAL(14,2) NOT NULL
  - total_cost_brl: DECIMAL(14,2) NOT NULL
  - margin_pct: DECIMAL(5,2) NOT NULL
  - margin_brl: DECIMAL(14,2) NOT NULL
  - subtotal_brl: DECIMAL(14,2) NOT NULL
  - tax_config: JSONB NOT NULL                -- snapshot da config fiscal no momento
  - tax_brl: DECIMAL(14,2) NOT NULL
  - total_price_brl: DECIMAL(14,2) NOT NULL
  - price_per_kg_brl: DECIMAL(10,4) NULL      -- benchmarking
  - calculated_at: TIMESTAMP DEFAULT NOW()
  - calculated_by_id: FK → UserProfile NOT NULL
```

---

### 3.7 BOM e Roteiro de Fabricação (alvo 2025, não implementado — ver §0)

```
Entity: BillOfMaterials
  - id: UUID (PK)
  - quotation_id: FK → Quotation NOT NULL
  - equipment_id: FK → Equipment NULL         -- NULL = BOM de toda a cotação
  - status: ENUM('draft','released','superseded') DEFAULT 'draft'
  - released_at: TIMESTAMP NULL
  - released_by_id: FK → UserProfile NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP

Entity: BOMItem
  - id: UUID (PK)
  - bom_id: FK → BillOfMaterials NOT NULL
  - component_id: FK → EquipmentComponent NOT NULL
  - material_id: FK → Material NOT NULL
  - form: ENUM('chapa','tubo','barra','forjado','fundido') NOT NULL
  - quantity: DECIMAL(12,4) NOT NULL
  - unit: ENUM('kg','un','m','m2') NOT NULL
  - gross_weight_kg: DECIMAL(12,3) NULL       -- com sobra/kerf
  - net_weight_kg: DECIMAL(12,3) NULL         -- peso líquido
  - utilization_pct: DECIMAL(5,2) NULL        -- aproveitamento de chapa
  - material_price_id: FK → MaterialPrice NOT NULL  -- snapshot do preço usado
  - total_cost_brl: DECIMAL(14,2) NOT NULL
  - notes: TEXT NULL
  - sort_order: SMALLINT DEFAULT 0
  INDEX: bom_id, material_id

Entity: ManufacturingRoute
  - id: UUID (PK)
  - quotation_id: FK → Quotation NOT NULL
  - equipment_id: FK → Equipment NULL
  - status: ENUM('draft','released','superseded') DEFAULT 'draft'
  - released_at: TIMESTAMP NULL
  - released_by_id: FK → UserProfile NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP

Entity: RouteOperation
  - id: UUID (PK)
  - route_id: FK → ManufacturingRoute NOT NULL
  - component_id: FK → EquipmentComponent NULL
  - operation_id: FK → Operation NOT NULL
  - machine_id: FK → Machine NULL
  - sequence: SMALLINT NOT NULL
  - description: TEXT NULL
  -- Estimativa de tempo
  - rate_id: FK → Rate NOT NULL               -- rate utilizado (com layer)
  - quantity: DECIMAL(12,4) NOT NULL          -- metros de solda, kg, m2, etc.
  - estimated_hours: DECIMAL(8,2) NOT NULL    -- calculado: quantity / rate.value
  - setup_hours: DECIMAL(6,2) DEFAULT 0.00
  - total_hours: DECIMAL(8,2) NOT NULL        -- estimated + setup
  -- Tempo real (H2 — apontamento)
  - actual_hours: DECIMAL(8,2) NULL
  - completed_at: TIMESTAMP NULL
  - completed_by_id: FK → UserProfile NULL
  - notes: TEXT NULL
  INDEX: route_id, sequence
```

---

### 3.8 Propostas Comerciais (desenho 2025; forma real na §0)

```
Entity: ProposalTemplate
  - id: UUID (PK)
  - name: VARCHAR(255) NOT NULL
  - description: TEXT NULL
  - docx_template_path: VARCHAR(500) NOT NULL  -- caminho do template .docx no volume
  - is_default: BOOLEAN DEFAULT FALSE
  - is_active: BOOLEAN DEFAULT TRUE
  - created_at: TIMESTAMP DEFAULT NOW()
  - updated_at: TIMESTAMP

Entity: Proposal
  - id: UUID (PK)
  - quotation_id: FK → Quotation NOT NULL
  - template_id: FK → ProposalTemplate NOT NULL
  - number: VARCHAR(100) NOT NULL             -- ex: PROP-2025-001-A
  - status: ENUM('generating','ready','sent','superseded') DEFAULT 'generating'
  - docx_path: VARCHAR(500) NULL
  - pdf_path: VARCHAR(500) NULL
  - docx_hash: CHAR(64) NULL                 -- SHA-256 do arquivo gerado
  - pdf_hash: CHAR(64) NULL
  - generated_at: TIMESTAMP NULL
  - generated_by_id: FK → UserProfile NOT NULL
  - sent_at: TIMESTAMP NULL
  - sent_by_id: FK → UserProfile NULL
  - sent_to_email: VARCHAR(255) NULL
  - created_at: TIMESTAMP DEFAULT NOW()
  INDEX: quotation_id, status
```

---

### 3.9 Auditoria e Acesso

```
Entity: AccessLog
  -- append-only: registra acesso a dados sensíveis (LGPD / ISO 27001 A.12.4)
  - id: BIGSERIAL (PK)
  - user_id: FK → UserProfile NOT NULL
  - action: ENUM('view','create','update','delete','export','print','approve','revoke') NOT NULL
  - resource_type: VARCHAR(100) NOT NULL      -- ex: 'Quotation', 'Proposal', 'Customer'
  - resource_id: UUID NOT NULL
  - ip_address: INET NOT NULL
  - user_agent: TEXT NULL
  - details: JSONB NULL                       -- contexto adicional
  - created_at: TIMESTAMP DEFAULT NOW()
  -- NUNCA UPDATE ou DELETE durante período de retenção
  INDEX: user_id, resource_type, created_at DESC
  INDEX: resource_type, resource_id, created_at DESC
  PARTITION BY RANGE(created_at)              -- particionar por ano para performance
```

---

## 4. Estratégia de Migrations

1. **Sprint 0:** Schema `public` (Tenant, Domain, Plan) + Schema shared de `accounts` + skeleton de `materials`
2. **Sprint 1:** `equipment`, `quotations` (estrutura base)
3. **Sprint 2:** snapshot de cotação + `bom` + `routing` (estrutura — dados em H2)
4. **Sprint 3:** `pricing`, `proposals`
5. **Sprint 4:** `audit` completo + `technicalapproval`

Toda migration passa por `migrate_schemas --tenant` em staging antes de ir para produção.
Migrations destrutivas (DROP COLUMN) precedidas de 1 sprint de deprecação (campo ignorado, não removido).

---

## 5. Índices e Constraints Adicionais

```sql
-- Performance: cotações por cliente e status
CREATE INDEX idx_quotation_customer_status ON quotation(customer_id, status, created_at DESC);

-- Integridade: aprovação técnica exige CREA preenchido no perfil
ALTER TABLE userprofile ADD CONSTRAINT chk_engineer_crea
  CHECK (role != 'engenheiro' OR crea_number IS NOT NULL);

-- Integridade: modo importado exige documento
ALTER TABLE equipmentcomponent ADD CONSTRAINT chk_imported_has_doc
  CHECK (calculation_mode != 'imported' OR imported_document_hash IS NOT NULL);

-- Auditoria H1.5: AccessLog não pode ser deletado antes de 15 anos
-- Alvo: trigger que rejeita DELETE antes de NOW() - interval '15 years'

-- Rate: hierarquia coerente
ALTER TABLE rate ADD CONSTRAINT chk_actual_has_samples
  CHECK (layer != 'actual' OR sample_count IS NOT NULL);
```

---

## Flags para o orchestrator

Nenhuma.
