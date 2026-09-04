# Current Position

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-03 against `origin/main` at `f556e16` (the merge of <span title="Pull Request">PR</span> #112); [Reference Implementation <span title="Continuous Integration">CI</span> run 33612719371](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33612719371) passed for that revision. This is source-level <span title="Continuous Integration">CI</span> evidence, not deployment, pilot, or production proof. |
| **Rule** | This is the one document that answers "where are we today". Every other planning document points here instead of restating a position. |
| **Documentation governance** | [`DOCUMENT-STATUS.md`](DOCUMENT-STATUS.md) records document authority, lifecycle, and review dispositions. |
| **Terminology** | [Company Brain Glossary](GLOSSARY.md) |

## Two yardsticks, stated explicitly

The repository is measured two ways, and the answers differ. Both are correct; quoting one as the
other is how a reference implementation gets mistaken for a product.

| Yardstick | What it counts | Position today |
|---|---|---|
| **Repository evidence** ([`../architecture/CAPABILITY-RECONCILIATION.md`](../architecture/CAPABILITY-RECONCILIATION.md), [`../architecture/MATURITY-SCORECARD.md`](../architecture/MATURITY-SCORECARD.md)) | Code, tests, and reference paths present at a revision | Reference implementations exist for most Company Brain capabilities; no capability row scores above 3.5 / 5 and none is production-capable |
| **Operational readiness** ([`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md), [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md)) | Retained evidence from a named environment | **No evidence record exists.** No named environment, external secret configuration, or pilot repository is recorded here; this checkout cannot support a deployment or production-proof claim |

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
| Product contracts under test | Done in this source contract — <span title="Pull Request">PR</span> Guardian, its shadow-pilot/readiness/bootstrap/promotion-review contracts, and `company_brain/product_contracts.py` have bounded, <span title="Continuous Integration">CI</span>-covered records; this is not pilot evidence |
| Documentation links/anchors gated in <span title="Continuous Integration">CI</span> | Done — `check_links.py`, `check_anchors.py` in `ci.yml` |
| Reference <span title="Continuous Integration">CI</span> green on `main` | Done for the reviewed upstream baseline — [Reference Implementation <span title="Continuous Integration">CI</span> run 33612719371](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33612719371) succeeded at `f556e16`. This records checked source only; it is not deployment or pilot evidence. |
| Every route in the release image works or is declared | Done — `/healthz` reports capabilities; startup fails closed when a capability is enabled but incomplete |
| Release image import closure verified | Done — `app/import_closure.py` runs inside the built image in CI |
| Legacy/unreferenced code retired | Done — `src/`, `providers/` deleted |
| Target-pilot reviewer labels and non-enforcing configuration | **Open** — the required label names and shadow-only configuration contract are defined, but no target pilot repository is named or configured |
| Shadow-pilot onboarding, readiness, bootstrap, and promotion-review validators | Done in source — the validators and read-only readiness/bootstrap tools bind a planned target scope and generated feedback report to declared external evidence references; they cannot enable a pilot or attest that evidence exists |
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
| 1 — shadow <span title="Pull Request">PR</span> Guardian | The shadow report computes `shadow-only` / `advisory-candidate`, fingerprints its normalized closure-record export, and fixes `blocking_authorized` false. Target-repository manifest validation, read-only readiness, and bootstrap tools plus an expiring promotion-review packet validator make the intended controls explicit; none invokes GitHub or changes mode — [`PR-GUARDIAN-PILOT-READINESS.md`](PR-GUARDIAN-PILOT-READINESS.md), [`PR-GUARDIAN-SHADOW-PILOT.md`](PR-GUARDIAN-SHADOW-PILOT.md), [`PR-GUARDIAN-PROMOTION-REVIEW.md`](PR-GUARDIAN-PROMOTION-REVIEW.md) | Name and configure a target repository, verify least-privilege retention on a real closed <span title="Pull Request">PR</span>, export artifacts to an approved immutable system, then collect ≥30 observations, ≥30 reviewer classifications, ≥5 confirmed risks, precision ≥0.50, recall ≥0.80, and independent post-merge correlation |
| 2 — advisory + knowledge plane | `ingestion/` has a runtime trigger (`scripts/ingest_repository.py`, `knowledge-ingest.yml`); the integration proof is manual-only and runs its private probe only after explicit confirmation on the approved private runner; evidence registry mechanics exist at `docs/evidence/` and `scripts/record_evidence.py` — [`INTEGRATION-PROOF-RUNBOOK.md`](INTEGRATION-PROOF-RUNBOOK.md), [`evidence/README.md`](evidence/README.md) | An Azure environment with secrets; 2–3 repositories indexed; a human advisory decision under the strategy gate; the first retained evidence record |
| 3 — selective enforcement + Architecture Guard | Repository-owned `.eip/pr-guardian.json` selects `shadow` / `advisory` / `enforce`; one deterministic rule with owner approval, expiry, waivers, and `EIP_PR_GUARDIAN_KILL_SWITCH`; the trusted publisher is the only writer and re-derives the condition; Architecture Guard on the <span title="Pull Request">PR</span> path with honest coverage counts — [`PR-GUARDIAN-REPOSITORY-CONFIG.md`](PR-GUARDIAN-REPOSITORY-CONFIG.md) | A service owner enabling `enforce` in their repository, a monitored false-negative rate over a retained window, CODEOWNERS on `.github/workflows/` and `.eip/` |
| 4 — operational intelligence L1/L2 | `POST /v1/events/deployment` and `/v1/events/incident` behind a shared secret; L2 proposals with `requires_human` fixed true; CLIs over fixture evidence — [`OPERATIONS-INTELLIGENCE-RUNBOOK.md`](OPERATIONS-INTELLIGENCE-RUNBOOK.md) | Azure Monitor / ADO wired to a real service; owner-confirmed outcomes; measured L2 acceptance |
| 5 — rehearsed L3 | `temporal` control-plane mode is constructible over Cosmos state and a hash-chain-compatible Cosmos audit log; opt-in `eip.remediation.v1` workflow with a plan-hash-bound approval signal; soak, readiness, and L3 exercise runners (simulated runs are graded `rehearsal`) — [`L3-REHEARSAL-RUNBOOK.md`](L3-REHEARSAL-RUNBOOK.md), [`TEMPORAL-WORKER-RUNBOOK.md`](TEMPORAL-WORKER-RUNBOOK.md) | A managed Temporal + Cosmos environment; the nine certification items exercised on a real cluster with retained evidence; 168h soak |
| 6 — scoped <span title="Autonomy Level 4 — bounded autonomous">L4</span> | Certification scope and material-inputs hashes; eligibility that excludes rehearsal-graded exercises; the executor and the <span title="Open Policy Agent">OPA</span> bundle refuse <span title="Autonomy Level 4 — bounded autonomous">L4</span> without a matching, unexpired record; `EIP_AUTONOMY_KILL_SWITCH` — [`L4-PROMOTION-RUNBOOK.md`](L4-PROMOTION-RUNBOOK.md) | Everything in Stage 5, per service + environment + runbook; nothing is certified |

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
