# Evidence — SQ-COST-3 Hours Decomposition

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-3`
**Branch:** `sdk/sq-cost-3-hours-decomposition-20260716-203812`
**Status:** AWAIT_PMO_REVIEW

---

## PLAN

- Launch SDK worker in isolated worktree.
- Enforce TDD for budgeted-vs-actual hours in production observations.
- Preserve pricing engine and Welford aggregator behavior unless tests demand additive changes.
- PMO review before commit/PR/merge.

## Environment note (infra, not code)

Docker on this host is currently broken for **new/restarted** containers: AppArmor's
`docker-default` profile denies `socket(AF_UNIX, ..., create)` for any freshly started
container process (confirmed via `dmesg`/`journalctl -k` — `apparmor="DENIED" operation="create"
class="net" ... family="unix"`, hitting `postgres`, `celery`, `curl`, `python` alike, not
specific to this worktree). The sibling worktree's own `db` container
(`smartquotation-sdk-sq-cost-2-db-1`) is crash-looping with the same error. This blocked
`docker compose up -d db redis` from the sprint's documented dev flow.
**Workaround (test-only, not part of the diff):** used the host's native `postgresql@17-main`
service; created an isolated `smartquotation_sqcost3` DB (owner `sq`, same credentials as
`backend/.env.example`) so as not to collide with any concurrent worker's `smartquotation` /
`test_smartquotation` databases. `backend/.env` (gitignored, not part of the diff) points
`POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=smartquotation_sqcost3`. Redis reused
the already-running container on `6380`. Also `pip install --user --break-system-packages -r
requirements/development.txt` to pick up `whitenoise` (missing from the shared user
site-packages, unrelated to this sprint). None of this touched `.env`/secrets belonging to
another project or environment — flagging for PMO awareness since it deviates from the
documented Docker flow; the host-level AppArmor issue is out of scope for this sprint and
should be triaged separately (affects all worktrees on this host, not introduced by this task).

## RED

Added `HorasDecompositionTests` to `backend/apps/production/tests.py` (5 tests) before touching
any production code:

- `test_fechamento_grava_estimated_hh_do_ofoperation`
- `test_delta_horas_pct_positivo_quando_real_maior_que_estimado`
- `test_delta_horas_pct_negativo_quando_real_menor_que_estimado`
- `test_delta_horas_pct_none_quando_estimated_hh_zero_sem_crash`
- `test_regressao_observed_rate_e_actual_rate_inalterados` (regression guard, written up front)

Ran `python3 manage.py test apps.production -v 1` against pre-change code:

```
ERROR: test_delta_horas_pct_negativo_quando_real_menor_que_estimado
  AttributeError: 'ProductionObservation' object has no attribute 'delta_horas_pct'
ERROR: test_delta_horas_pct_none_quando_estimated_hh_zero_sem_crash
  AttributeError: 'ProductionObservation' object has no attribute 'estimated_hh'
ERROR: test_delta_horas_pct_positivo_quando_real_maior_que_estimado
  AttributeError: 'ProductionObservation' object has no attribute 'delta_horas_pct'
ERROR: test_fechamento_grava_estimated_hh_do_ofoperation
  AttributeError: 'ProductionObservation' object has no attribute 'estimated_hh'
Ran 68 tests in 51.953s
FAILED (errors=4)
```

4/4 new-field tests failed as expected (RED). The 5th (regression) test passed even
pre-change, as intended — it only pins down existing behavior.

## GREEN

Minimal additive implementation:

1. `backend/apps/production/models.py` — `ProductionObservation` gains:
   - `estimated_hh` (`DecimalField`, `max_digits=8, decimal_places=2, default=0`) — mirrors
     `OFOperation.horas_hh` precision.
   - `delta_horas_pct` (`DecimalField`, `max_digits=10, decimal_places=2, null=True, blank=True`)
     — nullable, documented via `help_text`.
2. `backend/apps/production/migrations/0008_productionobservation_delta_horas_pct_and_more.py`
   — pure `AddField` × 2, no data migration, no change to existing columns.
3. `backend/apps/production/services.py::_close_out_observations` — snapshots
   `estimated_hh = Decimal(op.horas_hh)` at close-out and computes
   `delta_horas_pct = (actual_hh − estimated_hh) / estimated_hh × 100` **only when
   `estimated_hh > 0`**; otherwise leaves it `None` (zero-guard, no div/0). `observed_rate` /
   `_update_actual_rate` (Welford) untouched — not read, not written, not reordered.

Ran `python3 manage.py test apps.production -v 1` after the change:

```
Ran 68 tests in 55.389s
OK
```

All 68 production tests pass, including the 4 new RED tests (now GREEN) and the regression test.

## VERIFY

| Command | Result |
|---|---|
| `python3 manage.py makemigrations --check --dry-run` | `No changes detected` — model/migration in sync |
| `python3 manage.py test apps.production -v 1` | `OK` (68/68) |
| `python3 manage.py test apps.quotations apps.production -v 1` | `OK` — see below |
| `python3 -m tests.validate_feixe_completo` | `GATE OK: delta -2.9% dentro de ±10%, 0 erros.` (unchanged from baseline, `pricing_engine` untouched) |
| `python3 -m tests.validate_permutador_completo` | `GATE OK` — BEM Δ+0.00%, BEU Δ+0.00%, OF3683 Δ+0.15% (unchanged) |
| `git diff --check` | clean, no output |
| Added-line secret scan (`git diff \| grep -i password\|secret\|token\|api[_-]key\|BEGIN...\|AKIA`) | no hits |

`apps.quotations apps.production` combined run output:

```
Found 172 test(s).
Ran 172 tests in 156.537s
OK
```

## Files changed

- `backend/apps/production/models.py` — additive fields on `ProductionObservation`.
- `backend/apps/production/services.py` — snapshot + delta computation in `_close_out_observations`.
- `backend/apps/production/migrations/0008_productionobservation_delta_horas_pct_and_more.py` — new migration.
- `backend/apps/production/tests.py` — `HorasDecompositionTests` (5 tests: RED→GREEN + 1 regression).
- `.legatus/evidence/2026-07-16-sq-cost-3-hours-decomposition.md` (this file).

## Not implemented (explicitly out of scope this sprint)

- No admin/list/detail UI exposure of `estimated_hh`/`delta_horas_pct`. The production app's
  `templates/production/detail.html` renders per-operation `horas_hh`/`actual_hh` already but
  has no observation-level table; adding a read-only view of "operations with the largest
  deviation" (mentioned in the spec's SQ-COST-3 acceptance) would touch views/templates beyond
  what a focused RED test demanded here. Flagging for PMO: worth a fast follow-up sprint once
  this data model is accepted, rather than bundling UI risk into this additive slice.
- No `estimated_hm` field — `_close_out_observations`/`observed_rate` never read `horas_hm` or
  `actual_hm` today, so adding it would be speculative surface with no test driving it (avoided
  per TDD discipline: minimal code to pass a real failing test).
- `_update_actual_rate` (Welford) and `RateSuggestion` untouched, as mandated — `delta_horas_pct`
  is stored but not yet consumed to "route" the signal (Section 6 of the SQ-COST-1 spec describes
  that routing as a next-sprint concern).

## PMO REVIEW

Accepted by Hermes/Spock PMO after independent verification.

Additional PMO notes:

- Worker reached `AWAIT_PMO_REVIEW` with coherent artifacts and no commit/push.
- PMO inspected `models.py`, `services.py`, migration and tests. The implementation is additive and keeps `_update_actual_rate` / Welford untouched.
- PMO reran checks independently after dropping only the stale local `test_smartquotation` database left by the prior interrupted Django test run. This did not touch production or SmartQuotation runtime databases.
- `python3 manage.py check` and `python3 manage.py makemigrations --check --dry-run` passed.
- `python3 manage.py test apps.production -v 1` passed: 68/68 OK.
- `python3 manage.py test apps.quotations apps.production -v 1` passed: 172/172 OK.
- Engine gates and added-line secret scan passed.

## STATUS

PMO_ACCEPTED
