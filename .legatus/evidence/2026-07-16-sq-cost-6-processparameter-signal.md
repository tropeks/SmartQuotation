# Evidence — SQ-COST-6 ProcessParameter Review Signal

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-6`
**Branch:** `sdk/sq-cost-6-processparameter-signal-20260716-225253`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Turn SQ-COST-3/4/5 hour variance (`ProductionObservation.delta_horas_pct`) into a
  read-only, per-operation **operational signal** that suggests where a
  `ProcessParameter` (física → horas) may be wrong, WITHOUT auto-changing any
  parameter.
- Aggregate `delta_horas_pct` per `operacao` across closed `ProductionObservation` rows
  (these only exist post-fechamento, via `services._close_out_observations` — SQ-COST-3),
  compute `count` + `mean_abs_delta_pct` (ignoring `None`), and classify each operation
  as `insufficient_data` (< 3 samples) / `review_recommended` (mean |Δ| > 5.00% with
  ≥ 3 samples) / `ok` (otherwise). Reuse `ProductionObservation.TOLERANCIA_HORAS_PCT`
  (SQ-COST-5) as the threshold.
- Expose as a read-only `ProductionObservationManager.review_signal()` (custom manager
  method, no migration) plus a thin `services.production_review_signal()` wrapper
  (matching the literal function name/shape from the mission brief).
- Surface read-only on the OF detail page: a new "Sinal de Revisão — ProcessParameter"
  section listing only `review_recommended` operations that belong to *this* OF's
  routing (the signal itself is aggregated cross-OF; the surface is scoped per-OF to
  avoid dumping an unrelated global report on every page).
- Strict TDD: failing tests first, then minimal implementation.
- PMO review before commit/PR/merge.

## Environment note (infra, not code)

Same Docker/AppArmor issue documented in SQ-COST-3/4/5's evidence persists on this host
(`docker ps` → `permission denied`). **Workaround (test-only, not part of the diff):**
used the host's native `postgresql@17-main` service; created a fresh isolated DB
`smartquotation_sqcost6` (owner `sq`, same credentials as `backend/.env.example`) so as
not to collide with `smartquotation`/`smartquotation_sqcost{3,4,5}` used by
prior/concurrent workers. A dedicated `.venv` was created and
`requirements/development.txt` installed.

Note for future workers: `backend/smartquotation/settings/base.py` reads config via
`django-environ`'s `env(...)`, which only reads `os.environ` — the project never calls
`environ.Env.read_env(...)`, so **`backend/.env` is not actually loaded** by `manage.py`
(confirmed empirically: writing `backend/.env` alone left `settings.DATABASES` on the
`smartquotation` default). The working pattern (matches the `export POSTGRES_...` lines
already documented in this repo's root `CLAUDE.md` "Dev (Docker)" section) is to
`export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_USER=sq POSTGRES_PASSWORD=sq
POSTGRES_DB=smartquotation_sqcost6 FIELD_ENCRYPTION_KEY=<fernet key>` in the shell
before running `manage.py`. `backend/.env` was still written (gitignored — confirmed via
`git check-ignore -v backend/.env`) for documentation/parity with prior sprints' evidence,
but the actual test runs relied on the exported shell variables.

## RED

Added a new test class `ProductionReviewSignalTests` (7 tests) to
`backend/apps/production/tests.py`, following the existing
`HourVarianceUITests`/`HourVarianceToleranceTests` pattern (observations created
directly via `ProductionObservation.objects.create(...)`, not via the real close-out
flow, to exercise aggregation/classification/presentation only — not SQ-COST-3's
computation):

- `test_insufficient_data_com_menos_de_3_observacoes` (2 obs → `insufficient_data`)
- `test_review_recommended_quando_media_abs_acima_de_5pct_com_3_amostras` (3 obs,
  mean |Δ| = 8.00% → `review_recommended`, appears in the flagged subset)
- `test_ok_quando_media_abs_dentro_da_tolerancia_com_3_amostras` (3 obs, mean |Δ| =
  2.00% → `ok`, NOT in the flagged subset)
- `test_deltas_none_sao_ignorados_no_calculo_da_media` (3 real deltas + 2 `None` →
  `count=3`, mean computed only from the 3 real deltas, `None` rows don't count toward
  the sample threshold either)
- `test_service_agrega_por_operacao_corretamente` (two operations aggregated
  independently and correctly in the same call)
- `test_detail_renderiza_secao_de_sinal_para_operacao_flagged_da_propria_of` (uses a
  real `codigo_op` from this OF's copied routing; asserts the new section + operation
  code render on `/ofs/<pk>/`)
- `test_detail_nao_renderiza_secao_quando_nenhuma_operacao_flagged` (regression guard:
  a freshly-converted OF with no observations must not render the new section)

Ran (before any implementation):

```
python3 manage.py test apps.production.tests.ProductionReviewSignalTests -v 2
```

```
Ran 7 tests in 5.169s
FAILED (failures=1, errors=5)
```

6/7 failed/errored as expected: `AttributeError: module 'apps.production.services' has
no attribute 'production_review_signal'` on the 5 tests calling the service directly,
plus `AssertionError` on `test_detail_renderiza_secao_de_sinal_para_operacao_flagged_da_propria_of`
(no "Sinal de Revis" text in the response yet). Only
`test_detail_nao_renderiza_secao_quando_nenhuma_operacao_flagged` passed pre-change, as
intended — it pins down that "no signal, no section" is already true of an unmodified
detail page and must keep being true after the change.

## GREEN

Minimal additive implementation, no changes to `pricing_engine/`,
`services._close_out_observations`, `_update_actual_rate` (Welford), `RateSuggestion`,
`ProcessParameter`, or any stored `ProductionObservation` field (`delta_horas_pct` is
never recalculated/reassigned):

1. `backend/apps/production/models.py`:
   - New `ProductionObservationManager(models.Manager)` with
     `REVIEW_MIN_SAMPLES = 3` and `review_signal()` — the aggregation itself: excludes
     rows with `delta_horas_pct__isnull=True`, groups `abs(delta)` by `operacao` in
     Python, computes `mean_abs_delta_pct` (quantized to 2 decimals) and classifies via
     `ProductionObservation.TOLERANCIA_HORAS_PCT` (SQ-COST-5, reused verbatim — not
     redefined). Also `flagged_for_review()` as a small convenience filter.
   - `ProductionObservation.objects = ProductionObservationManager()` — a **plain
     `models.Manager` subclass that only adds methods** (does not override
     `get_queryset()`'s filtering), so every existing `.filter()/.get()/.create()` call
     across the codebase (production `services.py`, `admin.py`, all prior tests)
     continues to behave identically. Confirmed by the full `apps.production` +
     `apps.quotations` suites staying green (see VERIFY).
   - Three new class constants on `ProductionObservation`:
     `STATUS_REVIEW_INSUFFICIENT/RECOMMENDED/OK = "insufficient_data" /
     "review_recommended" / "ok"`.
   - No new DB field, no migration (confirmed by `makemigrations --check --dry-run`).
2. `backend/apps/production/services.py` — `production_review_signal()`, a thin
   module-level wrapper over `ProductionObservation.objects.review_signal()`, matching
   the exact function name/shape requested in the mission brief. Kept as a service
   function (not only a manager method) because the signal is a cross-OF aggregation,
   not something that hangs off a single `OrdemFabricacao`/`ProductionObservation`
   instance.
3. `backend/apps/production/views.py` (`ordem_detail`) — computes
   `of_operacao_codes` (the set of `codigo_op` in this OF's copied routing) and
   `review_signal_flagged` (the subset of `production_review_signal()` rows that are
   `review_recommended` AND belong to this OF), passed to the template. Added
   `ProductionObservation` to the existing `apps.production.models` import.
4. `backend/apps/production/templates/production/detail.html` — new
   `{% if review_signal_flagged %}` section "Sinal de Revisão — ProcessParameter",
   placed between the existing "Desvios de Horas" and "Plano de Inspeção" sections;
   lists operation code, sample count, and mean absolute deviation. Reuses the
   already-existing `g-section`/`g-table`/`q-badge q-badge--over` Design System G
   classes and the `brl` template filter — **no new CSS was added** (unlike SQ-COST-5,
   this sprint didn't need a new badge variant since `q-badge--over` already
   communicates "needs attention").
5. `backend/apps/production/tests.py` — `ProductionReviewSignalTests` (7 tests, see RED).

Ran:

```
python3 manage.py test apps.production.tests.ProductionReviewSignalTests \
  apps.production.tests.HourVarianceUITests \
  apps.production.tests.HourVarianceToleranceTests \
  apps.production.tests.ProductionObservationAdminTests -v 2
```

```
Ran 24 tests in 20.798s
OK
```

All 7 new SQ-COST-6 tests pass, plus all 17 pre-existing SQ-COST-4/5 tests
(`HourVarianceUITests` + `HourVarianceToleranceTests` + `ProductionObservationAdminTests`)
still pass unchanged.

## VERIFY

| Command | Result |
|---|---|
| `python3 manage.py check` | `System check identified no issues (0 silenced).` |
| `python3 manage.py makemigrations --check --dry-run` | `No changes detected` — only a manager (methods-only, no `get_queryset` override) + class constants + a service function + a view/template addition; no model field changes |
| Targeted SQ-COST-6 tests (`ProductionReviewSignalTests`) | `OK` — 7/7 |
| Targeted SQ-COST-6 + SQ-COST-4/5 regression (`ProductionReviewSignalTests` + `HourVarianceUITests` + `HourVarianceToleranceTests` + `ProductionObservationAdminTests`) | `OK` — 24/24 |
| `python3 manage.py test apps.production -v 1` | `OK` — 92/92 (85 baseline + 7 new) |
| `python3 manage.py test apps.quotations apps.production -v 1` | `OK` — 196/196 (189 baseline + 7 new) |
| `python3 -m tests.validate_feixe_completo` | `GATE OK: delta -2.9% dentro de ±10%, 0 erros.` (unchanged — `pricing_engine` untouched) |
| `python3 -m tests.validate_permutador_completo` | `GATE OK` — BEM Δ+0.00%, BEU Δ+0.00%, OF3683 Δ+0.15% (unchanged) |
| `git diff --check` | clean, no output (exit 0) |
| Strict added-line secret scan (`git diff -- backend \| grep -iE '^\+.*(password\|secret\|token\|api[_-]?key\|BEGIN [A-Z ]*PRIVATE KEY\|AKIA)'`) | 0 hits (exit 1 / no match) — no `force_login` password args or credentials were added in this sprint's tests/code |

## Files changed

- `backend/apps/production/models.py` — `ProductionObservationManager.review_signal()` /
  `.flagged_for_review()` (new custom manager, methods-only — no queryset-filtering
  override, no migration) + `STATUS_REVIEW_INSUFFICIENT/RECOMMENDED/OK` constants on
  `ProductionObservation`.
- `backend/apps/production/services.py` — `production_review_signal()` read-only
  wrapper function.
- `backend/apps/production/views.py` — `ordem_detail` computes and passes
  `review_signal_flagged` (this OF's operations only) to the template; imports
  `ProductionObservation`.
- `backend/apps/production/templates/production/detail.html` — new "Sinal de Revisão —
  ProcessParameter" read-only section (reuses existing CSS classes, no new CSS).
- `backend/apps/production/tests.py` — `ProductionReviewSignalTests` (7 tests), all
  RED→GREEN except the no-flag regression guard (passed both before and after, by
  design, mirroring SQ-COST-5's `test_delta_none_continua_sem_base` pattern).
- `.legatus/evidence/2026-07-16-sq-cost-6-processparameter-signal.md` (this file).

## Design decisions / not implemented (explicitly out of scope this sprint)

- **`count` semantics**: `count` in `review_signal()`'s output is the number of
  observations *with a usable delta* (`delta_horas_pct is not None`) for that
  operation — rows with `None` (fixed-value operations, no `ProcessParameter` hours
  basis) are excluded from both the sample count and the mean, not just the mean. This
  is the most defensible reading of "count of observations" as the denominator behind
  a statistic that is itself undefined without a base — a `None`-only operation has no
  physics signal to review. Documented here since the mission text left it slightly
  ambiguous ("count of observations" vs "ignore None in mean").
- **No median/max-abs-deviation** — the mission listed these as a "nice-to-have"; kept
  the statistic to `count` + `mean_abs_delta_pct` to keep the diff minimal, per
  "presentation/analytics only" and "keep UI changes minimal" constraints. Easy to add
  as extra dict keys later without touching the classification logic.
- **No admin note/inline added** — the mission asked for "a small read-only section on
  the OF detail page ... **and/or** a read-only admin note/inline"; implemented only
  the OF detail page section to keep the diff minimal and avoid recomputing the
  cross-OF aggregation per admin list row (would need request-scoped caching to stay
  cheap in `ProductionObservationAdmin`'s `list_display`). The existing
  `ProductionObservationAdmin`/SQ-COST-4/5 read-only admin surface was **not touched**.
- **OF detail scoping**: the underlying signal (`production_review_signal()`) is
  computed cross-OF (all closed observations for an operation, regardless of which OF
  they came from) — that's the whole point, since a single OF rarely has ≥3 samples of
  the same operation. The *view* then filters to just the operations present in the
  current OF's own routing, so the section only ever shows information relevant to
  what Wellington is looking at, rather than dumping the entire tenant-wide report on
  every OF page. This is a scoping/presentation decision, not a change to the
  aggregation itself.
- **No tenant-configurable threshold** — reused `ProductionObservation.TOLERANCIA_HORAS_PCT`
  (`5.00`, SQ-COST-5's fixed MVP constant) and a new fixed
  `ProductionObservationManager.REVIEW_MIN_SAMPLES = 3`, per the mission's explicit
  "Do NOT add tenant-configurable behavior unless trivial."
- Confirmed **no coupling** to `ProcessParameter`, `Rate`, `ActualRate`, `RateSuggestion`,
  or `pricing_engine` — `production_review_signal()` only reads
  `ProductionObservation.operacao`/`delta_horas_pct`, both already persisted by
  SQ-COST-3's `_close_out_observations` (untouched in this sprint).

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

Additional PMO notes:

- Worker reached `AWAIT_PMO_REVIEW` with coherent artifacts and no commit/push.
- PMO inspected the custom manager (methods-only, no `get_queryset` override), the service wrapper, the view scoping and the template section. The signal is read-only analytics over SQ-COST-3's stored `delta_horas_pct`; it does NOT mutate `ProcessParameter`, `Rate`, `ActualRate`/Welford, `RateSuggestion`, or `pricing_engine`, and does NOT change pricing/quotation totals.
- `count` semantics confirmed: rows with `delta_horas_pct=None` are excluded from both the sample count and the mean (documented design decision; defensible because a `None`-only operation has no hours-physics base to review).
- `python3 manage.py check` passed.
- `python3 manage.py makemigrations --check --dry-run` passed: no changes detected.
- Targeted SQ-COST-6/SQ-COST-4/5 tests passed: 24/24 OK.
- `python3 manage.py test apps.production -v 1` passed: 92/92 OK.
- `python3 manage.py test apps.quotations apps.production -v 1` passed: 196/196 OK.
- Engine gates, `git diff --check`, and strict added-line secret scan passed.

## STATUS

PMO_ACCEPTED
