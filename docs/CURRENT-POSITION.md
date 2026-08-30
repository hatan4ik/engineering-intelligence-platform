# Current Position

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-30 against `origin/main` at `a0fdfd7` (the merge of PR #96); [Reference Implementation CI run 33305907816](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33305907816) passed for that revision. This is source-level CI evidence, not deployment, pilot, or production proof. |
| **Rule** | This is the one document that answers "where are we today". Every other planning document points here instead of restating a position. |

## Two yardsticks, stated explicitly

The repository is measured two ways, and the answers differ. Both are correct; quoting one as the
other is how a reference implementation gets mistaken for a product.

| Yardstick | What it counts | Position today |
|---|---|---|
| **Repository evidence** ([`../architecture/CAPABILITY-RECONCILIATION.md`](../architecture/CAPABILITY-RECONCILIATION.md), [`../architecture/MATURITY-SCORECARD.md`](../architecture/MATURITY-SCORECARD.md)) | Code, tests, and reference paths present at a revision | Reference implementations exist for most original capabilities; no capability row scores above 3.5 / 5 and none is production-capable |
| **Operational readiness** ([`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md), [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md)) | Retained evidence from a named environment | **No evidence record exists.** No environment, secrets, or pilot repository is configured; nothing is deployed or production-proven |

The [Runtime capability contract](RUNTIME-CAPABILITY-CONTRACT.md) checks the declared
code, Helm, Terraform, and current-state boundaries for each exposed capability. It is a
source-only, reference capability contract; it does not turn a rendered chart or Terraform
resource into deployment evidence.

## Roadmap stage

**Stage 0 — product truth and pilot foundation** of
[`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md).
Stage 1 begins when the shadow publish and closure workflows have executed against a real pull
request and the first observation record is retained.

| Stage 0 exit item | State |
|---|---|
| Product contracts under test | Done in this source contract — `product/pr_guardian/contracts.py`, `company_brain/product_contracts.py`, and their contract tests |
| Documentation links/anchors gated in CI | Done — `check_links.py`, `check_anchors.py` in `ci.yml` |
| Reference CI green on `main` | Done for the reviewed upstream baseline — [Reference Implementation CI run 33305907816](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33305907816) succeeded at `a0fdfd7`. This records checked source only; it is not deployment or pilot evidence. |
| Every route in the release image works or is declared | Done — `/healthz` reports capabilities; startup fails closed when a capability is enabled but incomplete |
| Release image import closure verified | Done — `app/import_closure.py` runs inside the built image in CI |
| Legacy/unreferenced code retired | Done — `src/`, `providers/` deleted |
| Reviewer labels created on the pilot repository | Done for this repository (`eip-pr-guardian/*`) |
| Named pilot repository with service owner and non-enforcement configuration | **Open** — none named |
| Baseline metrics collection plan | Target contract defined; **open** for a named pilot scope, owner, and retained measurements |

## Engineering built vs. evidence earned, per stage

Every stage has an engineering half (code, runners, triggers, workflows) and an evidence half
(a named repository, a real environment, retained outcomes, exercised drills). Reference paths
exist across Stages 1–6, but that is not the same as completing each stage's engineering exit
criteria: the current source still lacks, for example, a Guardrail SLM, per-principal rate/
concurrency enforcement, managed durable runtime proof, and real-data governance operations.
**No evidence half has been earned; no stage beyond Stage 0 has exited.** Every runner below
fails closed and names its missing configuration when the environment it needs is absent.

| Stage | Engineering present (this revision) | Evidence still required before exit |
|---|---|---|
| 1 — shadow PR Guardian | Report computes a real `decision` (`shadow-only` / `advisory-candidate`) with `blocking_authorized` fixed false; calibration section (recommendation only); weekly report workflow. The [latest closed-PR write attempt](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33156433573) failed with GitHub `403` before artifact upload. This revision makes the retained outcome artifact fail-soft when only the calibration comment is refused, but that behavior remains unproven on GitHub — [`PR-GUARDIAN-SHADOW-REPORT.md`](PR-GUARDIAN-SHADOW-REPORT.md) | Verify least-privilege outcome retention on a real closed PR, resolve the comment permission/trust issue, then collect ≥30 observations, ≥30 reviewer classifications, ≥5 confirmed risks, precision ≥0.50, recall ≥0.80 on a named external repository |
| 2 — advisory + knowledge plane | `ingestion/` has a runtime trigger (`scripts/ingest_repository.py`, `knowledge-ingest.yml`); integration proof fails closed on any of its 14 required variables and runs on a schedule when an `integration` environment exists; evidence registry (`docs/evidence/`, `scripts/record_evidence.py`) — [`KNOWLEDGE-INGEST-RUNBOOK.md`](KNOWLEDGE-INGEST-RUNBOOK.md), [`evidence/README.md`](evidence/README.md) | An Azure environment with secrets; 2–3 repositories indexed; the strategy's Advisory gate; the first retained evidence record |
| 3 — selective enforcement + Architecture Guard | Repository-owned `.eip/pr-guardian.json` selects `shadow` / `advisory` / `enforce`; one deterministic rule with owner approval, expiry, waivers, and `EIP_PR_GUARDIAN_KILL_SWITCH`; the trusted publisher is the only writer and re-derives the condition; Architecture Guard on the PR path with honest coverage counts — [`PR-GUARDIAN-REPOSITORY-CONFIG.md`](PR-GUARDIAN-REPOSITORY-CONFIG.md) | A service owner enabling `enforce` in their repository, a monitored false-negative rate over a retained window, CODEOWNERS on `.github/workflows/` and `.eip/` |
| 4 — operational intelligence L1/L2 | `POST /v1/events/deployment` and `/v1/events/incident` behind a shared secret; L2 proposals with `requires_human` fixed true; CLIs over fixture evidence — [`OPERATIONS-INTELLIGENCE-RUNBOOK.md`](OPERATIONS-INTELLIGENCE-RUNBOOK.md) | Azure Monitor / ADO wired to a real service; owner-confirmed outcomes; measured L2 acceptance |
| 5 — rehearsed L3 | `temporal` control-plane mode is constructible over Cosmos state and a hash-chain-compatible Cosmos audit log; opt-in `eip.remediation.v1` workflow with a plan-hash-bound approval signal; soak, readiness, and L3 exercise runners (simulated runs are graded `rehearsal`) — [`L3-REHEARSAL-RUNBOOK.md`](L3-REHEARSAL-RUNBOOK.md), [`TEMPORAL-WORKER-RUNBOOK.md`](TEMPORAL-WORKER-RUNBOOK.md) | A managed Temporal + Cosmos environment; the nine certification items exercised on a real cluster with retained evidence; 168h soak |
| 6 — scoped L4 | Certification scope and material-inputs hashes; eligibility that excludes rehearsal-graded exercises; the executor and the OPA bundle refuse L4 without a matching, unexpired record; `EIP_AUTONOMY_KILL_SWITCH` — [`L4-PROMOTION-RUNBOOK.md`](L4-PROMOTION-RUNBOOK.md) | Everything in Stage 5, per service + environment + runbook; nothing is certified |

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
