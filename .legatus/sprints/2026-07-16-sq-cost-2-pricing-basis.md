# Sprint Contract — SQ-COST-2: Price provenance (`referencial` vs `validado_custo`)

**Date:** 2026-07-16  
**Backend:** Claude Agent SDK Python  
**PMO:** Hermes/Spock  
**Repo/worktree:** `/home/rcosta00/dev/SmartQuotation-sdk-sq-cost-2`  
**Branch:** `sdk/sq-cost-2-pricing-basis-20260716-200943`  
**Base:** `main` after PR #69 (`ea01829`)

---

## Mission

Implement the first production slice of cost provenance without changing price math:

- Add `Quotation.pricing_basis` enum with default/backfill `referencial`.
- Expose a read-only/admin-visible label/badge for `referencial` vs `validado_custo`.
- Ensure existing and newly created quotations remain `referencial` until a future CostStructure/minimum-price sprint qualifies them as `validado_custo`.
- Add tests proving no calculated price changes.

## Doctrine

Legatus remains source of truth. Claude Agent SDK is only the worker backend. Use strict TDD:

1. RED: write focused failing tests first.
2. GREEN: implement minimal code/migration/UI/admin wiring.
3. REFACTOR: clean only after tests pass.

## Scope

Allowed:
- Django model/admin/form/template/view changes needed for `pricing_basis` visibility.
- Migration for additive field/default/backfill.
- Tests for default/backfill/label/no price movement.
- Docs/evidence updates.

Forbidden:
- Overhead/CostStructure implementation.
- Changing pricing formulas or engine outputs.
- Reading `.env`/secrets/deploy credentials.
- Production deploy.
- Commit/PR by worker; PMO does that after review.

## Acceptance

- Test proves new `Quotation` defaults to `referencial`.
- Migration/backfill keeps existing records as `referencial`.
- UI/admin exposes provenance label without making it user-editable as arbitrary truth.
- No price calculation changes; existing engine/Django tests pass.
- `git diff --check` clean.
- No secrets touched.

## Stop condition

Worker stops at `AWAIT_PMO_REVIEW`.
