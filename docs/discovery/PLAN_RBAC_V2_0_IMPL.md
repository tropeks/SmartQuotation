# Plano de Implementação — RBAC & Aprovações V2.0

> Deriva de `SPEC_RBAC_APROVACOES_V2.md` (Fable 5). Escopo = **V2.0** ("o mínimo que
> destrava venda multi-empresa"). V2.1/V2.2 fora deste plano.
>
> **Invariante-mestre (critério de pronto):** um tenant novo, sem tocar em nada, se
> comporta **exatamente** como o F10 de hoje (5 papéis, gate técnico CREA único). Cada
> milestone abaixo é mergeável isoladamente com CI 100% verde; nenhum quebra tenant existente.

## Baseline F10 (o que já existe — não reescrever)

| Peça | Arquivo | Papel |
|---|---|---|
| Registry de capabilities | `access/capabilities.py` → `CAPABILITIES` | catálogo fail-closed (o que PODE existir) |
| Matriz default | `access/matrix.py` → `DEFAULT_MATRIX` (assert == CAPABILITIES) | seed papel×capability |
| Config por tenant | `access/models.py` → `RolePermission` (role=CharField enum), `ApprovalStage` | quem pode / estágios |
| Enforcement + cache | `access/enforcement.py` (`role_can`, `user_can`), `matrix.py` (cache por schema) | resolução + LocMem cache |
| Role do usuário | `accounts/models.py` → `UserProfile.role` (CharField enum) + `rbac.user_role()` | fonte da role (string) |
| Gate técnico | `audit/models.py` `TechnicalApproval`, `audit/services.py` (e-mail), `production.is_convertible` | CREA hoje |

---

## M0 — Fundação: capabilities novas + cache invalidation (baixo risco, sem UI)

Puramente aditivo. Não muda comportamento de nenhum tenant.

1. Adicionar ao registry `CAPABILITIES` (com `category="aprovacao"`, `is_dangerous` onde couber):
   `approval.technical_sign`, `approval.commercial_sign`, `approval.quality_sign`,
   `approval.custom_sign_1..3`, `role.manage`.
2. Estender `DEFAULT_MATRIX`: `technical_sign` só para `engenheiro`; `role.manage` só para `admin`;
   demais `*_sign` conforme seed dos templates (commercial→gestor_comercial). Manter o
   `assert set(DEFAULT_MATRIX)==set(CAPABILITIES)` verde.
3. `technical_sign` **não** substitui o gate CREA ainda — só entra no registry. Nenhum
   `require_capability("approval.technical_sign")` no código ainda (senão o gate duplica).
4. Testes: `tests_registry_integrity` já cobre "capability referenciada ∈ registry"; adicionar
   teste de que os 6 codes novos existem e estão no DEFAULT_MATRIX.

**Pronto quando:** CI verde, nenhum diff de comportamento; matriz do `/config/` mostra as
linhas novas (ainda sem uso — aceitável, catálogo pode ter capability sem enforcement).

---

## M1 — Roles como dado + trait `requires_crea` (resolve #86) — **pré-requisito de tudo**

O passo mais delicado: enum→FK **sem** quebrar os ~235 testes nem o cache. Estratégia em
duas migrações, contrato de `user_role()`/`role_can()` **inalterado**.

### Modelo
`access/models.py` (ou novo `apps/roles/`) — `Role` (por tenant):
- `key` (slug, unique), `name`, `description`
- traits: `requires_crea` (bool), `is_admin_like` (bool)
- proveniência: `is_seeded` (bool), `source_template` (char, blank), `template_version` (int, null)
- `RolePermission.role`: CharField → **FK(Role, to_field="key", db_column="role")**.

### Truque da migração (o coração do plano)
1. **Migração A (schema+data):** cria tabela `Role`; data migration cria as 5 roles com
   `key` idêntica ao enum (`viewer`, `orcamentista`, `engenheiro`, `gestor_comercial`, `admin`),
   `is_seeded=True`, `requires_crea=True` só em `engenheiro`, `is_admin_like=True` só em `admin`.
2. **Migração B (AlterField):** `UserProfile.role` CharField → `FK(Role, to_field="key",
   db_column="role")`. Como `to_field="key"` e a coluna já guarda a string da key, **os dados
   não migram** — só ganha constraint de FK. `profile.role_id` continua sendo a string key →
   `rbac.user_role()` retorna `profile.role_id` **sem mudar assinatura**. `role_can(key, cap)`,
   a matriz e o cache **não mudam** (continuam indexados por string key).
3. Idem `RolePermission.role` → FK(Role, to_field="key", db_column="role").
4. `provision_tenant` + `seed_access_matrix` passam a criar as 5 `Role` antes da matriz.

### Migrar os acoplamentos de string→trait (inventário da spec §3.1.3, confirmar por grep)
- `accounts/models.py` CheckConstraint `engenheiro_requires_crea` + `clean()`:
  `role=="engenheiro"` → `self.role.requires_crea`. A CheckConstraint de banco (hard-coded)
  **sai** (não referencia trait de FK cross-table de forma limpa); vira validação de aplicação
  em `clean()` + invariante no `Role` (bloquear salvar role com `technical_sign` e
  `requires_crea=False`). **← resolve o bug latente da issue #86.**
- `audit/models.py` `TechnicalApproval.clean` → checar `approver.role.requires_crea` +
  capability, não a string.
- `audit/services.py:79` (destinatários do e-mail hard-coded) → adiar o alvo para M4 (capability
  do estágio corrente); em M1 só trocar `role=="engenheiro"` por trait pra não regredir.
- Grep obrigatório antes de fechar: `ROLE_ENGENHEIRO|ROLE_GESTOR|user_role\(|role *== *["']`.

### Testes
- Os ~235 testes existentes devem passar **sem alteração** (mesmas keys). Se algum quebrar, a
  migração B está errada (provavelmente esqueceu `to_field`/`db_column`).
- Novos: criar role custom, atribuir a usuário, `role_can` resolve; invariante requires_crea×
  technical_sign; #86 — remover CREA-coupling não deixa nada hard-coded (teste de regressão).

**Pronto quando:** CI verde com testes intactos; issue #86 fechável.

---

## M2 — Página "Papéis" + 5 templates de role (gate `role.manage`)

UI sobre M1. Templates = **cópia** no momento da criação (nunca link vivo).

1. `RoleTemplate` como **código** (não tabela): 5 templates cujo conteúdo = recorte do
   `DEFAULT_MATRIX` atual ("Orçamentista", "Engenheiro"[requires_crea], "Gestor Comercial",
   "Somente leitura", "Administrador"). Versionados (`template_version`).
2. Página `/config/roles/` (gate `role.manage`):
   - Lista: nome, nº usuários, origem (template vN / do zero), traits.
   - "Novo papel": passo 1 template|branco → passo 2 nome/descrição → passo 3 grade de
     capabilities (a mesma do F10, pré-marcada pelo template, editável checkbox-a-checkbox).
     Grava `source_template`+`template_version`.
   - Editar: reusa a grade; `/config/` atual vira "matriz completa" com **colunas dinâmicas =
     roles do tenant**.
   - Excluir: bloqueado se houver usuário ativo → exige reatribuição em massa (dropdown "mover
     N usuários para…"); audita `role_change` (já existe no `AccessLog`).
3. Guard-rails: limite de roles/tenant (**15**, config por plano — decisão aberta #2 do Rom);
   anti-lockout generalizado (G8: não deixar remover a última role com `access.manage`/`role.manage`);
   `is_dangerous` marca capabilities sensíveis; **sem hierarquia/herança** (roles planas).
4. Invariante compliance: remover `requires_crea` de role que tem `technical_sign` ligado → bloqueado.

**Pronto quando:** admin cria/edita/exclui role custom pela UI; tenant intocado segue com as 5.

---

## M3 — Builder de fluxos + M4 execução (case/task) — o núcleo de aprovações

Pode ser 1 PR grande ou dividir builder (config) de execução (runtime). Recomendo **dois PRs**.

### M3 — Builder (config) sobre `ApprovalStage`
- `ApprovalWorkflow` (por tenant): `action_type="of.convert"` (único na V2.0), `is_active`.
  `ApprovalStage` ganha FK `workflow`.
- `WorkflowTemplate` (código): "Só técnica (CREA)" [default = comportamento atual], "Técnica +
  Comercial", "Técnica + Comercial + Qualidade", "Do zero".
- Página "Fluxo de aprovações" (evolui a seção de estágios do `/config/`): editor de lista
  ordenada (drag→`order`); por estágio label, role(s) aprovadora(s) [dropdown de roles → liga
  `approver_capability` por baixo, **Nota A**], obrigatório. Estágio técnico **travado**
  (`is_builtin`). Estágio custom consome slot `approval.custom_sign_N`.
- Nota A: UI escolhe role; por baixo grava `approver_capability` e liga essa capability à role
  na matriz. Fonte única da verdade continua a matriz. G8: avisar se estágio fica insatisfazível
  (nenhuma role com a capability).

### M4 — Execução (runtime — alimenta o inbox)
- `ApprovalCase` (1 por cotação×workflow disparado): `target`(cotação), `workflow_snapshot`(JSON
  congelado — filosofia snapshot do produto, **Nota B**), `status`, `snapshot_hash`.
- `ApprovalTask` (1 por estágio): `stage_key`, `status` pending|approved|rejected|skipped|invalidated,
  `decided_by`, `decided_at`, `reason` (obrigatório em rejeição); link p/ `TechnicalApproval` quando técnico.
- Semântica V2.0 (deliberadamente simples — SAP "níveis sequenciais"):
  - Estágios sequenciais por `order`; corrente = 1º `required` não aprovado.
  - Estágio satisfeito por **UMA** aprovação de qualquer usuário qualificado (sem quorum).
  - **Rejeição** (G2): motivo obrigatório → case `rejected`, cotação volta editável, nova
    solicitação = case novo (histórico preservado).
  - **Invalidação por edição**: case guarda `snapshot_hash` (mesmo mecanismo do
    `TechnicalApproval.calculation_snapshot_hash`); recompute/edição → case `invalidated`
    (estágios aprovados NÃO migram; auditoria mantém tudo).
  - **SoD** (G3): flag por tenant "solicitante não aprova a própria" default **on**; escape
    auditado (`metadata.self_approved=true`) só quando NENHUM outro usuário é qualificado.
- `production.is_convertible` passa a perguntar "case ativo desta cotação está `completed`?"
  (mantém fonte-única front/back, anti-flicker do F10).

**Pronto quando:** tenant monta "Diretor Comercial aprova depois do engenheiro" em <5 min e o
fluxo executa; técnico built-in preserva 100% o comportamento CREA atual.

---

## M5 — Inbox "Aprovações" + badge + e-mail corrigido (G4)

- Menu "Aprovações" (nome = decisão aberta #1 do Rom) com badge numérico; 0 pendências = sem badge.
- Página (evolui `approval.panel_read`), 2 abas:
  1. **A aprovar** — tarefas do estágio corrente que MEU role decide. Card: cotação (nº, título,
     cliente, valor), estágio, solicitante, quando, snapshot ok/desatualizado. Ações inline:
     Aprovar (técnico → fluxo CREA/senha/ART atual; demais → confirmação simples), Rejeitar (motivo).
  2. **Minhas solicitações** — cases que eu abri, com stepper de progresso e motivo se rejeitado.
- Badge performance (G15): sem escopo por objeto, a fila é idêntica por role → **1 count por
  (schema, role)**, cache `access:inbox:{schema}:{role}`, invalidado nos eventos do case. Poller
  HTMX reusa o padrão do painel de convertibilidade (5 s). LocMem ok single-node; multi-node→Redis.
- E-mail: `request_remote_approval` mira **quem tem a capability do estágio corrente** (corrige o
  hard-code de `audit/services.py:79` — **G4**), fechando o item deixado em M1.

**Pronto quando:** badge aparece só para quem pode agir; e-mail vai ao alvo certo.

---

## M6 — Auditoria com diff + empty-states (G14/G16) — polish

- Diff em `AccessLog` para saves de `Role` e `ApprovalWorkflow` (o que mudou, antes→depois).
  Invalidar cache de matriz **também** nos saves de `Role`.
- Empty-states de onboarding nas páginas novas (Papéis/Fluxo/Inbox) — reduz suporte.

---

## Ordem, riscos e gates

**Ordem obrigatória:** M0 → M1 → (M2 ∥ M3) → M4 → M5 → M6. M1 destrava tudo; M2 e M3 são
paralelizáveis após M1; M4 depende de M3; M5 depende de M4.

| Risco | Mitigação |
|---|---|
| Migração enum→FK quebra 235 testes | `to_field="key"` + `db_column="role"` → dados não migram, contrato de `user_role()`/cache intacto. Rodar a suíte RBAC como gate de M1. |
| CheckConstraint `engenheiro_requires_crea` não referencia trait cross-table | mover p/ validação de aplicação (`clean`) + invariante no `Role`; documentar no #86. |
| Registry estático vs slots custom | 3 slots custom cobrem P95 (SAP≤8 níveis); registry dinâmico é V2.2 (G6) — não fazer agora. |
| Cache de badge stale | invalidar em criar/aprovar/rejeitar/invalidar case; TTL curto de segurança. |
| Escopo inflar p/ V2.1 | condição-por-valor, quorum, delegação, SLA, outros action_types = **fora** deste plano. |

**Decisões abertas do Rom (não bloqueiam início):** (1) nome do menu "Aprovações"; (2) teto de
15 roles/tenant; (3) conforto com o escape de SoD auto-aprovado auditado.

**Estimativa de esforço (grosseira):** M0 P · M1 GG (migração é o custo) · M2 M · M3 M · M4 GG ·
M5 M · M6 P. Caminho crítico M1→M4.
