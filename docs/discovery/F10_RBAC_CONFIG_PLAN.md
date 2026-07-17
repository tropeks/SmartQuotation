# F10 — Permissões por perfil configuráveis + fluxo de aprovações (plano)

> **Origem:** pedido do Rom (17/07/2026) — permissões totalmente configuráveis por perfil + página de fluxo de aprovações + toggle "orçamentista converte OF".
> **Status:** desenho aterrado no código. Defaults de domínio dependem do Wellington (Q8–Q10 no doc de decisões).

## Estado atual do RBAC (fonte da verdade a migrar)
- Núcleo: `backend/apps/accounts/rbac.py` — `ROLE_GROUPS` (rbac.py:16-22), `ensure_groups()` (25-30), `require_role(*roles, allow_platform_staff=False)` (56-81). **Enforcement = `user_role(user) in tupla_hardcoded`**; os Django Groups NÃO participam do enforcement (vestigiais para autorização).
- Papéis: `viewer, orcamentista, engenheiro, gestor_comercial, admin` (`accounts/models.py:14-25`).

### Capabilities protegidas hoje (catálogo a criar)
| Capability | Onde | Papéis atuais |
|---|---|---|
| `quotation.create` | quotations/views.py:170,202,351,362 (`_ENTRY_ROLES`) | orcamentista, engenheiro, admin |
| `quotation.write` | quotations/views.py (`_WRITE_ROLES`) | orcamentista, engenheiro, gestor_comercial, admin |
| `quotation.read` | quotations/views.py (`_READ_ROLES`, allow_platform_staff) | todos |
| `quotation.price_api` | quotations/api.py:12-33 | orcamentista, engenheiro, gestor_comercial, admin |
| **`of.convert`** | production/views.py:97 (`_OF_CONVERT_ROLES`) | engenheiro, gestor_comercial, admin (**orcamentista FORA** — caso do stakeholder) |
| `of.transition` | production/views.py:110 | engenheiro, admin |
| `itp.manage` | production/views.py:132,152,164 | engenheiro, admin |
| `approval.request_remote`/`presencial` | audit/views.py:25,39 | orcamentista, engenheiro, gestor_comercial, admin |
| `approval.panel_read` | audit/views.py:59 | idem |
| `cost_discovery.write` | cost_discovery/views.py:29,50 | engenheiro, admin |
| `rate.change`/`rate.edit` | engineering_params/views.py:31,32 | subset |
| `proposal.write` | proposals/views.py:30,39,114 | engenheiro, admin |
| `tema_template.write` | tema_templates/views.py:55 | engenheiro, admin |
| `material.read`/`material.write` | materials/views.py:134,141,146,169 | read: todos exceto viewer; write: subset |
| `nomus.reexport` | integrations/nomus/views.py:44 | subset |
| `members.manage` | accounts/views.py:167,175,211,229 | admin |
| `access.manage` (NOVO — editar esta página) | — | admin (default; gestor_comercial = Q9) |

**Flags de UI derivadas (mesma fonte, senão flicker):** `can_create_quotation` (quotations/views.py:145), `can_convert` (quotations/views.py:309 E audit/views.py:69), `can_manage_itp/of` (production/views.py:89-90), `can_edit_prices` (materials/views.py:146).

**⚠️ Gotcha flicker:** `detail.html:78-79` faz `hx-get` a cada 5s para `audit:convertibility_panel`. `can_convert` é montado em quotations/views.py:309 (render) e audit/views.py:69 (poller). Hoje ambos importam `_OF_CONVERT_ROLES` de production.views (fonte única). **A refatoração DEVE manter fonte única** (`user_can(user, "of.convert")` nos dois) senão o botão pisca.

## Fluxo de aprovações existente (parcial)
- `audit/models.py`: `TechnicalApproval` (CREA, :8-52), `ApprovalRequest` (pending/approved/cancelled, :55-88).
- `audit/services.py`: `request_remote_approval`, `approve_presencial`, `approve_quotation`, `revoke_approval`.
- Gate de conversão: `production.services.is_convertible(q)` (exige aprovação técnica; usado em quotations/views.py:308, audit/views.py:67).
- Estados de OF: `OrdemFabricacao.status` + `transition_ordem` (production/views.py:110-129).

## Infra
- `accounts` e `audit` em `TENANT_APPS` (settings/base.py:45-46) → config vive **no schema do tenant**.
- **Sem `CACHES`** configurado (LocMemCache per-process); Redis só p/ Celery. Cache de config = tenant-aware (chave com `connection.schema_name`), invalidável.
- Backfill tenant-aware: `get_tenant_model()` + `schema_context(...)` (padrão em integrations/sap_b1/tasks.py:99-102).

## Design
- **Novo app `apps.access`** (adicionar a TENANT_APPS após accounts).
- **`capabilities.py`**: registry `CAPABILITIES` (fonte da verdade do catálogo, em código) + `ensure_capabilities()` (análogo a ensure_groups). Fail-closed: cap de decorator ausente do catálogo = erro de deploy.
- **`RolePermission`** (model): `role`, `capability` (code), `allowed` (bool), `unique_together=(role,capability)`, `updated_at/by`. **Complementa** Groups (não remove ensure_groups); enforcement passa a ler RolePermission.
- **`ApprovalStage`** (model): `key`, `label`, `order`, `required` (bool), `approver_capability` (code), `is_builtin` (bool — CREA travado). `is_convertible` passa a consultar os stages `required=True`.
- **`enforcement.py`**: `role_can(role, cap)` fail-closed + cache per-schema; `require_capability(cap, allow_platform_staff=False)` (mesma semântica de require_role); `user_can(user, cap)` p/ flags de template (mesma fonte → mata flicker).
- **Compat**: `require_role` NÃO é removido; migração incremental view a view. Seed default = tuplas atuais EXATAS (orcamentista.of.convert=False).
- **UI** (`apps/access/views.py` + templates DS-G, padrão members): grade papel×capability (checkbox Alpine + hx-post parcial), config de ApprovalStage; gating `@require_capability("access.manage")`; guard-rail anti-lockout (não desligar o último access.manage do admin); `log_access("permission_change"/"approval_config_change")`.
- **Backfill**: management command idempotente `seed_access_matrix` (tenant-aware) + data migration retroativa (roda em migrate_schemas) + chamada no `provision_tenant.py`. DEFAULT_MATRIX derivado literal das tuplas.

## Riscos
- Perf: cache per-tenant `access:matrix:{schema}`, invalidar no save. 1 query fria/request.
- Flicker can_convert: `user_can(user,"of.convert")` nos DOIS pontos.
- Fail-closed: cap desconhecida/sem linha → False; startup check que toda cap de decorator existe no catálogo.
- Não quebrar ~235 testes RBAC: manter require_role + símbolos legados (`_OF_CONVERT_ROLES` etc.) exportados; migrar decoradores gradualmente; semear matriz ANTES de trocar decoradores e provar `role_can == user_role in tupla`.

## Tasks (dependência sequencial)
- **T1** app `apps.access` + `capabilities.py` (registry cobrindo todas as caps acima) + `ensure_capabilities()`. DoD: check ok; registry 1:1 com as tuplas; teste do registry.
- **T2** models `RolePermission`/`ApprovalStage` + migrations. DoD: makemigrations/migrate_schemas ok.
- **T3** `enforcement.py` (`role_can`/`require_capability`/`user_can`) + cache. DoD: testes anônimo→login, sem-perm→403, cap desconhecida→False, staff bypass, invalidação de cache.
- **T4** `DEFAULT_MATRIX` + `seed_access_matrix` (idempotente, tenant-aware) + data migration + hook no provision_tenant. DoD: `role_can==user_role in tupla` p/ toda combinação; idempotência; orcamentista.of.convert=False.
- **T5** migrar decoradores/flags → capabilities (mantendo símbolos legados). DoD: suíte RBAC (~235) verde; teste anti-flicker can_convert (render==poller) por papel.
- **T6** UI de config (grade + toggle HTMX + anti-lockout + audit). DoD: admin edita→persiste→role_can reflete; não-admin 403; não remove último access.manage do admin.
- **T7** ApprovalStage no `is_convertible` + UI de estágios (CREA built-in travado). DoD: desligar stage não-builtin remove o gate; CREA não desabilitável; defaults preservam comportamento. **(semântica = Wellington Q10)**
- **T8** endurecimento (startup check cap∈catálogo) + docs (migrar CACHES p/ Redis se multi-node). DoD: teste que falha se `require_capability("x")` referenciar cap fora do registry.

## Precisa do Wellington (defaults de domínio, NÃO a mecânica)
- Q8: default de `orcamentista.of.convert` (mecânica entrega toggle; default fica False até validar).
- Q9: `access.manage` só admin ou também gestor_comercial.
- Q10: estágios de aprovação obrigatórios e quem aprova.
