# ADR-004: Bounded decision context, evidence receipts, and durable publication

| | |
|---|---|
| **Status** | Accepted |
| **Classification** | Accepted architecture decision — source-level contract, not a deployment or production-proof claim |
| **Owner** | Platform Engineering + Data Governance |
| **Decision date** | 2026-09-09 |
| **Scope** | Principal-scoped Company Brain decision context, human corrections, and external product publication |
| **Related design** | [System Design](../design.md), [ADR-003](003-company-brain-runtime-topology-and-recovery.md), [Decision Experience Contract](../../docs/COMPANY-BRAIN-DECISION-EXPERIENCE.md) |
| **Authoritative current state** | [Current Position](../../docs/CURRENT-POSITION.md) |

## Context

Company Brain needs to explain why a recommendation is relevant at the moment a person makes a
decision. Passing an unbounded graph, raw documents, or a model's private working memory into a
product would make scope, access, omissions, and evidence revisions invisible. Directly publishing
GitHub comments/checks after computing a result also permits partial external effects: one call can
succeed, another can fail, and a process crash can lose the knowledge needed for safe recovery.

The platform already has an authorization-qualified `DecisionContext`, product findings, plan-bound
approvals, and reference SQLite stores. It needs a product-neutral boundary that adds operational
context limits, read-before-proposal provenance, governed human corrections, and recoverable
external presentation without confusing any of those records with action authority.

## Decision

1. **Decision Context remains the full authorized source result.** It is principal-scoped and
   evidence-qualified; it is not a public or cross-reader payload.
2. **Every bounded consumer step receives a deterministic Context Packet.** The packet contains a
   fixed byte/count budget, all supporting evidence for every retained relationship, and explicit
   omission records. It cannot re-query, widen authorization, or silently truncate a claim.
3. **A short-lived signed Evidence Read Receipt binds later proposals to one exact read.** It
   binds tenant, product, scope, correlation, principal fingerprint, Context Packet digest, and
   source evidence revisions. It is rejected when stale, forged, incomplete, unqualified, or used
   outside that binding. It is not an approval.
4. **Decision Briefs keep human requests separate from evidence facts.** Context Health reports
   whether a proposal is eligible and gives a non-disclosing `why not?` result. Owner IDs derive
   only from qualified ownership edges contained in the packet.
5. **Human corrections are append-only revalidation requests.** An authenticated requesting user
   and authenticated reviewing user are required. No correction directly updates a source, Company
   Brain fact, policy, or workflow; accepted reviews enter separately authorized reconciliation.
6. **External product effects use a durable artifact outbox.** The complete source-safe artifact
   and intended deliveries commit before any adapter call. Deliveries are independently leased,
   fenced, acknowledged, and retried. GitHub checks use stable external IDs for retry upsert, and
   GitHub comments use a controlled sticky marker.
7. **SQLite implementations are reference adapters only.** A managed implementation must preserve
   these semantic contracts but may choose an appropriate transaction and delivery substrate.

## Alternatives considered

| Alternative | Decision |
|---|---|
| Pass raw graph/document context directly to products or models | Rejected: scope, ACL, revisions, and omissions become implicit; source content can leak beyond its audience |
| Treat vector/retrieval scores as enough evidence | Rejected: a score does not bind a fact to authorized source revisions or explain missing evidence |
| Use a long-lived bearer-style read token | Rejected: it creates an authority-shaped credential rather than an auditable, short-lived evidence binding |
| Let users edit Company Brain facts or documents from a correction form | Rejected: it bypasses source ownership, reconciliation, retention, and review |
| Publish direct GitHub effects and rely on webhook redelivery | Rejected: it cannot prove intent, isolate a failed effect, or safely recover a crash after one effect succeeds |
| Add a generic message broker immediately | Rejected: a broker is transport, not authority; it needs a typed port, caller, operational design, and separate evidence before it is introduced |

## Security and privacy impact

- Context packets do not contain source bodies and must record omissions rather than fill them with
  inferred content.
- Receipts store source locator digests, not access-controlled locators, and bind the reader's
  principal fingerprint.
- A receipt, Context Packet, Decision Brief, correction, or external artifact cannot authorize a
  merge, deployment, or remediation. Consequential actions continue to require deterministic
  policy and plan-bound approval.
- GitHub-facing output remains non-disclosing because a repository audience is not equivalent to a
  Company Brain principal. Any future interactive view must re-authorize its individual reader.

## Reliability and rollback impact

- Product publication is recoverable per delivery: a completed check is not reissued when a comment
  fails, and a stale worker cannot acknowledge a newer lease.
- The outbox is immutable by artifact identity. Retry uses the same external delivery identity, so
  a process failure between adapter success and acknowledgement can be safely replayed.
- A failed delivery remains pending with bounded backoff. A managed deployment must define its
  retry/<span title="Dead-Letter Queue">DLQ</span>, alerting, backup/restore, and operator recovery evidence before operational use.
- The decision adds no new mutation path; correction acceptance still requires a separately
  authorized source reconciliation and can be stopped without rolling back Company Brain state.

## FinOps impact

- Context Packet bounds prevent an authorized but unexpectedly large graph/evidence set from
  becoming an unbounded model prompt or delivery payload.
- The reference byte cap is not a token-cost guarantee. A model adapter must publish and enforce
  its own tokenizer-aware input/output and retry budgets.
- Independent retries prevent paying to replay a successful external side effect solely because a
  sibling delivery failed.

## Consequences

- Product adapters have a small common vocabulary for bounded evidence, safe human review, and
  recoverable external effects rather than inventing their own opaque agent-memory path.
- PR Guardian now requires a durable finding store and artifact outbox whenever it publishes; its
  offline/shadow evaluation path can remain `publish=False` without external effects.
- The design intentionally adds no production maturity claim. Managed storage, an authenticated
  reader experience, scheduled recovery, and named-pilot evidence remain separate work.

## Evidence and metrics that can cause reconsideration

- Corpus results for citation support, abstention, omission disclosure, and correction review.
- Outbox recovery results: delivery age, retry count, duplicate-external-effect rate, stale-lease
  rejection, and dead-letter/alert handling in a named environment.
- Per-reader authorization tests and retention/deletion exercises for the future interactive
  decision experience.
- Pilot measurements showing whether bounded briefs improve reviewer decisions without increasing
  unsupported claims, latency, or cost.
