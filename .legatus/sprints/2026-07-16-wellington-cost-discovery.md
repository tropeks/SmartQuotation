# Sprint Contract — SQ-COST-0: Wellington Cost Discovery

**Date:** 2026-07-16 19:20 -03
**Branch:** docs/wellington-cost-discovery-*
**PMO:** Hermes/Spock
**Design partner:** ENGEMATEX / Wellington
**Stop condition:** `AWAIT_APPROVAL` before commit/merge.

---

## Objective

Consolidate Wellington's forwarded audio discovery into durable SmartQuotation product artifacts and prepare the next Legatus sprint plan for cost/margin/ETO evolution without losing or invalidating the current CPQ MVP.

## Scope

- Create a discovery MD with verbatim transcriptions and synthesized product decisions.
- Prepare sprint candidates for the cost-structure/margin roadmap.
- Launch an Opus probe to independently decompose the discovery into Legatus sprints/tasks.
- PMO-review the probe artifact before updating master docs (`PRODUCT_VISION.md`, `ROADMAP.md`) or coding.

## Non-goals

- No database migrations in this sprint.
- No changes to `pricing_engine/` or Django domain models yet.
- No modification of production settings/secrets/deploy files.
- No claim that ENGEMATEX historical prices are correct.
- No ERP/fiscal implementation in this sprint.

## Source artifacts

- `docs/discovery/wellington-costing-eto-sprints-2026-07-16.md`
- `docs/PRODUCT_VISION.md`
- `docs/ROADMAP.md`
- `docs/STATUS.md`
- `PROJECT_MAP.md`
- `CLAUDE.md`

## Expected worker/probe output

`/tmp/sq_wellington_cost_opus_probe.md` containing:

1. Sprint decomposition with priority/order.
2. Task list per sprint with acceptance criteria.
3. Existing-code reconciliation: what overlaps with `apps/cost_discovery`, `TenantCostChain`, `ActualRate`, `RateSuggestion`, `production` and pricing engine.
4. Risks/non-goals.
5. Recommended first implementable sprint after documentation alignment.

## Verification plan

- `git diff --check`
- Markdown files exist and include transcriptions.
- Probe launched and telemetry recorded.
- No sensitive files read/printed.

## PMO approval rule

Approve only after Hermes reads the Opus output and verifies that it does not duplicate existing SmartQuotation modules or propose scope explosion before the MVP/CPQ path remains protected.
