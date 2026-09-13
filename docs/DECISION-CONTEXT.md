# Company Brain Decision Context

| | |
|---|---|
| **Classification** | Reference contract — principal-scoped explanation, not a public API, pilot, or action authority |
| **Owner** | Engineering Intelligence lead + Platform Engineering |
| **Code** | [`company_brain/decision_context.py`](../company_brain/decision_context.py) |
| **First product consumer** | [`product/pr_guardian/company_brain.py`](../product/pr_guardian/company_brain.py) |
| **Depends on** | [Qualified World Model](COMPANY-BRAIN-WORLD-MODEL.md) and [Company Brain Core](COMPANY-BRAIN-CORE.md) |

## Purpose

A **Decision Context** is the bounded explanation that connects organizational evidence to a
specific product decision. It answers three distinct questions without collapsing them into one
model assertion:

| Question | Contract answer | It must not become |
|---|---|---|
| What is known? | An authorized evidence pointer with source kind and locator, qualified at the relationship level for freshness and confidence. | Copied source content or an unscoped retrieval result. |
| Why is it relevant here? | A fresh, authorized, conflict-free relationship plus a deterministic product derivation. | An inferred causal story or a hidden chain of thought. |
| What should happen? | A separately versioned product policy, recommendation, or review request. | Authority to merge, deploy, or execute a runbook. |

This contract is the Company Brain's **speaking and searching** boundary: it makes a compact,
reviewable explanation available at a moment of truth without turning the Brain into unrestricted
agent memory or an authority engine.

## Query and provenance boundary

```text
tenant + repository + changed services + requesting principal
                         |
                         v
              QualifiedWorldModelContext
                         |
                         v
                  DecisionContext
                         |
                         +--> product-specific policy / finding / outcome
                         |
                         `--> audience-safe presentation
```

`decision_context_from_world_model()` does not read storage or make a second authorization
decision. It projects one already-qualified `QualifiedWorldModelContext` into:

- a reproducible `context_version` fingerprint;
- aggregate authorized evidence inventory for the product record;
- `DecisionContextRelationship` facts, each with stable source/target IDs, labels, relationship
  kind, confidence, freshness, and authorized evidence references;
- explicit limitations and conflict IDs; and
- an explicit `qualified` flag supplied by the consuming product's qualification rule.

Only a relationship that is all of the following can enter `DecisionContext.relationships`:

1. usable under the qualified world-model policy;
2. fresh and supported by authorized evidence;
3. free of a detected conflict; and
4. fully represented by endpoints already present in the authorized query result.

`has_evidence` is structural provenance, not an explanatory business fact, and therefore cannot
appear as a Decision Context relationship. Aggregate evidence remains useful audit provenance, but
only the relationship list identifies the facts that passed the decision-usable path.

The Decision Context's source bound is semantic: tenant, repository, changed-service scope, and
requesting principal. Its operational consumer boundary is now the
[Decision Experience Contract](COMPANY-BRAIN-DECISION-EXPERIENCE.md): a deterministic
`ContextPacket` adds byte/count limits and explicit omissions without re-querying or widening
access. That reference byte cap is not a tokenizer/model budget or a production interface claim;
any broader interactive experience still needs its own per-reader and model-specific limits.

## Audience safety

Evidence authorization is performed for the requesting Company Brain principal. That authorization
does **not** automatically apply to everyone who can read a GitHub pull-request comment.

Accordingly, the current PR Guardian renderer publishes only:

- qualification state;
- counts of mapped/affected services, qualified relationships, and retained evidence pointers;
- the context fingerprint; and
- explicit limitations.

It deliberately omits `EvidenceReference.locator` values and relationship statements. A future
interactive view must authenticate its human reader, re-run the world-model query for that reader,
and apply that reader's access control list before showing source locations or relationship labels.
It must not reuse a service-account Decision Context as proof that a human viewer is authorized.

## PR Guardian integration

PR Guardian is the first consumer. The qualified adapter creates a `DecisionContext`, its bounded
`ContextPacket`, and a `ContextHealthReport` alongside its service graph.
`PRGuardianCompanyContext` exposes the context as its source of truth for evidence, context
version, qualification, limitations, and conflicts; it no longer carries parallel mutable copies
of those fields.

The publisher appends a non-authorizing **Company Brain decision context** section after the
canonical shadow observation. The canonical workflow-transfer artifact is unchanged. When context
is limited, that section states why the simulated control remains neutral. When it is qualified, it
states the scope and evidence state without disclosing ACL-filtered source details.

The durable `PRFinding` continues to retain the aggregate authorized `EvidenceBundle`, qualification
state, and fingerprint. It does not claim to persist a replayable Decision Context or to create a
human outcome. Explicit reviewer feedback and independently correlated outcomes remain the only
learning signals described in [PR Guardian / Company Brain](PR-GUARDIAN-COMPANY-BRAIN.md).

## Non-goals and next boundary

- It does not infer causality, ownership, or intent from prose.
- It does not expose source bodies, elevate a vector score into evidence, or bypass source access
  control.
- It does not grant a simulated policy, a merge decision, deployment authority, or remediation
  execution authority.
- It is not yet a user-facing search endpoint, Context Room, or general-purpose agent workspace.
- It does not replace the signed evidence-read receipt, human correction workflow, or durable
  external-publication contract in [Decision Experience](COMPANY-BRAIN-DECISION-EXPERIENCE.md).
- It does not prove a named pilot, useful reviewer outcomes, production readiness, or any autonomy
  tier. The authoritative position remains [Current Position](CURRENT-POSITION.md).

The next product boundary is an authenticated, per-reader Decision Context viewer only after a
named pilot establishes the required authorization, retention, audit, usability, and evidence
requirements. It is not implied by this reference contract or by the source-level Decision Brief
and Context Packet records.

## Verification

[`tests/test_company_brain_decision_context.py`](../tests/test_company_brain_decision_context.py)
protects the invariant that unqualified relationships do not enter a Decision Context.
[`tests/test_pr_guardian_company_brain.py`](../tests/test_pr_guardian_company_brain.py) protects
both the private relationship explanation and the GitHub-safe summary, including the absence of
source locators from published comments. The operational packet, receipt, health, correction, and
why-answer contracts are covered in [Decision Experience](COMPANY-BRAIN-DECISION-EXPERIENCE.md).
