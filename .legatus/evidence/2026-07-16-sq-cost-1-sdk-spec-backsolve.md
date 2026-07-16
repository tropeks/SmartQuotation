# Evidence — SQ-COST-1 SDK Spec + Back-solve Audit

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python (`/home/rcosta00/.venvs/claude-agent-sdk`)
**Wrapper:** `claude-agent-sdk-python`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Record Captain's order: use Claude Agent SDK for these sprints.
- Keep Legatus as source of truth; use SDK as SessionHarness/backend.
- Launch SDK worker for SQ-COST-1 spec + back-solve contamination audit.
- Verify generated artifacts independently.

## RED

Not applicable: documentation/spec sprint. Future implementation sprints must start with RED tests.

## GREEN

SDK worker read the discovery doc, the Opus probe, the sprint contract, and the following source files
end-to-end before writing anything: `pricing_engine/rates.py`, `pricing_engine/wbs.py`,
`apps/cost_discovery/{models,services}.py`, `apps/quotations/{models,adapter}.py`,
`apps/production/{models,services}.py`, `apps/engineering_params/{models,services}.py`,
`apps/audit/services.py` (log_access) and `apps/quotations/validators.py` (avisos schema).

Wrote `docs/specs/sq-cost-1-cost-model-backsolve-audit-2026-07-16.md` (12 sections per contract):
1. Executive recommendation — three findings (no overhead concept; back-solve contamination is live;
   hours already flow end-to-end).
2. Concept map — every Wellington concept mapped to an existing field/model or marked `AUSENTE`
   (fixed cost, productive capacity, cost/hour rateio, contribution margin, minimum price, pricing
   provenance, hours-variance comparison are all confirmed absent).
3. Back-solve contamination audit — exact call chain
   `back_solve → _price_at → build_chain_from_db → quote_feixe` and `run_back_solve → _apply_fator_mo →
   TenantParamConfig.get_solo()` (singleton, unversioned); precise statement of what `error_pct` does and
   does not measure (bisection convergence to a historical price, NOT margin/cost coverage).
4. Proposed extension — new `CostStructure` model (versioned, `valid_from/valid_until` like `Rate`/
   `MaterialPrice`), plugged into `apps.cost_discovery` (not a rival wizard); overhead as a separate
   `overhead_hora` field on `TenantCostChain`, default 0.0, never absorbed into `rate_hh` (rationale tied
   to protecting the already-audited `ActualRate`/`RateSuggestion` Welford loop).
5. Price provenance model — `Quotation.pricing_basis` derived (never hand-set), backfill rule (existing
   quotations → `referencial`), migration strategy at design level.
6. Hours decomposition — exact conflation site `production/services.py:317-325`
   (`observed_rate = custo_orçado / horas_reais`), contract for `ProductionObservation.estimated_hh` +
   `delta_horas_pct` for SQ-COST-3, explicit guardrail not to touch the Welford aggregator.
7. Naming constraint — `wbs.py:47` `OperacaoExecutada.custo_fixo` documented as a false friend (fixed-value
   *service*, not overhead); `overhead_*`/`custo_estrutura_*` mandated for any engine-facing field.
8. Non-goals — no cost centres, no competitive analytics, advisory-only price alerts via existing
   `Quotation.avisos` channel, no calculated-value changes this sprint.
9. Next sprint contracts — SQ-COST-2 (provenance) and SQ-COST-3 (hours decomposition) scoped in enough
   detail to start without re-discovery.
10. Acceptance criteria + evidence checklist.
11. Open questions for Wellington/Romulo (fixed cost value, productive hours, global vs cost-centre
    confirmation, existing back-solve sessions inventory, advisory-only confirmation, overhead-separate
    sign-off).
12. Ends with `AWAIT_PMO_REVIEW`.

## VERIFY

- `git diff --check` → clean (no whitespace errors).
- `git status --short` → only the two expected new/modified files:
  - `docs/specs/sq-cost-1-cost-model-backsolve-audit-2026-07-16.md` (new)
  - `.legatus/evidence/2026-07-16-sq-cost-1-sdk-spec-backsolve.md` (modified)
- No `.py` or migration files appear in `git diff --stat` — confirmed via targeted diff check (docs/specs
  and .legatus paths only).
- No `.env`, secrets, deployment credentials, or tunnel configs were read during this sprint.

## ARTIFACTS

- Sprint contract: `.legatus/sprints/2026-07-16-sq-cost-1-sdk-spec-backsolve.md`
- Spec artifact (produced): `docs/specs/sq-cost-1-cost-model-backsolve-audit-2026-07-16.md`
- This evidence file: `.legatus/evidence/2026-07-16-sq-cost-1-sdk-spec-backsolve.md`

## PMO REVIEW

Hermes/Spock reviewed the SDK worker output after process `proc_fdee2b8401a3` completed with exit code 0.

Accepted decisions:
- SQ-COST-1 remains a design/spec sprint; no app code or migrations were changed.
- `CostStructure` is approved as a future versioned tenant-scoped extension inside `apps.cost_discovery`, not a rival wizard.
- Price provenance should distinguish `referencial` from `validado_custo`; existing/back-solved quotations default to `referencial`.
- Structural overhead must remain a separate future line (`overhead_*`/`custo_estrutura_*`) and must not be absorbed into `rate_hh`.
- Engine-facing overhead must not be named `custo_fixo` because `pricing_engine.wbs.OperacaoExecutada.custo_fixo` already means fixed-value service.
- Competitive “vitória perigosa” analytics stays deferred until cost validation is trustworthy.

Independent verification:
- Spec artifact exists and ends with `AWAIT_PMO_REVIEW`.
- `git diff --check` is clean.
- No `.py` or migration files were changed.

## STATUS

PMO_APPROVED_FOR_COMMIT
