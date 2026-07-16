# Evidence — SQ-COST-2 Price Provenance

**Started:** 2026-07-16
**PMO:** Hermes/Spock
**Execution backend:** Claude Agent SDK Python
**Worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-2`
**Branch:** `sdk/sq-cost-2-pricing-basis-20260716-200943`
**Status:** PMO_APPROVED_FOR_COMMIT

---

## PLAN

- Launch SDK worker in isolated worktree.
- Enforce TDD for `Quotation.pricing_basis`.
- Verify no pricing math changes.
- PMO review before commit/PR/merge.

## SDK TELEMETRY

- Worker process `proc_c3ec073b69b7` exited with code 1 because Claude Code returned `Reached maximum number of turns (40)`.
- PMO classified this as a harness/turn-budget stop, not an implementation failure: code artifacts, migration, tests, and docs were present for independent verification.
- PMO continued verification manually rather than relaunching immediately.

## RED

SDK worker added focused tests before implementation for:

- `PricingBasisTests.test_nova_cotacao_default_referencial`
- `PricingBasisTests.test_label_humano_provenance`
- `PricingBasisTests.test_pricing_basis_nao_e_campo_do_form_data_sheet`
- `PricingBasisTests.test_recompute_nao_altera_totais_calculados`
- `PricingBasisMigrationTests.test_migration_backfill_pricing_basis_referencial`

## GREEN

Implemented additive provenance slice:

- `Quotation.PRICING_BASIS` choices:
  - `referencial` → `Referencial`
  - `validado_custo` → `Validado por custo`
- `Quotation.pricing_basis` as `CharField(... default="referencial", editable=False)`.
- Migration `quotations.0008_quotation_pricing_basis` with additive default/backfill.
- Admin list/filter/read-only display for `pricing_basis`.
- Detail template badge/label in summary and price section.
- No pricing engine changes.

## VERIFY

Commands run by PMO:

- `cd backend && python3 manage.py makemigrations --check --dry-run` → `No changes detected`.
- `cd backend && python3 manage.py test apps.quotations.tests.PricingBasisTests -v 2` → 4 tests OK.
- `cd backend && python3 manage.py test apps.quotations.tests.PricingBasisMigrationTests -v 2` → 1 test OK.
- `cd backend && ./.venv/bin/python manage.py check` → OK.
- `cd backend && ./.venv/bin/python manage.py makemigrations --check --dry-run` → `No changes detected`.
- `cd backend && ./.venv/bin/python manage.py test apps.quotations -v 1` → 104 tests OK.
- `python3 -m tests.validate_feixe_completo` → gate OK, delta -2.9% dentro de ±10%.
- `python3 -m tests.validate_permutador_completo` → gate OK for BEM, BEU, OF3683.
- `git diff --check` → clean.
- Added-line secret scan → `OK_NO_SECRET_PATTERNS`.

Note: running quotation tests with system `python3` failed with `ModuleNotFoundError: whitenoise` because the command used the wrong environment; rerunning with `backend/.venv/bin/python` passed.

## ARTIFACTS

- Sprint contract: `.legatus/sprints/2026-07-16-sq-cost-2-pricing-basis.md`
- Evidence: `.legatus/evidence/2026-07-16-sq-cost-2-pricing-basis.md`
- Model: `backend/apps/quotations/models.py`
- Migration: `backend/apps/quotations/migrations/0008_quotation_pricing_basis.py`
- Admin: `backend/apps/quotations/admin.py`
- Detail UI: `backend/apps/quotations/templates/quotations/detail.html`
- Tests: `backend/apps/quotations/tests.py`

## PMO REVIEW

Accepted for commit:

- Scope is additive and matches SQ-COST-2.
- Existing/new quotations default to `referencial`.
- Users cannot manually claim `validado_custo` via normal data sheet form.
- `validado_custo` remains reserved for future CostStructure/minimum-price derivation.
- No price formula or engine path changed.

## STATUS

PMO_APPROVED_FOR_COMMIT
