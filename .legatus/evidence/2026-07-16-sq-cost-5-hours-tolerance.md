# Evidence — SQ-COST-5 Hours Variance Tolerance

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-5`
**Branch:** `sdk/sq-cost-5-hours-tolerance-20260716-215842`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Add a read-only ±5% tolerance/semaphore layer on top of SQ-COST-4's hour variance UI
  (`ProductionObservation.delta_horas_pct`), so small deviations stop presenting as
  operational alerts.
- Preserve computation/rate/pricing behavior — no changes to `pricing_engine`,
  `services._close_out_observations`, `_update_actual_rate` (Welford), `RateSuggestion`,
  or the stored `delta_horas_pct` value itself.
- Strict TDD: write failing tests first, then minimal implementation.
- PMO review before commit/PR/merge.

## Environment note (infra, not code)

Same Docker/AppArmor issue documented in SQ-COST-3/SQ-COST-4's evidence persists on this
host (`docker ps` → `permission denied`). **Workaround (test-only, not part of the
diff):** used the host's native `postgresql@17-main` service; created a fresh isolated DB
`smartquotation_sqcost5` (owner `sq`, same credentials as `backend/.env.example`) so as
not to collide with `smartquotation` / `smartquotation_sqcost3` / `smartquotation_sqcost4`
used by prior/concurrent workers. `backend/.env` (gitignored — confirmed via
`git check-ignore -v backend/.env`) points `POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432
POSTGRES_DB=smartquotation_sqcost5`; a locally-generated `FIELD_ENCRYPTION_KEY` (Fernet
key, dev-only, not committed) was set. A dedicated `.venv` was created and
`requirements/development.txt` installed. Redis was not needed for the suites run.

## RED

Added a new test class `HourVarianceToleranceTests` (8 tests) to
`backend/apps/production/tests.py`, following the existing `HourVarianceUITests` pattern
(observations created directly, not via the real close-out flow, so tests exercise
presentation/classification only — not SQ-COST-3's computation):

- `test_delta_0_01_pct_dentro_da_tolerancia_nao_alerta` (+0.01%)
- `test_delta_exatamente_5_pct_dentro_da_tolerancia` (+5.00%)
- `test_delta_exatamente_minus_5_pct_dentro_da_tolerancia` (-5.00%)
- `test_delta_5_01_pct_acima_da_tolerancia` (+5.01%)
- `test_delta_minus_5_01_pct_abaixo_da_tolerancia` (-5.01%)
- `test_delta_none_continua_sem_base` (regression: `None` stays `sem base`)
- `test_ui_menciona_tolerancia_de_5_porcento` (copy mentions `±5%`)
- `test_model_hours_variance_status_classifica_corretamente` (direct model-property unit
  test over all boundary values, no DB save required)

Verified true RED by first reverting any implementation changes (model property was
written, then explicitly reverted before writing/running tests, to guarantee the tests
were run against unmodified SQ-COST-4 code). Ran:

```
python3 manage.py test apps.production.tests.HourVarianceToleranceTests -v 1
```

```
Ran 8 tests in 6.190s
FAILED (failures=6, errors=1)
```

7/8 failed/errored as expected: `AttributeError: 'ProductionObservation' object has no
attribute 'hours_variance_status'` (model), and 5 template-rendering assertions failed
(no `"dentro do esperado"` / `"acima da tolerância"` / `"abaixo da tolerância"` / `"±5%"`
copy yet — SQ-COST-4's template only had strict-sign over/under/neutral logic). Only
`test_delta_none_continua_sem_base` passed pre-change, as intended — it pins down that
the pre-existing `None → sem base` behavior already satisfied this sprint's requirement
and must keep working unchanged.

## GREEN

Minimal additive implementation, no changes to `pricing_engine/`, `services.py`, or
`ProductionObservation`'s stored fields/migrations (SQ-COST-3's computation is untouched
— `delta_horas_pct` itself is never recalculated or reassigned):

1. `backend/apps/production/models.py` — `ProductionObservation.hours_variance_status`
   (new `@property`) plus class constants `TOLERANCIA_HORAS_PCT = Decimal("5.00")` and
   `STATUS_SEM_BASE/STATUS_DENTRO/STATUS_ACIMA/STATUS_ABAIXO`. Pure classification over
   the existing `delta_horas_pct` field:
   - `None` → `sem_base`
   - `abs(delta) <= 5.00` → `dentro`
   - `delta > 5.00` → `acima`
   - `delta < -5.00` → `abaixo`
   No new DB field, no migration (confirmed by `makemigrations --check --dry-run`).
2. `backend/apps/production/templates/production/detail.html` — "Desvios de Horas"
   section header now includes a `<p class="g-note">tolerância ±5%</p>` subtitle; the
   per-row badge branches on `obs.hours_variance_status` instead of the raw sign of
   `delta_horas_pct`:
   - `sem_base` → `q-badge--na` "sem base" (unchanged from SQ-COST-4)
   - `acima` → `q-badge--over` "+X% acima da tolerância"
   - `abaixo` → `q-badge--under` "X% abaixo da tolerância"
   - `dentro` (covers the old exact-0 case too) → new `q-badge--ok` "±X% dentro do
     esperado" (no existing test asserted the old `q-badge--neutral`/"0,00% no orçado"
     copy, so this is a safe additive change within the "dentro" bucket).
3. `backend/static/css/design-system-g.css` — new `.q-badge--ok` modifier (reuses the
   existing gray/neutral tone, same as `.q-badge--neutral`, which is left in place
   unused rather than removed, to minimize risk). No new dependencies/JS.

Ran:

```
python3 manage.py test apps.production.tests.HourVarianceToleranceTests \
  apps.production.tests.HourVarianceUITests apps.production.tests.ProductionObservationAdminTests -v 2
```

```
Ran 17 tests in 14.496s
OK
```

All 8 new SQ-COST-5 tests pass, plus all 9 pre-existing SQ-COST-4 tests (`HourVarianceUITests`
+ `ProductionObservationAdminTests`) still pass unchanged — including the ones using
delta values of `25.00`/`-40.00` (unaffected: still over/under tolerance) and `5.00`
(`OP-PEQUENO`, only checked in ordering assertions, not badge class — now classified
`dentro`, no regression).

## VERIFY

| Command | Result |
|---|---|
| `python3 manage.py check` | `System check identified no issues (0 silenced).` |
| `python3 manage.py makemigrations --check --dry-run` | `No changes detected` — only a `@property` + class constants added, no model field changes |
| Targeted SQ-COST-5 tests (`HourVarianceToleranceTests`) | `OK` — 8/8 |
| `python3 manage.py test apps.production -v 1` | `OK` — 85/85 (77 baseline + 8 new) |
| `python3 manage.py test apps.quotations apps.production -v 1` | `OK` — 189/189 (181 baseline + 8 new) |
| `python3 -m tests.validate_feixe_completo` | `GATE OK: delta -2.9% dentro de ±10%, 0 erros.` (unchanged — `pricing_engine` untouched) |
| `python3 -m tests.validate_permutador_completo` | `GATE OK` — BEM Δ+0.00%, BEU Δ+0.00%, OF3683 Δ+0.15% (unchanged) |
| `git diff --check` | clean, no output (exit 0) |
| Strict added-line secret scan (`git diff -- backend \| grep -iE '^\+.*(password\|secret\|token\|api[_-]?key\|BEGIN [A-Z ]*PRIVATE KEY\|AKIA)'`) | 0 hits (exit 1 / no match) — no `force_login` password args were added in this sprint's tests |

## Files changed

- `backend/apps/production/models.py` — `ProductionObservation.hours_variance_status`
  read-only property + `TOLERANCIA_HORAS_PCT`/status constants.
- `backend/apps/production/templates/production/detail.html` — tolerance-aware badge
  classification + "tolerância ±5%" subtitle on the "Desvios de Horas" section.
- `backend/static/css/design-system-g.css` — `.q-badge--ok` modifier.
- `backend/apps/production/tests.py` — `HourVarianceToleranceTests` (8 tests), all
  RED→GREEN except the `None` regression guard (passed both before and after, by design).
- `.legatus/evidence/2026-07-16-sq-cost-5-hours-tolerance.md` (this file).

## Not implemented (explicitly out of scope this sprint)

- No tenant-configurable tolerance — `TOLERANCIA_HORAS_PCT` is a fixed `5.00` class
  constant on `ProductionObservation`, per sprint contract ("Default tolerance: 5% for
  this MVP slice... Do not make it tenant-configurable in this sprint").
- No migration added — the tolerance is computed on the fly from the existing
  `delta_horas_pct` field; nothing new is persisted.
- `q-badge--neutral` CSS class kept in `design-system-g.css` but no longer referenced
  by any template (superseded by `q-badge--ok` for all within-tolerance cases, including
  exact 0%) — left in place rather than removed, to minimize diff/risk in a CSS file
  shared by other apps.

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

Additional PMO notes:

- Worker reached `AWAIT_PMO_REVIEW` with coherent artifacts and no commit/push.
- PMO inspected model classification property, template copy/classes, CSS and tests. The implementation is presentation/classification only and does not alter SQ-COST-3 stored `delta_horas_pct`, pricing, `ActualRate`/Welford, `RateSuggestion`, or `ProcessParameter` logic.
- `python3 manage.py check` passed.
- `python3 manage.py makemigrations --check --dry-run` passed: no changes detected.
- Targeted SQ-COST-5/SQ-COST-4 tests passed: 17/17 OK.
- `python3 manage.py test apps.production -v 1` passed: 85/85 OK.
- `python3 manage.py test apps.quotations apps.production -v 1` passed: 189/189 OK.
- Engine gates, `git diff --check`, and strict added-line secret scan passed.

## STATUS

PMO_ACCEPTED
