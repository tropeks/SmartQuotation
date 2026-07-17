# Sprint Contract — SQ-COST-4: Superfície visual/admin para desvios de horas

**Date:** 2026-07-16
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-4`
**Branch:** `sdk/sq-cost-4-hours-variance-ui-20260716-212023`
**Base:** `main` after PR #71 (`732bb9b`)

---

## Mission

Expose SQ-COST-3's stored budgeted-vs-actual hour variance to operators/Wellington in a low-risk read-only surface.

Implement a first visual/admin slice that helps answer:

> Which production operations deviated most from the quoted/estimated hours?

## Doctrine

- Legatus artifacts are source of truth.
- Claude Agent SDK is the worker backend.
- Strict TDD: write failing tests first, then implementation.
- Worker stops at `AWAIT_PMO_REVIEW` and does not commit/push.

## Scope

Allowed:
- Read-only display of `estimated_hh`, `actual_hh`, and `delta_horas_pct` on production OF detail, preferably near the per-operation/apontamento section.
- Visual badge/class for over/under/on-target deviations using existing Design System G style conventions.
- Admin read-only exposure/filter/search for `ProductionObservation` if admin surface already exists or is cheap/safe to add.
- Query/helper ordering observations by absolute variance to highlight biggest deviations.
- Tests for rendered labels/values and zero/null delta handling.
- Legatus evidence updates.

Forbidden:
- Changing SQ-COST-3 computation semantics.
- Changing pricing formulas, quotation totals, Welford/ActualRate, RateSuggestion or ProcessParameter update logic.
- Adding charts/heavy JS/new dependencies.
- Reading `.env` or secret/deploy credentials.
- Production deploy.

## Acceptance

- Production OF detail exposes a read-only variance section/list when observations exist.
- Biggest deviations are easy to see/sorted by absolute `delta_horas_pct` when feasible.
- Null delta from zero estimated hours is displayed safely (not crash, not misleading percent).
- Admin/read-only surface included if natural.
- Tests fail before implementation and pass after.
- Existing production/quotation tests pass.
- Engine gates unchanged.
- `git diff --check` clean and added-line secret scan clean.

## Verification commands

- `cd backend && python3 manage.py check`
- `cd backend && python3 manage.py makemigrations --check --dry-run`
- targeted tests added for SQ-COST-4
- `cd backend && python3 manage.py test apps.production -v 1`
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` if feasible
- `python3 -m tests.validate_feixe_completo`
- `python3 -m tests.validate_permutador_completo`
- `git diff --check`
- added-line secret scan

## Stop condition

`AWAIT_PMO_REVIEW`
