# Sprint Contract — SQ-COST-8-UI: Fechamento dos achados de UI (sonda Opus)

**Date:** 2026-07-17
**Backend:** Claude Agent SDK Python
**PMO:** Hermes/Spock
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-8-ui`
**Branch:** `sdk/sq-cost-8-ui-findings-20260717-002300`
**Base:** `main` after PR #75 (`ffe7431`)

---

## Context

Opus UI validation probe (`/tmp/sq_ui_validation_opus_report.md`) approved the two surfaces
(SQ-COST-4/5 hour variance badges, SQ-COST-6/7 ProcessParameter review signal + manual proposal)
with NO blockers, but flagged 5 minor findings. This sprint closes them. None change behavior
of the cost engine; all are UI/perf/copy/test-coverage polish on the OF detail page.

## Findings to close

1. **(média)** `views.py` computes `processparameter_suggestion()` for ALL flagged operations
   then discards those outside the current OF. Filter the suggestion computation to this OF's
   `of_operacao_codes` BEFORE computing (or equivalently, only call it for the operations that
   will be rendered). Avoid ~4 wasted queries per non-rendered flagged operation.
2. **(baixa)** Copy `detail.html` "acima de ±5%" is imprecise — the compared value is already
   absolute. Change to e.g. "acima da tolerância (±5%)" / "abaixo da tolerância (±5%)" so the
   text matches the absolute delta semantics.
3. **(baixa)** `hour_variance_observations` property is evaluated twice (two `{% if %}` blocks).
   Compute once in the view and pass a boolean flag, or accept the duplicate evaluation only if
   it is truly free. Prefer computing once in the view to avoid double DB-free (it iterates a
   relation) work. Keep the change minimal.
4. **(baixa)** Tolerance value is hardcoded in the template copy ("±5%"). This is acceptable for
   the MVP fixed tolerance, but prefer referencing `ProductionObservation.TOLERANCIA_HORAS_PCT`
   in the view and passing it to the template so the copy and the logic cannot drift. Keep the
   displayed string "±5%".
5. **(baixa, coverage)** The "método ambíguo → —" branch in the template (protected by
   `!= None`) has a service test but NO template/UI test. Add a `ProcessParameterSuggestionTests`
   case (or an OF-detail render test) asserting that when an operation's observations disagree on
   `metodo` (or have no resolvable `ProcessParameter`), the rendered table shows `—` for
   ProcessParameter atual/proposto while still showing the factor/means.

## Doctrine

- Legatus artifacts are source of truth.
- Claude Agent SDK is the worker backend.
- Strict TDD: failing tests first, then minimal implementation.
- Worker stops at `AWAIT_PMO_REVIEW` and does not commit/push.

## Scope / guardrails

- Preserve all existing behavior of SQ-COST-3..7 (no change to stored `delta_horas_pct`, no
  auto-apply of `ProcessParameter`, no pricing/engine change).
- The displayed tolerance text stays "±5%" (single source from `TOLERANCIA_HORAS_PCT`).
- Changes limited to `views.py`, `detail.html`, and `tests.py` (and the new contract/evidence).
- No new migrations.
- Do NOT touch the cost engine, `services._close_out_observations`, Welford/`ActualRate`,
  `RateSuggestion`, or `pricing_engine`.

## Acceptance

- Finding 1: suggestion loop scoped to the current OF's operations (verified by test/inspection;
  no wasted cross-OF computation for non-rendered rows).
- Finding 2: copy corrected to absolute-delta phrasing.
- Finding 3: property evaluated once (boolean flag from view) or demonstrably free.
- Finding 4: template copy tolerance sourced from `TOLERANCIA_HORAS_PCT` via view context.
- Finding 5: new UI test asserts `—` for ambiguous-metodo rows, factor/means still shown.
- Tests fail before implementation and pass after.
- Existing production/quotation tests still pass.
- Engine gates unchanged.
- `git diff --check` and strict added-line secret scan clean.

## Verification commands

- `cd backend && python3 manage.py check`
- `cd backend && python3 manage.py makemigrations --check --dry-run`
- targeted SQ-COST-8 + SQ-COST-4/5/6/7 regression tests
- `cd backend && python3 manage.py test apps.production -v 1`
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` if feasible
- `python3 -m tests.validate_feixe_completo`
- `python3 -m tests.validate_permutador_completo`
- `git diff --check`
- strict added-line secret scan

## Stop condition

`AWAIT_PMO_REVIEW`
