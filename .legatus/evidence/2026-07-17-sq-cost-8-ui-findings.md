# Evidence — SQ-COST-8-UI Findings Closure

**Started:** 2026-07-17
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-8-ui`
**Branch:** `sdk/sq-cost-8-ui-findings-20260717-002300`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Close the 5 minor UI findings from the Opus UI validation probe (SQ-COST-4/5/6/7 detail page):
  cross-OF suggestion query waste, inaccurate "±5%" copy, double property eval, hardcoded
  tolerance in template, missing template test for ambiguous-metodo `—` branch.
- Strict TDD; PMO review before commit/PR/merge.

## Environment note

`docker compose up -d db` failed in this sandbox exactly as the Opus probe reported (Postgres
container cannot create a Unix socket in `/var/run/postgresql` — permission denied under this
sandbox's Docker driver). Unlike the probe, I had passwordless `sudo` available, but `sudo docker
compose up` hit the same in-container socket permission error (not a host-docker-permission
issue, so `sudo` didn't help). Found a natively-running `postgresql.service` on the host
(`localhost:5432`, role `sq`/`sq`, already used by sibling SmartQuotation worktrees). Created a
dedicated scratch DB `smartquotation_sqcost8` there, pointed `backend/.env`
(`POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_DB=smartquotation_sqcost8`) at it, ran
`migrate_schemas --shared` + `provision_tenant`, and used it to actually run
`manage.py test apps.production` / `apps.quotations` with a real DB (`TenantTestCase` creates its
own Postgres test schema per run). This closes the gap the Opus probe flagged ("não consegui
rodar apps/production/tests.py"). Scratch DB and `.env` files were dropped/removed after
verification; nothing DB-related is part of this change (no new migration).

## RED (before implementation)

`python manage.py test apps.production -v 1` — 103 tests (97 pre-existing + 6 new), ran against
the pre-implementation tree:

- `HourVarianceToleranceTests.test_tolerancia_vem_do_context_a_partir_de_tolerancia_horas_pct`
  → **ERROR** `KeyError: 'tolerancia_horas_pct'` (context var didn't exist yet). Finding 4.
- `ProcessParameterSuggestionTests.test_suggestion_computation_e_escopada_as_operacoes_informadas`
  → **ERROR** `TypeError: processparameter_suggestion() got an unexpected keyword argument
  'operacoes'`. Finding 1.
- `ProductionReviewSignalTests.test_copy_da_secao_de_sinal_usa_frase_precisa_com_tolerancia`
  → **FAIL** — response didn't contain "acima da tolerância (±5%)", still had "acima de ±5%".
  Finding 2.
- `HourVarianceUITests.test_hour_variance_observations_avaliada_uma_unica_vez_na_view` → first
  draft used `return_value=[]` for the mocked property and passed *vacuously* (falsy `[]` short-
  circuits the `{% for %}`, so the property was only hit once regardless of the bug). Rewrote to
  return a truthy `[obs]` list; re-ran in isolation → **FAIL** `2 != 1` (property evaluated once
  in the `{% if %}`, once in the `{% for %}`). Finding 3, confirmed RED.
- `ProcessParameterSuggestionTests.test_view_computa_sugestao_somente_para_operacoes_da_of_atual`
  and `test_detail_renderiza_traco_para_metodo_ambiguo_mas_mantem_fator_e_medias` passed
  immediately — expected: these are regression/coverage additions for behavior that was already
  correct (view already filtered `review_signal_flagged` by `of_operacao_codes`; the ambiguous-
  `metodo` → `—` template branch already worked, it just had no dedicated template test, per
  Finding 5's own description "has a service test but NO template/UI test"). Left as-is; they
  serve as regression coverage going forward and stayed green through the implementation.

## GREEN (after implementation)

Changes (all within the allowed scope: `views.py`, `services.py`, `detail.html`, `tests.py`):

- `backend/apps/production/services.py`: `processparameter_suggestion(operacoes=None)` — new
  optional param; when given, flagged operations outside the set are `continue`d *before* the
  per-operation `ProductionObservation` queries (actual/estimated means, metodo resolution,
  `ProcessParameter.objects.vigente` lookup) run. `None` (default) preserves prior behavior for
  existing callers/tests.
- `backend/apps/production/views.py`:
  - `services.processparameter_suggestion(operacoes=of_operacao_codes)` — suggestions are now
    only computed for this OF's roteiro codes (Finding 1).
  - `hour_variance_observations = of.hour_variance_observations` computed once and passed in
    context; template no longer calls the property from two separate `{% if %}`/`{% for %}`
    sites (Finding 3).
  - `tolerancia_horas_pct = f"±{ProductionObservation.TOLERANCIA_HORAS_PCT:.0f}%"` passed in
    context (Finding 4) — renders "±5%", sourced from the model constant instead of duplicated
    template literals.
- `backend/apps/production/templates/production/detail.html`:
  - `{% if of.hour_variance_observations %}` / `{% for obs in of.hour_variance_observations %}`
    → `{% if hour_variance_observations %}` / `{% for obs in hour_variance_observations %}`.
  - `tolerância ±5%` → `tolerância {{ tolerancia_horas_pct }}`.
  - `"...acima de ±5% em observações fechadas..."` →
    `"...acima da tolerância ({{ tolerancia_horas_pct }}) em observações fechadas..."` (Finding 2).
- `backend/apps/production/tests.py`: 6 new tests (see RED above) across `HourVarianceUITests`,
  `HourVarianceToleranceTests`, `ProductionReviewSignalTests`, `ProcessParameterSuggestionTests`;
  extended `ProcessParameterSuggestionTests._observation` with an optional `ordem=` kwarg (used by
  the scoping test to attach observations to a different OF).

`python manage.py test apps.production -v 1` → **103/103 OK**.

## VERIFY

- `cd backend && python3 manage.py check` → `System check identified no issues (0 silenced).`
- `cd backend && python3 manage.py makemigrations --check --dry-run` → `No changes detected`
  (no new migration, as required).
- `cd backend && python3 manage.py test apps.production -v 1` → **103/103 OK**.
- `cd backend && python3 manage.py test apps.quotations apps.production -v 1` → **207/207 OK**
  (no regression in SQ-COST-3..7 or quotations behavior).
- `python3 -m tests.validate_feixe_completo` → **GATE OK** (delta -2.9%, 0 errors — unchanged;
  `pricing_engine` was not touched).
- `python3 -m tests.validate_permutador_completo` → **GATE OK** (BEU/BEM/OF3683 all OK, 0 geometry
  divergences — unchanged; `pricing_engine` was not touched).
- `git diff --check` → clean, no whitespace errors.
- Strict added-line secret scan (`git diff | added lines | grep -iE
  "(api[_-]?key|secret|password|token|bearer|aws_|private_key|-----BEGIN)"`) → no matches.
- `.env` / scratch test DB created for local verification were removed (`.env` is gitignored,
  never staged; `smartquotation_sqcost8` DB dropped after the run) — no residue in the diff.

## Findings closure summary

1. **(média) Cross-OF suggestion query waste** — CLOSED. `processparameter_suggestion(operacoes=…)`
   added; view passes `of_operacao_codes`; per-op queries now `continue` before running for
   operations outside this OF's roteiro. Verified by
   `test_suggestion_computation_e_escopada_as_operacoes_informadas` (service-level membership) and
   `test_view_computa_sugestao_somente_para_operacoes_da_of_atual` (view/context integration).
2. **(baixa) Imprecise "acima de ±5%" copy** — CLOSED. Changed to "acima da tolerância (±5%)" in
   the Sinal de Revisão section header. Verified by
   `test_copy_da_secao_de_sinal_usa_frase_precisa_com_tolerancia`.
3. **(baixa) Double `hour_variance_observations` property eval** — CLOSED. View computes once,
   passes the list via context; template reads the context var in both the `{% if %}` and
   `{% for %}`. Verified by `test_hour_variance_observations_avaliada_uma_unica_vez_na_view`
   (PropertyMock call-count == 1).
4. **(baixa) Hardcoded "±5%" in template** — CLOSED. View derives `tolerancia_horas_pct` from
   `ProductionObservation.TOLERANCIA_HORAS_PCT`; template uses `{{ tolerancia_horas_pct }}` in
   both places it previously hardcoded the string. Displayed text unchanged ("±5%"). Verified by
   `test_tolerancia_vem_do_context_a_partir_de_tolerancia_horas_pct` (asserts
   `response.context["tolerancia_horas_pct"] == "±5%"`) plus the pre-existing
   `test_ui_menciona_tolerancia_de_5_porcento`.
5. **(baixa, coverage) Missing template test for ambiguous-metodo `—` branch** — CLOSED.
   `test_detail_renderiza_traco_para_metodo_ambiguo_mas_mantem_fator_e_medias` added: 3 closed
   observations for the same `codigo_op` linked to two different `OFOperation`s with divergent
   `metodo` ("radial" vs "cnc") → `current_value`/`proposed_value` stay `None` in the service;
   asserts the rendered row shows exactly 2 "—" (ProcessParameter atual/proposto) while factor
   ("1,2000×") and mean actual hours ("12,00") still render. This test passed without any
   behavior change (the branch already worked) — it only adds the missing coverage, as the
   finding's own description anticipated ("has a service test but NO template/UI test").

## Scope discipline

No changes to `pricing_engine`, `services._close_out_observations`, Welford/`ActualRate`,
`RateSuggestion`. No stored `delta_horas_pct` semantics changed. No `ProcessParameter` auto-apply
introduced. No new CSS (reused existing Design System G classes `g-note`, `q-badge`, `g-table`,
etc.). No new migration. Changes limited to `views.py`, `services.py` (one additive optional
kwarg), `detail.html`, and `tests.py`.

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

PMO independently re-ran (no DB sandbox workaround needed — `python3` system + `postgresql.service`
host DB was used both by the worker and PMO):
- engine gates unchanged: feixe -2.9%, permutador BEU/BEM/OF3683 OK.
- `manage.py check` clean; `makemigrations --check` clean (no migration).
- 6 new SQ-COST-8 tests PASS (RED→GREEN proven by worker; PMO confirmed GREEN).
- `apps.production` 103/103 OK; `apps.quotations + apps.production` 207/207 OK.
- `git diff --check` clean; added-line secret scan clean.
- Scope discipline confirmed: only `views.py`, `services.py` (+1 optional kwarg),
  `detail.html`, `tests.py`. No motor/preço/migration.

Findings 1-5 CLOSED. Recommended for merge.

## STATUS

AWAIT_PMO_REVIEW → ACCEPTED
