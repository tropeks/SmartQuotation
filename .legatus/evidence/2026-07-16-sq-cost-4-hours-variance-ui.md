# Evidence — SQ-COST-4 Hours Variance UI

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-4`
**Branch:** `sdk/sq-cost-4-hours-variance-ui-20260716-212023`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Add read-only visual/admin surface for SQ-COST-3 hour variance (`ProductionObservation.estimated_hh`
  / `actual_hh` / `delta_horas_pct`).
- Preserve computation/rate/pricing behavior — no changes to `pricing_engine`, `services._close_out_observations`,
  `_update_actual_rate` (Welford), or `RateSuggestion`.
- Strict TDD: write failing tests first, then minimal implementation.
- PMO review before commit/PR/merge.

## Environment note (infra, not code)

Same Docker/AppArmor issue documented in SQ-COST-3's evidence persists on this host (`docker ps` returns
`permission denied` for this session; `docker compose up -d db redis` was not attempted since Docker access
itself was denied here, not just container start). **Workaround (test-only, not part of the diff):** used the
host's native `postgresql@17-main` service; created an isolated `smartquotation_sqcost4` DB (owner `sq`, same
credentials as `backend/.env.example`) so as not to collide with `smartquotation` / `smartquotation_sqcost3` /
`test_smartquotation*` used by concurrent/prior workers. `backend/.env` (gitignored, not part of the diff, confirmed
via `git check-ignore -v backend/.env`) points `POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432
POSTGRES_DB=smartquotation_sqcost4`; also set a locally-generated `FIELD_ENCRYPTION_KEY` (Fernet key, dev-only,
not committed). Redis was not needed for the test suites run. A stale `test_smartquotation_sqcost4` DB from an
earlier command that hit the harness's own 2-minute tool timeout (not a server hang — the `manage.py test`
command needs ~166s and the *tool call*, not the shell `timeout`, was capping at 120s) was dropped via
`--noinput` on the next run; this only touched a test DB created by this session in an isolated database, not
any other worker's or production data.

## RED

Added two new test classes to `backend/apps/production/tests.py` (11 tests) before touching any
production code, following existing patterns in the file (`OrdemFabricacaoDetailViewTests` for view
tests, `apps.integrations.sap_b1.admin.SapB1ReadOnlyAdmin` for the read-only-admin test shape):

- `HourVarianceUITests` (9 tests) — builds `ProductionObservation` rows directly (not via the real
  close-out flow) so the tests exercise presentation only, not SQ-COST-3's computation:
  - `test_detail_renderiza_secao_desvios_de_horas_quando_observations_existem`
  - `test_detail_sem_observations_nao_renderiza_secao_e_nao_quebra` (regression guard, passes pre-change too)
  - `test_delta_positivo_renderiza_badge_over`
  - `test_delta_negativo_renderiza_badge_under`
  - `test_delta_none_renderiza_sem_base_sem_crash`
  - `test_hour_variance_observations_ordenadas_por_maior_delta_absoluto`
  - `test_detail_renderiza_ordem_por_maior_desvio_absoluto`
- `ProductionObservationAdminTests` (2 tests):
  - `test_admin_e_somente_leitura`
  - `test_admin_list_display_inclui_delta`

Ran `python3 manage.py test apps.production.tests.HourVarianceUITests
apps.production.tests.ProductionObservationAdminTests -v 2` against pre-change code:

```
test_delta_negativo_renderiza_badge_under ... FAIL
test_delta_none_renderiza_sem_base_sem_crash ... FAIL
test_delta_positivo_renderiza_badge_over ... FAIL
test_detail_renderiza_ordem_por_maior_desvio_absoluto ... ERROR
test_detail_renderiza_secao_desvios_de_horas_quando_observations_existem ... FAIL
test_detail_sem_observations_nao_renderiza_secao_e_nao_quebra ... ok
test_hour_variance_observations_ordenadas_por_maior_delta_absoluto ... ERROR
test_admin_e_somente_leitura ... ERROR
test_admin_list_display_inclui_delta ... ERROR
```

8/9 failed/errored as expected (missing template section, missing `OrdemFabricacao.hour_variance_observations`
property, missing `ProductionObservationAdmin`). The regression test (`test_detail_sem_observations_...`)
passed pre-change too, as intended — it only pins down that OF detail keeps working with zero observations.

## GREEN

Minimal additive implementation, no changes to `pricing_engine/`, `services.py`, or `ProductionObservation`'s
fields/migrations (SQ-COST-3's model and computation are untouched):

1. `backend/apps/production/models.py` — `OrdemFabricacao.hour_variance_observations` (new `@property`,
   same style as existing `OFItem.custo_total` / `OFOperation.actual_hh` properties): returns
   `self.observations.all()` sorted in Python by `|delta_horas_pct|` descending (nulls last, via a `Decimal("-1")`
   sentinel key since real deltas are always `>= 0` in absolute value). Pure read-only sort, no recomputation.
2. `backend/apps/production/templates/production/detail.html` — new "Desvios de Horas (Orçado × Real)" section,
   placed right after "Roteiro & Apontamento" (per sprint guidance: near the per-operation/apontamento section),
   gated on `{% if of.hour_variance_observations %}` (i.e. renders whenever observations exist — not tied to OF
   status, since the acceptance criterion is "when ProductionObservation rows exist"). Per row: operação, horas
   est., horas reais, and a badge: `q-badge--over` (delta > 0, "+X% acima"), `q-badge--under` (delta < 0, "X%
   abaixo"), `q-badge--neutral` (delta == 0), `q-badge--na` ("sem base", delta is `None` — no misleading "0%").
3. `backend/static/css/design-system-g.css` — 4 small modifier classes on the existing `.q-badge` base
   (`--over`/`--under`/`--neutral`/`--na`) using already-defined semantic color vars (`--g-red`, `--g-green`,
   `--g-gray-1`, `--g-amber`). No new dependencies/JS.
4. `backend/apps/production/admin.py` — `ProductionObservationAdmin` (`@admin.register(ProductionObservation)`),
   same read-only shape as `apps.integrations.sap_b1.admin.SapB1ReadOnlyAdmin` (blocks add/delete, all fields
   readonly via `get_readonly_fields`); `list_display` includes `delta_horas_pct`/`estimated_hh`/`actual_hh`;
   `list_filter`/`search_fields` on `operacao`/`ordem__number`.

Ran `python3 manage.py test apps.production.tests.HourVarianceUITests
apps.production.tests.ProductionObservationAdminTests -v 2` after the change:

```
Ran 9 tests in 10.361s

OK
```

All 9 new tests pass (8 RED→GREEN + 1 regression, unaffected throughout).

## VERIFY

| Command | Result |
|---|---|
| `python3 manage.py check` | `System check identified no issues (0 silenced).` |
| `python3 manage.py makemigrations --check --dry-run` | `No changes detected` — no model field changes, only a `@property` (no migration needed) |
| `python3 manage.py test apps.production -v 1` | `OK` (77/77 — 68 baseline + 9 new) |
| `python3 manage.py test apps.quotations apps.production -v 1` | `OK` (181/181 — 172 baseline + 9 new) |
| `python3 -m tests.validate_feixe_completo` | `GATE OK: delta -2.9% dentro de ±10%, 0 erros.` (unchanged — `pricing_engine` untouched) |
| `python3 -m tests.validate_permutador_completo` | `GATE OK` — BEM Δ+0.00%, BEU Δ+0.00%, OF3683 Δ+0.15% (unchanged) |
| `git diff --check` | clean, no output |
| Added-line secret scan (`git diff \| grep -iE '^\+.*(password\|secret\|token\|api[_-]?key\|BEGIN ... PRIVATE KEY\|AKIA)'`) | 1 hit, reviewed: `User.objects.create_user(username="eng_hv", password="x")` in the new test — a dummy fixture password, matching the exact `password="x"` pattern already used 7 other times pre-existing in this same test file (e.g. `ApontamentoViewTests`). Not a real credential. |

## Files changed

- `backend/apps/production/models.py` — `OrdemFabricacao.hour_variance_observations` read-only property.
- `backend/apps/production/templates/production/detail.html` — new "Desvios de Horas" section.
- `backend/static/css/design-system-g.css` — `.q-badge--over/--under/--neutral/--na` modifiers.
- `backend/apps/production/admin.py` — read-only `ProductionObservationAdmin`.
- `backend/apps/production/tests.py` — `HourVarianceUITests` (7 tests) + `ProductionObservationAdminTests`
  (2 tests) = 9 new tests, all RED→GREEN except the one regression guard.
- `.legatus/evidence/2026-07-16-sq-cost-4-hours-variance-ui.md` (this file).

## Not implemented (explicitly out of scope this sprint)

- No neutral-band threshold (e.g. "±5% = neutral"): `delta_horas_pct == 0` exactly maps to the neutral badge,
  everything else is strictly over/under. A tolerance band would be a product decision not specified in the
  sprint contract — flagging as a possible fast follow-up if Wellington/PMO wants it.
- No dedicated admin `list_filter` on OF status (would require a custom `SimpleListFilter` traversing the FK) —
  kept to the cheap/safe `operacao` filter + `operacao`/`ordem__number` search per the "do not overbuild"
  instruction.
- Existing "R$/h Observado (fechamento)" section (gated on `status == concluida`, uses `of.observations.all()`
  in its original unsorted order) was left untouched — the new "Desvios de Horas" section is additive, not a
  replacement, per the forbidden-scope instruction not to touch SQ-COST-3's existing surfaces.

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

Additional PMO notes:

- Worker reached `AWAIT_PMO_REVIEW` with coherent artifacts and no commit/push.
- PMO inspected model property, template, CSS, admin and tests. The implementation is additive and does not touch SQ-COST-3 computation, pricing, `ActualRate`/Welford or `RateSuggestion`.
- PMO removed the dummy `password="x"` argument from the new UI test fixture so the strict added-line secret scan passes with zero hits; `force_login()` does not require a password.
- `python3 manage.py check` passed.
- `python3 manage.py makemigrations --check --dry-run` passed: no changes detected.
- Targeted SQ-COST-4 tests passed: 9/9 OK.
- `python3 manage.py test apps.production -v 1` passed: 77/77 OK.
- `python3 manage.py test apps.quotations apps.production -v 1` passed: 181/181 OK.
- Engine gates, `git diff --check`, and strict added-line secret scan passed.

## STATUS

PMO_ACCEPTED
