# Sprint Contract — SQ-COST-3: Decompor horas orçadas vs reais

**Date:** 2026-07-16
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-3`
**Branch:** `sdk/sq-cost-3-hours-decomposition-20260716-203812`
**Base:** `main` after PR #70 (`c6daef3`)

---

## Mission

Implement the first production slice that separates physical/process-hour error from hourly-rate error:

- Add estimated/budgeted hours to production close-out observations.
- Compute/display hour variance (`delta_horas_pct`) so the team can see whether a deviation is caused by ProcessParameter/physical estimate or Rate/R$/h.
- Keep the existing Welford `ActualRate` aggregator behavior intact unless a focused RED test proves a required additive change.

## Doctrine

Legatus remains source of truth. Claude Agent SDK is only the worker backend. Use strict TDD:

1. RED: write focused failing tests first.
2. GREEN: implement minimal model/migration/service/view changes.
3. REFACTOR: clean only after tests pass.

## Scope

Allowed:
- Additive fields/migration for `ProductionObservation` such as `estimated_hh`, `estimated_hm`, `delta_horas_pct` if appropriate.
- Production close-out service changes to snapshot estimated hours from `OFOperation` when observations are created.
- Read-only UI/admin/reporting exposure where natural.
- Tests for estimated hours snapshot, variance computation, zero-hour guard, and no regression to pricing gates.
- Docs/evidence updates.

Forbidden:
- Changing pricing formulas or pricing_engine.
- Implementing CostStructure/overhead.
- Auto-suggesting or auto-changing ProcessParameter in this sprint.
- Refactoring the Welford aggregator unless strictly necessary and covered by tests.
- Reading `.env`/secrets/deploy credentials.
- Production deploy.
- Commit/PR by worker; PMO does that after review.

## Acceptance

- Test proves close-out observation snapshots estimated hours from OFOperation.
- Test proves `delta_horas_pct` distinguishes actual vs estimated hours.
- Test proves `estimated_hh = 0` is handled safely for fixed-value/service operations.
- Existing production/quotation tests pass.
- Engine gates remain unchanged.
- `git diff --check` clean.
- No secrets touched.

## Stop condition

Worker stops at `AWAIT_PMO_REVIEW`.
