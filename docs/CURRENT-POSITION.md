# Current Position

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 at the revision that merged this file |
| **Rule** | This is the one document that answers "where are we today". Every other planning document points here instead of restating a position. |

## Two yardsticks, stated explicitly

The repository is measured two ways, and the answers differ. Both are correct; quoting one as the
other is how a reference implementation gets mistaken for a product.

| Yardstick | What it counts | Position today |
|---|---|---|
| **Repository evidence** ([`../architecture/CAPABILITY-RECONCILIATION.md`](../architecture/CAPABILITY-RECONCILIATION.md), [`../architecture/MATURITY-SCORECARD.md`](../architecture/MATURITY-SCORECARD.md)) | Code, tests, and reference paths present at a revision | Reference implementations exist for most original capabilities; no capability row scores above 3.5 / 5 and none is production-capable |
| **Operational readiness** ([`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md), [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md)) | Retained evidence from a named environment | **No evidence record exists.** No environment, secrets, or pilot repository is configured; nothing is deployed or production-proven |

## Roadmap stage

**Stage 0 — product truth and pilot foundation** of
[`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md).
Stage 1 begins when the shadow publish and closure workflows have executed against a real pull
request and the first observation record is retained.

| Stage 0 exit item | State |
|---|---|
| Product contracts under test | Done — `product/pr_guardian/contracts.py`, `tests/test_pr_guardian_contracts.py` |
| Documentation links/anchors gated in CI | Done — `check_links.py`, `check_anchors.py` in `ci.yml` |
| Reference CI green on `main` | **Open** — 13 tests currently fail after the partial async Temporal migration changed synchronous workflow/service APIs without updating callers and tests; `main` protection remains a repository setting to enable |
| Every route in the release image works or is declared | Done — `/healthz` reports capabilities; startup fails closed when a capability is enabled but incomplete |
| Release image import closure verified | Done — `app/import_closure.py` runs inside the built image in CI |
| Legacy/unreferenced code retired | Done — `src/`, `providers/` deleted |
| Reviewer labels created on the pilot repository | Done for this repository (`eip-pr-guardian/*`) |
| Named pilot repository with service owner and non-enforcement configuration | **Open** — none named |
| Baseline metrics collection plan | **Open** |

## How the planning schemes map

Only the roadmap stages sequence work. The other schemes describe *what kind* of thing a stage
produces, not *when*.

| Roadmap stage | Product trust stage ([strategy](PRODUCT-STRATEGY.md)) | Autonomy level ([design](../architecture/design.md)) | Scorecard target for rows it advances |
|---|---|---|---|
| Stage 0 | pre-shadow | L0 | 3.0 reference |
| Stage 1 | Shadow | L1 | 3.0 → 3.5 |
| Stage 2 | Advisory | L1 | 4.0 production-capable for PR Guardian, gateway, ingestion |
| Stage 3 | Selective enforcement | L1 | 4.0 → 4.5 |
| Stage 4 | Expand to incident intelligence | L1 → L2 | 3.5 → 4.0 for operational rows |
| Stage 5 | — | L3 (scoped) | 4.0 for control-plane rows; L3 certification 4.0 |
| Stage 6 | — | L4 (scoped) | 5.0 only with retained evidence |

Milestone names (`M2`, `M3`) are historical records of reference slices and do not sequence
future work. The P0–P4 labels in the historical alignment review are correction waves; the P0–P3
labels in the August architecture review are finding severities. Neither is a roadmap stage.

## Update rule

Change this file in the same pull request as any change that moves a Stage 0–6 exit item, and
record the revision. Do not renew the reviewed date without re-checking every row.
