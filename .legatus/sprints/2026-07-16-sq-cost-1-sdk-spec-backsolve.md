# Sprint Contract — SQ-COST-1: Cost model spec + back-solve contamination audit

**Date:** 2026-07-16
**Backend ordered by Captain:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo:** `/home/rcosta00/dev/SmartQuotation`
**Branch:** `docs/wellington-cost-discovery-20260716-192038`
**Stop condition:** `AWAIT_PMO_REVIEW` before code implementation, migrations, commit or merge.

---

## Captain's order

Use the Claude Agent SDK for these SmartQuotation/Legatus sprints. Legatus remains the source of truth for sprint contracts, evidence, gates and approval; SDK is the worker/session backend.

## Objective

Produce the SQ-COST-1 design/spec artifact and back-solve contamination audit before any model/migration/code implementation.

## Scope

- Inspect existing code/docs around:
  - `apps/cost_discovery`
  - `TenantCostChain`
  - `TenantParamConfig`
  - `Rate`, `ProcessParameter`, `ActualRate`, `RateSuggestion`
  - `Quotation`, `Quotation.avisos`, `fator_preco`, `impostos_pct`
  - production observation flow
- Write a spec document under `docs/specs/`.
- Write or include a back-solve contamination audit section.
- Map every proposed concept to existing fields/models or mark it absent.
- Answer the key domain design choices at spec level:
  - overhead separate vs absorbed in `rate_hh`;
  - versioned `CostStructure` vs extension of existing models;
  - `referencial` vs `validado por custo` provenance implications.

## Non-goals

- No migrations.
- No app code changes.
- No database access required.
- No production/deploy changes.
- No secrets or `.env` reads.
- No implementation of competitive “vitória perigosa”.
- No cost centres in this sprint.

## Expected artifacts

- `docs/specs/sq-cost-1-cost-model-backsolve-audit-2026-07-16.md`
- Updated `.legatus/evidence/2026-07-16-sq-cost-1-sdk-spec-backsolve.md`
- SDK telemetry/logs under `/tmp/sq_cost_1_sdk_*`

## Verification plan

- `git diff --check`
- Assert no Python/migration files changed.
- Grep for `.env`/secret reads in generated telemetry if needed.
- PMO readback of spec and artifact paths.

## Acceptance criteria

- Spec clearly distinguishes price fidelity from margin/cost validation.
- Back-solve contamination risk is concrete and tied to existing code paths.
- New model proposal, if any, is justified as extension plugged into `cost_discovery`, not a rival wizard.
- `overhead_*`/`custo_estrutura_*` naming is used; `custo_fixo` naming collision is documented as forbidden for structural overhead.
- Next sprint(s) can be launched from the spec without re-discovery.
