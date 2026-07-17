# Sprint Contract — SQ-COST-6: Sinal operacional de revisão de ProcessParameter

**Date:** 2026-07-16
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-6`
**Branch:** `sdk/sq-cost-6-processparameter-signal-20260716-225253`
**Base:** `main` after PR #73 (`34eaaa7`)

---

## Mission

Turn SQ-COST-3/4/5 hour variance into a read-only *operational signal* that suggests where a `ProcessParameter` (física → horas) may be wrong — WITHOUT auto-changing any parameter.

The signal must:

- Aggregate per-operation `delta_horas_pct` from closed `ProductionObservation` rows.
- Compute a stable per-operation statistic (e.g. mean / median absolute deviation, or count of out-of-tolerance observations).
- Classify each operation as:
  - `review_recommended` if the aggregated signal is beyond tolerance (e.g. mean `abs(delta) > 5%` and/or enough samples)
  - `ok` otherwise
  - `insufficient_data` when there are too few observations to judge
- Expose this as a read-only model/service API (property or method), not a UI rewrite and not a parameter mutation.
- Provide a small read-only view/section or admin note that lists operations flagged for review, so Wellington can see "where the physics/process is off" before touching rates.

Do NOT:
- Change stored `delta_horas_pct` (SQ-COST-3).
- Change tolerance UI (SQ-COST-5) semantics beyond optionally reusing `ProductionObservation.TOLERANCIA_HORAS_PCT`.
- Auto-update `ProcessParameter`, `Rate`, `ActualRate`/`Welford`, `RateSuggestion`, or anything in `pricing_engine`.
- Change pricing/quotation totals.
- Add tenant config/migrations unless strongly justified (prefer additive read-only computed values; a new read-only model or property is acceptable only if it does not require migration — otherwise propose migration in evidence and keep it minimal).

## Doctrine

- Legatus artifacts are source of truth.
- Claude Agent SDK is the worker backend.
- Strict TDD: failing tests first, then minimal implementation.
- Worker stops at `AWAIT_PMO_REVIEW` and does not commit/push.

## Acceptance

- A service/property aggregates `ProductionObservation.delta_horas_pct` per operation.
- `insufficient_data` when sample count < a clear threshold (e.g. < 3 observations).
- `review_recommended` when aggregated absolute deviation exceeds tolerance with enough samples.
- `ok` otherwise.
- At least one read-only surface (admin note, detail section, or small page) lists flagged operations.
- Tests fail before implementation and pass after.
- Existing production/quotation tests pass.
- Engine gates unchanged.
- `git diff --check` and strict added-line secret scan clean.

## Verification commands

- `cd backend && python3 manage.py check`
- `cd backend && python3 manage.py makemigrations --check --dry-run`
- targeted SQ-COST-6 tests
- `cd backend && python3 manage.py test apps.production -v 1`
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` if feasible
- `python3 -m tests.validate_feixe_completo`
- `python3 -m tests.validate_permutador_completo`
- `git diff --check`
- strict added-line secret scan

## Stop condition

`AWAIT_PMO_REVIEW`
