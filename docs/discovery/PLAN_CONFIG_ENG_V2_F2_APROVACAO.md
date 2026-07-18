# Plano — F2 / Bloco B (lite): aprovação por lote dos knobs sensíveis

> F1 (knobs configuráveis) completo em `bafa0d6`. Hoje qualquer `rate.edit` edita os knobs
> DIRETO (PR #100). F2 põe **dupla validação (SoD)** nos knobs sensíveis: um propõe, outro aprova.
> **Lite** = generaliza o padrão `RateSuggestion` (pending→applied) + SoD simples; **NÃO** generaliza
> o `ApprovalCase` do RBAC V2 (que é acoplado a `Quotation` NOT NULL — refatoração grande, fica p/
> quando houver multi-estágio real).

## 1. O que existe (reusar) e o que falta

| Peça | Onde | Reuso |
|---|---|---|
| `RateSuggestion` pending→accepted, `resolved_by` | `engineering_params/models.py:199` | **padrão**, mas SEM SoD (1 ator aceita). Generalizar + adicionar SoD. |
| SoD escape auditado (sole-qualified) | `audit/approvals.py:135` `_other_qualified_exists`, `:208` `self_approved` | **espelhar a lógica** (não o `ApprovalCase`). |
| `role_can(role, capability)` | `apps/access/enforcement.py` | gate de propor/aprovar. |
| edição direta dos knobs | `engineering_params/views.py:save_knobs` (PR #100) | **ponto de integração** — passa a PROPOR p/ knobs sensíveis. |
| `log_access("param_change", …)` | `audit/services.py:48` | auditoria do apply on-approve. |

## 2. Modelo novo — `KnobChangeProposal` (engineering_params)

Generaliza `RateSuggestion` + SoD. NÃO reusa `ApprovalCase` (sem `Quotation`).

```
status       : pending | applied | rejected            (índice)
payload      : JSONField  = {"perda_por_familia": {before:{}, after:{}}, "setup_frac": {before, after}}
requested_by : FK(User, SET_NULL)                       # propositor
resolved_by  : FK(User, SET_NULL, null)                 # aprovador/rejeitador
created_at / resolved_at
self_approved: bool (default False)                     # escape auditado
```

- `before` capturado no momento da proposta → base da checagem de **staleness** (se o valor vigente
  mudou desde a proposta, o apply recusa/avisa — espelha o `invalidate_stale_cases` do RBAC).
- **Só 1 proposta `pending` por vez** (UniqueConstraint condicional `status='pending'`, igual ao
  RateSuggestion) — evita filas concorrentes e conflito de apply. (Decisão §7.1: por LOTE.)

## 3. Serviço (SoD no core, testável sem HTTP)

```
create_knob_proposal(user, before, after)      → cria pending; recusa se já há pending.
approve_knob_proposal(pk, approver, request)   → SoD + staleness → aplica ao TenantParamConfig
                                                  (mesma coerção do adapter) + log_access + status=applied.
reject_knob_proposal(pk, user)                 → status=rejected (sem mutar cfg).
```

- **SoD**: `approver != requested_by`, salvo se NÃO houver outro usuário ativo qualificado
  (`_other_qualified_exists` espelhado) → `self_approved=True` auditado. Espelha `approvals.py:208`.
- **Staleness**: se `TenantParamConfig` atual ≠ `payload.before` nas chaves da proposta → **recusa**
  com aviso ("a config mudou desde a proposta; refaça"). Não aplica em cima de base movida.
- **Apply atômico** (`transaction.atomic` + `select_for_update` no cfg): grava só as chaves da
  proposta, preserva o resto. `log_access("param_change", cfg, {proposal_id, anterior, novo, self_approved})`.

## 4. Integração com a UI dos knobs (muda o comportamento do PR #100)

- `save_knobs`: hoje aplica direto. Passa a: montar `after` do POST; se o lote toca knob **sensível**
  → `create_knob_proposal(...)` e renderizar "enviado para aprovação" (NÃO muta cfg). Se o lote só
  toca knob livre → aplica direto (comportamento atual).
- **Página de aprovações**: seção/aba "Aprovações de knobs pendentes" com o **diff** (padrão do M6),
  botões Aprovar/Rejeitar gateados, SoD aplicado (o propositor vê "aguardando 2º" em vez de Aprovar,
  salvo sole-qualified). Reusa o markup `.g-table` + HTMX.

## 5. Decisões de produto (com recomendação) — ⚠️ CONFIRMAR ANTES DE CODAR

1. **Quais knobs são "sensíveis"** → **regra, não lista** (§7.2): knob que entra no CÁLCULO. Hoje
   TODOS os knobs da UI (perda, setup) são sensíveis → **todo save vira proposta**. (Os livres —
   baffle_cut, tube_lengths, tema_compat, u_bend — nem estão nessa página.) **Rec.: sim, sempre propor.**
2. **Capability de APROVAR** → duas opções:
   - **(Rec.) Reusar `rate.change`** (a que "aplica sugestão" na calibração) como aprovar, e `rate.edit`
     como propor. Zero surface nova de RBAC (importante: RBAC tem migration bloqueada pela corrupção do
     DB de prod). Separação já existe: GESTOR tem `rate.change` e não `rate.edit` (aprova, não propõe).
   - Criar `knob.approve` dedicada — mais limpo semanticamente, mas mexe em `capabilities.py` +
     `seed_access_matrix` (surface RBAC). **Rec.: reusar `rate.change`; criar dedicada só se o Rom quiser.**
3. **SoD com 1 engenheiro** → **escape auditado** (`self_approved`), igual ao RBAC. Alternativa (bloquear
   sempre) trava tenant de 1 pessoa. **Rec.: escape auditado.**
4. **Staleness** → **recusar** apply sobre base movida (não aplicar silenciosamente). **Rec.: recusar+avisar.**

## 6. Faseamento (2 PRs, como no F1)

- **F2/A (backend)**: model `KnobChangeProposal` + migration + serviço (create/approve/reject com SoD
  + staleness + apply atômico) + testes de serviço (SoD, sole-qualified, staleness, apply/reject).
  Sem tocar a UI. Verde isolado.
- **F2/B (wiring + UI)**: `save_knobs` → proposta p/ sensível; página de aprovações (lista+diff+
  aprovar/rejeitar, gate `rate.change`, SoD na UI); testes de fluxo. Muda o comportamento do PR #100.

## 7. Riscos

- **Comportamento**: F2/B tira a edição direta dos knobs sensíveis — é a intenção (dupla validação),
  mas é mudança visível. Documentar no PR.
- **RBAC/DB de prod**: se optar por capability nova, a migration da access-matrix esbarra na corrupção
  do DB (ver incidente 2026-07-18). Reusar `rate.change` evita isso.
- **`ParamChangeProposal` do spec (§Bloco B)**: o spec chamou de `ParamChangeProposal` e falava em
  target genérico p/ `ApprovalCase`. Aqui é mais enxuto (`KnobChangeProposal` só p/ os knobs do
  `TenantParamConfig`), sem `ApprovalCase` — fiel ao "lite". Renomear se o Rom preferir o nome do spec.
