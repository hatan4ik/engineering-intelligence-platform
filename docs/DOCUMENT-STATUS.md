# Documentation Status and Freshness

| | |
|---|---|
| **Status** | Current documentation-governance policy |
| **Owner** | Platform Engineering |
| **Rule** | No document may imply a stronger implementation or production state than its evidence supports |

## Classification

| Label | Meaning | Use for decisions? |
|---|---|---|
| **Current design** | Approved target architecture and invariants | Yes, for intended design decisions |
| **Current implementation state** | What is present in the repository or a named environment at the stated revision | Yes, subject to linked evidence |
| **Target proposal** | Planned architecture or roadmap, not an implementation claim | Yes, for planning only |
| **Historical review** | Point-in-time analysis retained for context | No; use its stated date/revision only |
| **Generated evidence** | Reproducible report/artifact with scope and expiry | Yes, only for the claim and scope recorded |

## Required header fields

Any current architecture, readiness, scorecard, or capability document must state:

1. classification and owner;
2. reviewed date and, for implementation claims, commit or environment;
3. the authoritative current-state and production-evidence documents; and
4. whether its assertions are implemented, deployed, or production-proven.

Use links to tests, IaC, dashboards, signed artifacts, or evidence IDs for claims that affect
security, autonomy, reliability, quality, or economics. “Implemented” alone never means
production-certified.

## Canonical documents

| Document | Classification | Authority |
|---|---|---|
| [`../architecture/design.md`](../architecture/design.md) | Current design | System invariants and target architecture |
| [`../architecture/capability-reconciliation.md`](../architecture/capability-reconciliation.md) | Current implementation state | Reference implementation capability status and queue |
| [`../architecture/non-functional-requirements.md`](../architecture/non-functional-requirements.md) | Current design | Operational, data, and safety requirements |
| [`PRODUCT-STRATEGY.md`](PRODUCT-STRATEGY.md) | Current product decision | First product wedge and expansion gates |
| [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) | Current evidence contract | What must be retained to support a promotion claim |
| [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md) | Target promotion plan | Required sequence and gates |
| [`../architecture/maturity-scorecard.md`](../architecture/maturity-scorecard.md) | Current repository assessment | Directional maturity, never production proof |
| [`../architecture/alignment-review.md`](../architecture/alignment-review.md) | Historical review | Pre-corrective baseline only |
| [`architecture-review-2026-08.md`](architecture-review-2026-08.md) | Historical review | Point-in-time assessment only |

## Review cadence

- Update implementation state and scorecard in the same pull request as a material capability
  change.
- Update target design and NFRs before a change that affects trust boundaries, data handling,
  production policy, or autonomy.
- Reclassify a review as historical when later work invalidates its observed state.
- Review active documents at least quarterly; do not renew a status merely by changing its date.
