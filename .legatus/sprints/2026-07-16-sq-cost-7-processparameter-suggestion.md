# Sprint Contract — SQ-COST-7: Sugestão de novo ProcessParameter (proposição)

**Date:** 2026-07-16
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-7`
**Branch:** `sdk/sq-cost-7-processparameter-suggestion-20260716-232557`
**Base:** `main` after PR #74 (`46a3db9`)

---

## Mission

Build on SQ-COST-6: when an operation is flagged `review_recommended`, compute a *proposed* new
`ProcessParameter` value (física → horas) that would reduce the observed hour variance — but
present it as a suggestion only. The engineer must approve it manually. Nothing is auto-applied.

The suggestion logic (keep it simple and defensible):

- For a flagged operation, use the closed `ProductionObservation` rows:
  - `mean_actual_hh` = mean of `actual_hh`
  - `mean_estimated_hh` = mean of `estimated_hh`
- A reasonable *proposed* physical parameter scales the current estimate toward actual:
  - `proposed_factor = mean_actual_hh / mean_estimated_hh` (guard divide-by-zero; if
    `mean_estimated_hh == 0`, no suggestion)
  - `proposed_value = current_process_parameter_value * proposed_factor` (only as a
    suggestion; do NOT write it back)
- Output a read-only dict per flagged operation:
  `{"operacao", "current_value", "proposed_value", "factor", "mean_actual_hh", "mean_estimated_hh"}`

Do NOT:
- Change stored `delta_horas_pct` (SQ-COST-3).
- Auto-update `ProcessParameter`, `Rate`, `ActualRate`/`Welford`, `RateSuggestion`, or
  `pricing_engine`.
- Change pricing/quotation totals.
- Require a migration unless strongly justified (prefer additive read-only computed values).
- Apply the suggestion anywhere; this is analytics + a UI proposal surface only.

## Scope of the existing ProcessParameter link

Before computing, the worker MUST understand how `ProcessParameter` is keyed (operation ×
machine? operation only? what field is the "physical → horas" value?). Read
`backend/apps/engineering_params/models.py` and any usage in `services.py`/adapter. The
suggestion should reference the *current* `ProcessParameter` value for the operation if a
reliable key exists; if the relationship is ambiguous or not safely joinable from
`ProductionObservation`, the worker should:
- still compute the factor/proposed_value generically, and
- document in evidence exactly which `ProcessParameter` row (if any) the suggestion maps to,
  or state clearly that the mapping is left to the engineer (proposal only).

Do not invent a fake ProcessParameter join. Read the code first.

## Doctrine

- Legatus artifacts are source of truth.
- Claude Agent SDK is the worker backend.
- Strict TDD: failing tests first, then minimal implementation.
- Worker stops at `AWAIT_PMO_REVIEW` and does not commit/push.

## Acceptance

- A service/function computes, for flagged operations, a proposed `ProcessParameter` value.
- Divide-by-zero guarded; `estimated_hh == 0` => no suggestion (or `None` proposed value).
- Proposed value is NOT written to any `ProcessParameter` row.
- A read-only UI surface (detail section or similar) shows the suggestion next to the
  review signal, clearly labeled as a manual proposal.
- Tests fail before implementation and pass after.
- Existing production/quotation tests pass.
- Engine gates unchanged.
- `git diff --check` and strict added-line secret scan clean.

## Verification commands

- `cd backend && python3 manage.py check`
- `cd backend && python3 manage.py makemigrations --check --dry-run`
- targeted SQ-COST-7 tests
- `cd backend && python3 manage.py test apps.production -v 1`
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` if feasible
- `python3 -m tests.validate_feixe_completo`
- `python3 -m tests.validate_permutador_completo`
- `git diff --check`
- strict added-line secret scan

## Stop condition

`AWAIT_PMO_REVIEW`
