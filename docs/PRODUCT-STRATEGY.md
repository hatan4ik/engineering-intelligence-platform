# Product Strategy — Initial Wedge

| | |
|---|---|
| **Status** | Current product decision — reference implementation, not production proof |
| **Primary owner** | Engineering Intelligence lead + Developer Experience |
| **Decision date** | 2026-08-26 |
| **Related delivery status** | [`../architecture/CAPABILITY-RECONCILIATION.md`](../architecture/CAPABILITY-RECONCILIATION.md) |

## Decision

The first product is **PR Guardian for Azure engineering teams**, not a general-purpose
engineering chatbot and not production self-healing.

It produces evidence-backed, reviewable change-risk feedback on pull requests for one or two
selected repositories. It starts in shadow mode and is non-blocking until measured outcomes
justify a narrowly scoped enforcement decision.

The broader platform architecture remains the target state. It is not a commitment to ship all
planes before this product has demonstrated value and safety.

## Customer and job to be done

| Item | Decision |
|---|---|
| **Primary user** | Author, reviewer, tech lead, and service owner of an Azure-hosted engineering service |
| **Job** | Before merge, understand material blast radius, policy/architecture concerns, relevant prior regressions, and the exact follow-up needed |
| **User outcome** | Faster, more reliable reviews with fewer missed high-risk changes and less low-value review noise |
| **Economic buyer** | VP Engineering / CTO accountable for delivery reliability and engineering throughput |
| **Initial surface** | GitHub pull-request check/comment; portal and chat are secondary evidence views, not the product entry point |

## Product contract

For an eligible pull request, PR Guardian may:

1. map changed paths to services and dependency blast radius;
2. apply deterministic risk factors and show their evidence;
3. link authorized source evidence and state uncertainty explicitly;
4. recommend tests, reviewers, or a follow-up ticket/plan; and
5. publish a reviewable result with correlation ID and audit trail.

It must not claim that a merge is safe, mutate production, grant itself permissions, or turn an
uncalibrated score into a blocking control.

## Scope and non-goals

| In scope for the first product | Explicitly deferred |
|---|---|
| GitHub PR event, service mapping, deterministic risk score, evidence comment/check, feedback capture | General engineering chat or IDE productization |
| One or two repositories with named service owners | Organization-wide source ingestion and cross-cloud expansion |
| Shadow-mode calibration and a human-reviewed enforcement proposal | Incident automation, corrective PR generation, L3 remediation, or L4 autonomy |
| Authorized retrieval and auditability required by the system design | Claims of saved engineering capacity before measured adoption/outcomes exist |

## Success and expansion gates

The product owner, service owners, Security, and Developer Experience must agree the numeric
thresholds before enabling a blocking check. The thresholds are repository-specific; they are not
copied from a generic platform target.

| Stage | Required evidence | Decision |
|---|---|---|
| **Shadow** | Representative PR sample, reviewer disposition for every material finding, false-positive/false-negative analysis, citation review, ACL isolation checks, latency/cost distribution | Continue only if the feedback is useful and safe enough to improve |
| **Advisory** | Sustained precision and acceptance above the pre-agreed threshold; no unresolved high-severity ACL, provenance, or evidence defect | Enable a non-blocking check for the certified repository scope |
| **Selective enforcement** | Service-owner approval, calibrated high-severity threshold, documented waiver/expiry path, rollback switch, and monitored false-negative rate | Block only the narrow, deterministic condition that has proved reliable |
| **Expand to incident intelligence** | PR Guardian outcome retained over a meaningful window and a demonstrated need for operational correlation | Start L1/L2 incident intelligence; do not inherit mutation authority |

Every result must be labelled **measured**, **derived**, or **modeled**. An LLM-derived
recommendation cannot satisfy a deterministic enforcement rule by itself.

## Product metrics

The baseline is collected before a target is committed. Review weekly by repository and service,
not as a single blended platform average.

- PR Guardian precision, false-positive rate, and observed false-negative rate by severity.
- Reviewer acceptance/action rate and time to disposition.
- Citation correctness and insufficient-evidence/refusal correctness.
- Review-cycle time and rework attributable to findings.
- Query/check latency, token/search cost per accepted finding, and cost per active repository.
- Unauthorized retrieval blocks, policy failures, overrides, and kill-switch activations.

## Stop conditions

Pause expansion and return to advisory or shadow mode after any material ACL breach, unsupported
high-severity finding, unbounded cost/latency regression, provenance/audit gap, or materially
worse reviewer experience. No status or maturity score substitutes for this decision.

## Relationship to the roadmap

[`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md)
describes the target sequencing. Its Phase 2 PR Intelligence exit is the next product decision
point. L3/L4 work remains governed by the production-proof and certification documents and is not
an implied follow-on to PR Guardian adoption.
