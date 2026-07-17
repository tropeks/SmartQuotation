# Sprint Contract — SQ-COST-5: Tolerância/semáforo de desvios de horas

**Date:** 2026-07-16
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-5`
**Branch:** `sdk/sq-cost-5-hours-tolerance-20260716-215842`
**Base:** `main` after PR #72 (`5742b35`)

---

## Mission

Refine SQ-COST-4's hour variance UI so small deviations are not presented as operational alerts.

Implement a simple read-only tolerance band / semaphore for `ProductionObservation.delta_horas_pct`:

- `sem base`: `delta_horas_pct is None`
- `dentro do esperado`: `abs(delta_horas_pct) <= 5.00`
- `acima da tolerância`: `delta_horas_pct > 5.00`
- `abaixo da tolerância`: `delta_horas_pct < -5.00`

Default tolerance: **5%** for this MVP slice. Make it obvious in the UI copy. Do not make it tenant-configurable in this sprint unless the existing code makes it trivial; avoid migrations unless strongly justified.

## Doctrine

- Legatus artifacts are source of truth.
- Claude Agent SDK is the worker backend.
- Strict TDD: write failing tests first, then implementation.
- Worker stops at `AWAIT_PMO_REVIEW` and does not commit/push.

## Scope

Allowed:
- Add a model/helper/property for variance classification if useful.
- Update OF detail labels/classes to use tolerance rather than exact 0-only neutral.
- Update CSS badge naming/colors if needed, preserving existing Design System G style.
- Tests for exact boundary values: -5, 0, +5, +5.01, -5.01 and null.
- Evidence updates.

Forbidden:
- Changing SQ-COST-3 stored computation semantics.
- Changing pricing formulas, quotation totals, Welford/ActualRate, RateSuggestion or ProcessParameter update logic.
- Adding tenant config/migrations/heavy UI unless necessary.
- Reading `.env` or secret/deploy credentials.
- Production deploy.

## Acceptance

- `+0.01%`, `0%`, `+5%`, and `-5%` render as within tolerance, not over/under alert.
- `+5.01%` renders as over tolerance.
- `-5.01%` renders as under tolerance.
- Null delta remains `sem base`.
- Tests fail before implementation and pass after.
- Existing production/quotation tests pass.
- Engine gates unchanged.
- `git diff --check` and strict added-line secret scan clean.

## Verification commands

- `cd backend && python3 manage.py check`
- `cd backend && python3 manage.py makemigrations --check --dry-run`
- targeted SQ-COST-5 tests
- `cd backend && python3 manage.py test apps.production -v 1`
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` if feasible
- `python3 -m tests.validate_feixe_completo`
- `python3 -m tests.validate_permutador_completo`
- `git diff --check`
- strict added-line secret scan

## Stop condition

`AWAIT_PMO_REVIEW`
