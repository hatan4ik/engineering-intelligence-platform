# Company Brain Qualified World Model

| | |
|---|---|
| **Classification** | Reference contract — local read model, not a production knowledge or action authority |
| **Code** | [`company_brain/world_model.py`](../company_brain/world_model.py) |
| **Depends on** | [Durable Store Contract](COMPANY-BRAIN-STORE.md) and [Governed Memory Synchronization](COMPANY-BRAIN-MEMORY-SYNC.md) |

## Purpose

`CompanyBrainWorldModel` turns active, tenant-scoped durable records into a **qualified** company
context. An entity or relationship is never trusted merely because it exists in storage. The model
uses the ACL-bearing evidence pointer and its provenance to calculate confidence and freshness
before a link can affect repository scope, blast radius, or ownership context.

The interface is read-only. It does not authorize a merge, deployment, policy change, or runbook.

## Qualification contract

| Input condition | Result |
|---|---|
| Evidence is not visible to the requesting `BrainPrincipal` | Fail closed: no evidence, no usable relationship, no inferred graph path |
| Authorized evidence is older than its source policy | Relationship is marked `stale` and excluded from decision paths |
| Fresh evidence confidence is below policy threshold | Relationship remains visible as a limitation but is not usable |
| More than one fresh owner asserts the same service | Return all owners and an `ambiguous_ownership` conflict; never choose one |
| Two services directly depend on each other | Emit `dependency_cycle` and exclude both edges from blast-radius traversal |
| Source evidence is fresh and reaches threshold | Relationship is `usable` and may participate in a qualified query |

The default source policy is deterministic and checked into code. It assigns source-specific
confidence and maximum age to ADRs, repository changes, runbooks, incidents, deployments,
documentation, work items, and conversations. Unknown sources default to low confidence and a
short freshness window. A deployment must provide a policy with the same semantics; it must not
replace evidence qualification with an embedding score or model assertion.

## Query result

`context_for_change()` requires a tenant-bound model, a repository ID, changed service IDs, and an
authorized principal. It returns:

- repository-scoped changed services and transitive blast radius using only qualified dependencies;
- qualified entities and relationships with confidence, freshness, authorized evidence, and
  limitations;
- candidate owners without collapsing ambiguity;
- typed conflicts; and
- an overall conservative confidence equal to the weakest usable non-evidence relationship in the
  returned context.

The result intentionally preserves uncertainty. A caller must show its limitations or take the
insufficient-evidence path; it may not convert a low-confidence or conflicted graph edge into a
silent approval.

## Current product integration

PR Guardian is the first product consumer. Its adapter translates qualified context into a
repository-scoped service graph and an ACL-authorized `EvidenceBundle`; its reference store retains
typed findings and explicit reviewer outcomes. The adapter preserves the distinction between a
measured fact, a derived risk assessment, and a policy decision. It does not turn any of those
records into a merge, deployment, or remediation authority.

The next proof is operational rather than another source-only integration: a named pilot must show
that authorized evidence, reviewer feedback, and independently correlated outcomes remain useful
and safe in the certified repository scope. Until then, the integration is reference behavior, not
pilot or production evidence.
