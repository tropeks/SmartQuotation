# Evidence — SQ-COST-7 ProcessParameter Suggestion

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-7`
**Branch:** `sdk/sq-cost-7-processparameter-suggestion-20260716-232557`
**Base:** `main` after PR #74 (`46a3db9`), same worktree lineage as SQ-COST-6
(`PMO_ACCEPTED`, `.legatus/evidence/2026-07-16-sq-cost-6-processparameter-signal.md`).
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Build on SQ-COST-6's `production_review_signal()` (per-operation
  `review_recommended`/`insufficient_data`/`ok` classification over
  `ProductionObservation.delta_horas_pct`). For each `review_recommended` operation,
  compute a *proposed* new `ProcessParameter.valor` (física → horas) as a **read-only,
  manual-only suggestion** — never write it back.
- Formula (per mission/sprint contract): `mean_actual_hh` / `mean_estimated_hh` over the
  same closed observations the SQ-COST-6 signal already aggregates; `factor =
  mean_actual_hh / mean_estimated_hh` (guarded against `mean_estimated_hh == 0`);
  `proposed_value = current_value * factor` only when a `ProcessParameter` mapping is
  available.
- First understand `ProcessParameter`'s keying (`apps/engineering_params/models.py`)
  before attempting any join — see "ProcessParameter keying decision" below.
- Surface read-only on the OF detail page as extra columns in the existing "Sinal de
  Revisão — ProcessParameter" table (SQ-COST-6), not a new section — the proposal is a
  continuation of the same signal, not a separate concept — plus a note paragraph
  stating explicitly that nothing is applied automatically.
- Strict TDD: failing tests first (verified by temporarily stashing the
  implementation, see RED below), then minimal implementation.
- PMO review before commit/PR/merge.

## ProcessParameter keying decision

Read `backend/apps/engineering_params/models.py` first, as instructed:

- `ProcessParameter` is keyed by **(`operacao`, `metodo`, `material`, `valid_from`)** —
  `metodo ∈ {radial, cnc, manual}`, `material` optional (`None` = fallback covering all
  materials for that operacao+metodo). `ProcessParameterManager.vigente(operacao,
  metodo, material=None, on_date=None)` resolves the vigente row: specific-material row
  wins if present, else the `material=None` fallback. `valor` (`DecimalField`,
  `null=True` — "None = pendente") is the física→horas field the mission asks about.
- `ProductionObservation` (the SQ-COST-3/6 source of the signal) only stores
  `operacao` (a plain `CharField`, matching `OFOperation.codigo_op` /
  `ProcessParameter.operacao` by *string value*, not an FK) — it has **no `metodo` and
  no `material` field of its own**. The only place `metodo` exists on the production
  side is `OFOperation.metodo` (copied at OF-conversion time from
  `ItemOperation.metodo`, itself driven by the pricing engine's radial/CNC routing
  rule), reachable from a `ProductionObservation` only via its nullable
  `of_operation` FK (`on_delete=models.SET_NULL`).
- This means a **single `operacao` code can legitimately have been apportioned under
  different `metodo`s across different OFs/observations** (e.g. a drilling op done
  radial in one job, CNC in another — this is precisely the ≤600/>600-hole rule
  documented in root `CLAUDE.md`). There is **no reliable, always-safe join** from an
  aggregated `operacao` bucket straight to one `ProcessParameter` row — the mission
  explicitly said not to invent a fake one.
- **What I implemented** (`services.processparameter_suggestion()`,
  `backend/apps/production/services.py`): for each flagged operation, collect the
  `metodo` values of the `OFOperation`s still linked (`of_operation` not null, `metodo`
  not blank) to that operation's closed observations. **If and only if exactly one
  distinct `metodo` is present**, resolve `ProcessParameter.objects.vigente(operacao,
  metodo, material=None)` — using the `material=None` fallback deliberately, since
  there is no reliable material key available on the production side to disambiguate
  further, and `vigente()` itself falls back to `material=None` when no
  material-specific row exists. If `metodo`s disagree (or none are known — e.g. all
  linked `OFOperation`s were deleted, `of_operation` went `NULL` via `SET_NULL`, or no
  vigente `ProcessParameter` with a non-null `valor` exists), `current_value` and
  `proposed_value` are `None` — the row is still returned with `factor` +
  `mean_actual_hh`/`mean_estimated_hh`, so the analytics/proposal itself never
  disappears, only the automatic mapping to a specific `ProcessParameter` row. The
  engineer is expected to eyeball which `ProcessParameter` (operação × método ×
  material) the proposal should apply to in that case — exactly what the mission asked
  for as the documented fallback.

## RED

Added a new test class `ProcessParameterSuggestionTests` (5 tests) to
`backend/apps/production/tests.py`, following the exact same pattern as SQ-COST-6's
`ProductionReviewSignalTests` (observations created directly via
`ProductionObservation.objects.create(...)`, not via the real close-out flow — this
sprint exercises the suggestion computation/presentation only, not SQ-COST-3's
computation of `delta_horas_pct`):

- `test_proposed_value_e_current_vezes_factor_com_mapeamento_disponivel` — 3 closed
  observations (`actual_hh=12.00`, `estimated_hh=10.00`, all linked via `of_operation`
  to one `OFOperation` with `metodo="radial"`) plus one matching `ProcessParameter`
  (`valor=40.0000`, `metodo="radial"`, `material=None`) → asserts
  `mean_actual_hh=12.00`, `mean_estimated_hh=10.00`, `factor=1.2000`,
  `current_value=40.0000`, `proposed_value=48.0000`.
- `test_estimated_hh_medio_zero_nao_gera_proposed_value` — 3 flagged observations with
  `estimated_hh=0.00` (a deliberately contrived combination for the guard — real
  close-out via `services._close_out_observations` never produces a non-`None`
  `delta_horas_pct` when `estimated_hh<=0`, so this is a defensive test, not a realistic
  production scenario) → asserts `mean_estimated_hh=0.00`, `factor is None`,
  `proposed_value is None`.
- `test_operacao_nao_flagged_nao_aparece_na_sugestao` — an `ok`-classified operation
  (mean |Δ|=2.00% ≤ 5.00%) is absent from `processparameter_suggestion()`'s output.
- `test_sugestao_nao_persiste_processparameter` — calls
  `services.processparameter_suggestion()` (with a mappable operation/factor/proposal)
  and then `refresh_from_db()`s the `ProcessParameter` row, asserting `valor` is still
  the original `40.0000` — the proposal is never written back.
- `test_detail_renderiza_proposta_manual_para_operacao_flagged` — hits `/ofs/<pk>/` for
  an OF with a flagged operation (using a real `codigo_op` copied into this OF's own
  routing, with `metodo` forced to `"radial"` to make the mapping reliable) and asserts
  the response contains both the manual-proposal copy (`"proposta manual"`) and the
  rendered proposed value (`"48,0000"`, pt-BR formatted).

Verified RED **empirically**, not just by inspection: stashed only the implementation
files (`services.py`, `views.py`, `detail.html` — kept `tests.py`) with `git stash push
-- <paths>`, ran the new test class against the pre-implementation code, then restored
the stash (`git stash pop`) before implementing. Output before implementation:

```
python3 manage.py test apps.production.tests.ProcessParameterSuggestionTests -v 2
```

```
test_detail_renderiza_proposta_manual_para_operacao_flagged ... FAIL
test_estimated_hh_medio_zero_nao_gera_proposed_value ... ERROR
test_operacao_nao_flagged_nao_aparece_na_sugestao ... ERROR
test_proposed_value_e_current_vezes_factor_com_mapeamento_disponivel ... ERROR
test_sugestao_nao_persiste_processparameter ... ERROR

Ran 5 tests in 5.088s
FAILED (failures=1, errors=4)
```

4/5 errored with `AttributeError: module 'apps.production.services' has no attribute
'processparameter_suggestion'` (the 4 tests calling the service directly); the 5th
(`test_detail_renderiza_proposta_manual_para_operacao_flagged`) failed on
`assertContains(response, "proposta manual")` — the OF detail page rendered the
SQ-COST-6 "Sinal de Revisão" section (unrelated pre-existing feature) but not the new
proposal copy/value, as expected.

## GREEN

Minimal additive implementation, no changes to `pricing_engine/`,
`services._close_out_observations`, `_update_actual_rate` (Welford), `RateSuggestion`,
any `ProcessParameter` row, or any stored `ProductionObservation`/`delta_horas_pct`
field:

1. `backend/apps/production/services.py` — new `processparameter_suggestion()`
   (module-level, matching the exact name suggested in the mission brief). Iterates
   `ProductionObservation.objects.flagged_for_review()` (SQ-COST-6, unchanged), and for
   each flagged `operacao`:
   - Re-reads the same closed observations (`delta_horas_pct__isnull=False`) to compute
     `mean_actual_hh` / `mean_estimated_hh` (quantized to 2 decimals, matching
     `ProductionObservation`'s own `DecimalField` precision).
   - `factor = mean_actual_hh / mean_estimated_hh` (quantized to 4 decimals, matching
     `ProcessParameter.valor`'s `decimal_places=4`), `None` when
     `mean_estimated_hh == 0` (divide-by-zero guard).
   - Resolves `current_value` via the single-`metodo` join described above
     (`apps.engineering_params.models.ProcessParameter`, imported locally inside the
     function — same convention as the other cross-app imports already in this file,
     e.g. `apps.integrations.protheus`/`apps.integrations.sap_b1`).
   - `proposed_value = current_value * factor` (quantized to 4 decimals), only when
     both are not `None`.
   - Returns a list of dicts:
     `{"operacao", "current_value", "proposed_value", "factor", "mean_actual_hh",
     "mean_estimated_hh"}` — exactly the shape requested in the mission brief.
   - **No write** anywhere — pure read + Python arithmetic, no `.save()`/`.update()`
     call touches `ProcessParameter`.
2. `backend/apps/production/views.py` (`ordem_detail`) — computes
   `suggestion_by_op = {row["operacao"]: row for row in
   services.processparameter_suggestion()}` and merges each suggestion into the
   existing `review_signal_flagged` rows as `row["suggestion"]`
   (`{**row, "suggestion": suggestion_by_op.get(row["operacao"])}`). Since
   `processparameter_suggestion()` iterates the exact same `flagged_for_review()` set
   as `production_review_signal()`'s `review_recommended` subset, every row in
   `review_signal_flagged` always has a matching (possibly all-`None`-mapping) entry in
   `suggestion_by_op` — no `KeyError`/silent drop.
3. `backend/apps/production/templates/production/detail.html` — extended the existing
   SQ-COST-6 "Sinal de Revisão — ProcessParameter" table (did **not** duplicate it into
   a separate section) with four new columns: "HH médio real", "HH médio estimado",
   "Fator proposto", "ProcessParameter atual", "ProcessParameter proposto" (`—` when
   `None`, using `{% if ... != None %}` since `Decimal("0")`/`Decimal("0.0000")` are
   Python-falsy and would otherwise wrongly render as `—`). Added one `<p class="g-note">`
   paragraph directly below the table stating the values are a **"proposta manual"**
   suggestion, that **"nada é alterado automaticamente"**, and that when there is no
   unambiguous `metodo` the mapping shows `—` and is left to the engineer's judgement.
   Reused `g-table`/`g-note`/`mono`/`num` Design System G classes and the existing
   `brl` filter (`|brl:4` for the 4-decimal `ProcessParameter`-precision figures) — no
   new CSS.
4. `backend/apps/production/tests.py` — `ProcessParameterSuggestionTests` (5 tests, see
   RED).

Ran (targeted SQ-COST-7 + SQ-COST-4/5/6 regression):

```
python3 manage.py test apps.production.tests.ProcessParameterSuggestionTests \
  apps.production.tests.ProductionReviewSignalTests \
  apps.production.tests.HourVarianceUITests \
  apps.production.tests.HourVarianceToleranceTests \
  apps.production.tests.ProductionObservationAdminTests -v 2
```

```
Ran 29 tests in 25.462s
OK
```

All 5 new SQ-COST-7 tests pass, plus all 24 SQ-COST-4/5/6 tests unchanged.

## VERIFY

Environment note: same infra situation as SQ-COST-3/4/5/6 — `docker ps` on this host
still fails with `permission denied while trying to connect to the Docker daemon
socket`. Used the host's native `postgresql.service` (already running), created a
fresh isolated DB `smartquotation_sqcost7` (`CREATE DATABASE smartquotation_sqcost7
OWNER sq;`, same `sq`/`sq` credentials as `backend/.env.example`) so as not to collide
with `smartquotation`/`smartquotation_sqcost{3,4,5,6}` from prior/concurrent workers.
Created a dedicated `backend/.venv` and installed `requirements/development.txt`. As
documented in SQ-COST-6's evidence, `backend/.env` is not actually read by
`manage.py` (`django-environ` never calls `read_env`), so all commands below export
`POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_USER=sq POSTGRES_PASSWORD=sq
POSTGRES_DB=smartquotation_sqcost7 FIELD_ENCRYPTION_KEY=<fernet key>` directly in the
shell first.

| Command | Result |
|---|---|
| `python3 manage.py check` | `System check identified no issues (0 silenced).` |
| `python3 manage.py makemigrations --check --dry-run` | `No changes detected` — no model field/migration change, additive service function + view/template only |
| RED verification (stash implementation, keep tests) | 4 errors (`AttributeError: ... no attribute 'processparameter_suggestion'`) + 1 failure (`assertContains` proposal copy) — confirmed real RED, not just by inspection |
| Targeted SQ-COST-7 tests (`ProcessParameterSuggestionTests`) | `OK` — 5/5 |
| Targeted SQ-COST-7 + SQ-COST-4/5/6 regression (29 tests) | `OK` — 29/29 |
| `python3 manage.py test apps.production -v 1` | `OK` — 97/97 (92 baseline + 5 new) |
| `python3 manage.py test apps.quotations apps.production -v 1` | `OK` — 201/201 (196 baseline + 5 new) |
| `python3 -m tests.validate_feixe_completo` | `GATE OK: delta -2.9% dentro de ±10%, 0 erros.` (unchanged — `pricing_engine` untouched) |
| `python3 -m tests.validate_permutador_completo` | `GATE OK` — BEM Δ+0.00%, BEU Δ+0.00%, OF3683 Δ+0.15% (unchanged) |
| `git diff --check` | clean, exit 0, no output |
| Strict added-line secret scan (`git diff -- backend \| grep -iE '^\+.*(password\|secret\|token\|api[_-]?key\|BEGIN [A-Z ]*PRIVATE KEY\|AKIA)'`) | 0 hits (exit 1 / no match) — no `force_login` password args or credentials added |

## Files changed

- `backend/apps/production/services.py` — `processparameter_suggestion()`, a new
  read-only function computing per-flagged-operation proposed `ProcessParameter`
  values (see GREEN above for the exact algorithm and the single-`metodo` mapping
  rule).
- `backend/apps/production/views.py` — `ordem_detail` computes
  `processparameter_suggestion()` and merges it into `review_signal_flagged` rows as
  `row["suggestion"]` (scoped, like SQ-COST-6, to this OF's own routing via the
  pre-existing `of_operacao_codes` filter — no new scoping logic added).
- `backend/apps/production/templates/production/detail.html` — extends the SQ-COST-6
  "Sinal de Revisão — ProcessParameter" table (does not add a new section) with
  proposal columns + a manual-proposal disclaimer note. No new CSS.
- `backend/apps/production/tests.py` — `ProcessParameterSuggestionTests` (5 tests, all
  RED→GREEN, verified by an actual stash/run/restore cycle, not just code inspection).
- `.legatus/evidence/2026-07-16-sq-cost-7-processparameter-suggestion.md` (this file).

## Design decisions / not implemented (explicitly out of scope this sprint)

- **No auto-apply anywhere** — `processparameter_suggestion()` never calls `.save()`/
  `.update()` on `ProcessParameter` (or anything else); confirmed by
  `test_sugestao_nao_persiste_processparameter` and by inspection (the function only
  does `ProcessParameter.objects.vigente(...)`, a read).
- **Ambiguous-`metodo` operations get `current_value=None`/`proposed_value=None`, not a
  guessed row** — per the mission's explicit "do not invent a fake join." The
  factor/means are still shown so the proposal isn't hidden, just the automatic
  `ProcessParameter` mapping.
- **Material is always resolved via the `material=None` fallback** — there is no
  material key reachable from `ProductionObservation`/`OFOperation` at all (material is
  tracked per-`OFMaterial`/item, not per-operation), so attempting to disambiguate by
  material would itself be an invented join. This mirrors how `ProcessParameter.vigente`
  already treats `material=None` as "applies broadly."
- **No admin surface** — mission asked for a "detail page or similar" read-only UI
  surface; extended the existing SQ-COST-6 detail-page table only, consistent with
  SQ-COST-6's own choice not to touch the admin.
- **No tenant-configurable behavior added** — reuses SQ-COST-6's fixed
  `REVIEW_MIN_SAMPLES`/`TOLERANCIA_HORAS_PCT`; the SQ-COST-7 computation itself has no
  new tunable constants, per "Do NOT add tenant-configurable behavior unless trivial."
- Confirmed **no coupling** to `Rate`, `ActualRate` (Welford), `RateSuggestion`, or
  `pricing_engine` — `processparameter_suggestion()` only reads
  `ProductionObservation.{operacao,actual_hh,estimated_hh,delta_horas_pct,of_operation}`
  (SQ-COST-3, unchanged) and `ProcessParameter.{operacao,metodo,material,valor}`
  (`engineering_params`, unchanged) — read-only on both.
- Stored `delta_horas_pct` was **not** touched (no test or code path in this diff
  writes to it) — confirmed via `git diff` review and the passing SQ-COST-3/4/5
  regression tests (`HourVarianceUITests`/`HourVarianceToleranceTests`).

## Risks / open questions for PMO

- The single-`metodo` heuristic is a judgment call, not something explicitly
  prescribed by the sprint contract (which left the ambiguous case to the worker to
  design and document). An alternative would have been "most common `metodo` among
  observations" instead of "exactly one distinct `metodo`, else `None`" — I chose the
  stricter version to avoid ever silently picking a `ProcessParameter` row the engineer
  didn't actually use for some of the underlying observations. Worth a PMO sanity check
  since it affects how often `current_value`/`proposed_value` show `—` vs. a number in
  practice (in real long-lived operations that occasionally switch radial↔CNC, they'll
  show `—` even though most of the mass agrees on one `metodo`).
- `mean_actual_hh`/`mean_estimated_hh` are recomputed by
  `processparameter_suggestion()` from the same closed-observations query
  `production_review_signal()` already runs (not shared/cached) — an intentional
  simplicity trade-off (two small read-only queries per flagged operation instead of
  threading the raw observation list through both functions), acceptable given OF
  detail pages are low-traffic, human-facing pages, not a hot path.

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

Additional PMO notes:

- Worker reached `AWAIT_PMO_REVIEW` with coherent artifacts and no commit/push.
- PMO inspected `processparameter_suggestion()` (read-only, no write to `ProcessParameter`), the view merge, and the extended template with the manual-proposal disclaimer. The suggestion is analytics + a manual proposal surface only; it NEVER writes back to `ProcessParameter`, `Rate`, Welford/`ActualRate`, `RateSuggestion`, or `pricing_engine`, and does not change `delta_horas_pct` or pricing/quotation totals.
- ProcessParameter keying decision confirmed by PMO inspection of `apps/engineering_params/models.py`: keyed by `(operacao, metodo, material, valid_from)`; `ProductionObservation` only stores `operacao` (string) and `metodo` is only reachable via nullable `of_operation`. The worker resolves `current_value` only when all closed observations for an operation agree on exactly one non-blank `metodo` (via `ProcessParameter.objects.vigente(operacao, metodo, material=None)`); otherwise `current_value`/`proposed_value` are `None` and only `factor` + means are shown. This is the defensible "no fake join" behavior from the contract.
- `python3 manage.py check` passed.
- `python3 manage.py makemigrations --check --dry-run` passed: no changes detected.
- Targeted SQ-COST-7/SQ-COST-4/5/6 tests passed: 29/29 OK.
- `python3 manage.py test apps.production -v 1` passed: 97/97 OK.
- `python3 manage.py test apps.quotations apps.production -v 1` passed: 201/201 OK.
- Engine gates, `git diff --check`, and strict added-line secret scan passed.

## STATUS

PMO_ACCEPTED
