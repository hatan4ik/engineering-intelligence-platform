# PR Guardian Product Domain Contract

| | |
|---|---|
| **Status** | Current product boundary — versioned reference contracts, not a pilot result |
| **Owner** | Engineering Intelligence lead + Developer Experience |
| **Product decision** | [PR Guardian strategy](PRODUCT-STRATEGY.md) |
| **Delivery sequence** | [Outcome-gated roadmap](../roadmap/technical-roadmap-24-months.md) |

## Purpose

PR Guardian needs one product contract before it gains a durable store, portal, richer retrieval,
or additional workflow adapters. The contracts in
[`product/pr_guardian/contracts.py`](../product/pr_guardian/contracts.py) define that boundary.
They are deliberately independent of GitHub payloads, Actions artifacts, SQLite, Temporal, and
any future portal/API implementation.

The existing [`product/pr_guardian_shadow.py`](../product/pr_guardian_shadow.py) records remain
the strict, safe transfer schema between the untrusted PR evaluation workflow and the trusted
publisher. They are not replaced in this tranche. Future adapters translate those wire records
into the product records below.

## Canonical records

| Record | Purpose | Safety invariant |
|---|---|---|
| `RepositoryConfig` | Names the repository, services, owners, allowed evidence sources, policy version, and shadow/advisory mode | No anonymous or organization-wide installation; no enforcement mode exists in the contract |
| `EvidenceReference` | Minimal, ACL-authorized evidence pointer | Unauthorized evidence cannot enter a finding |
| `EvidenceBundle` | Labels evidence as measured, derived, or modeled and records limitations | Missing evidence is explicit; measured evidence requires an authorized reference |
| `PRFinding` | Reviewable risk finding bound to PR SHA, correlation ID, policy version, and a simulated action | `would-block` is descriptive only and cannot authorize a merge decision |
| `FindingOutcome` | Explicit reviewer disposition and optional independent post-merge correlation | Closure, merge, silence, and ignored advice are not inferred as correct or incorrect |
| `EvaluationRun` | Dataset/policy/version-bound quality evaluation | Threshold changes are reviewed policy changes, not automatic learning |

## Adoption sequence

1. Retain the existing GitHub shadow workflow and its strict artifact validation.
2. Translate every published shadow observation into one or more durable `PRFinding` records.
3. Resolve evidence through governed retrieval, preserving source authorization and limitations in
   the `EvidenceBundle`.
4. Capture reviewer labels as `FindingOutcome`; separately correlate independent post-merge
   signals with a retained correlation reference.
5. Run versioned `EvaluationRun` datasets before proposing an advisory or deterministic blocking
   rule.

## Non-goals

- The contract does not create a merge gate, execute an action, grant a permission, or change OPA
  policy.
- It does not treat a reviewer disposition as production incident/rollback evidence.
- It does not require Temporal for PR review; durable orchestration is introduced only when the
  product has a genuine multi-step, resumable workflow.
