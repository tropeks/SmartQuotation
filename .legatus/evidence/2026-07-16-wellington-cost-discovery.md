# Evidence — SQ-COST-0 Wellington Cost Discovery

**Started:** 2026-07-16 19:20 -03
**PMO:** Hermes/Spock

## PLAN

- Capture the Wellington/Romulo audio discovery into a durable document.
- Attach verbatim transcripts.
- Prepare sprint candidates.
- Launch Opus probe for independent sprint/task decomposition.
- Verify files and report telemetry.

## RED

Not applicable yet: documentation/discovery sprint. Future implementation sprints must start with RED tests.

## GREEN

- Created `docs/discovery/wellington-costing-eto-sprints-2026-07-16.md` with verbatim transcripts, synthesis, product decisions, and preliminary sprint candidates.
- Created `.legatus/sprints/2026-07-16-wellington-cost-discovery.md` as the current PMO sprint contract.
- Launched Opus probe in background process `proc_2c5dc16ebdda` / PID `1404738`; it completed normally with exit code 0.
- Reviewed `/tmp/sq_wellington_cost_opus_probe.md` (302 lines). Key PMO decisions accepted for docs:
  - preserve CPQ MVP; layer cost/margin intelligence;
  - add `referencial` vs `validado por custo` as product language;
  - correct stale claim that the engine does not expose estimated hours;
  - treat fixed cost/overhead as a separate future line (`overhead_*`/`custo_estrutura_*`), not `custo_fixo` due to naming collision in `wbs.py`;
  - defer competitive “vitória perigosa” analytics until cost validation is trustworthy.
- Updated master docs for SQ-COST-0:
  - `docs/PRODUCT_VISION.md`
  - `docs/ROADMAP.md`
  - `docs/STATUS.md`
  - `PROJECT_MAP.md`

## VERIFY

- `git diff --check` passed after doc updates.
- Stale-hours grep passed: `grep -RInE 'não expõe horas|motor não expõe horas|não horas\)' docs PROJECT_MAP.md` returned no hits.
- Changed tracked doc stat after SQ-COST-0 edits:
  - `PROJECT_MAP.md`: 3-line diff
  - `docs/PRODUCT_VISION.md`: 20-line diff
  - `docs/ROADMAP.md`: 3-line diff
  - `docs/STATUS.md`: 5-line diff
- Artifact line counts:
  - discovery doc: 280 lines
  - Opus probe: 302 lines
  - sprint contract: 58 lines
  - evidence file: updated in this section

## REVIEW

PMO review complete for SQ-COST-0 documentation slice. Status is `AWAIT_APPROVAL` before commit/merge and before moving to SQ-COST-1 implementation/spec work.

## ARTIFACTS

- `docs/discovery/wellington-costing-eto-sprints-2026-07-16.md`
- `.legatus/sprints/2026-07-16-wellington-cost-discovery.md`
- `.legatus/evidence/2026-07-16-wellington-cost-discovery.md`
- `/tmp/sq_wellington_cost_opus_probe.md` (expected)
- `/tmp/sq_wellington_cost_opus_probe.log` (raw background log)

## STATUS

AWAIT_APPROVAL
