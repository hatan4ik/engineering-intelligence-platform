# Company Brain Decision Experience and Publication Contract

| | |
|---|---|
| **Classification** | Reference contract — source-level decision and publication controls, not a deployed user experience or production proof |
| **Owner** | Platform Engineering + Data Governance |
| **Code** | [`company_brain/context_packet.py`](../company_brain/context_packet.py), [`company_brain/evidence_receipts.py`](../company_brain/evidence_receipts.py), [`company_brain/decision_brief.py`](../company_brain/decision_brief.py), [`company_brain/corrections.py`](../company_brain/corrections.py), [`company_brain/artifact_outbox.py`](../company_brain/artifact_outbox.py) |
| **Design decision** | [ADR-004](../architecture/adr/004-company-brain-decision-experience-and-publication.md) |
| **Depends on** | [Qualified World Model](COMPANY-BRAIN-WORLD-MODEL.md), [Decision Context](DECISION-CONTEXT.md), and [Durable Store](COMPANY-BRAIN-STORE.md) |

## Purpose

Company Brain must bring the right evidence to a human decision without becoming unbounded agent
memory, a source of hidden reasoning, or an authority to act. This contract makes the moment of
truth explicit: what was requested, which bounded evidence was read, what was omitted, who read
it, and which external artifact was intended before an effect is attempted.

```text
authenticated principal + scoped product request
                    |
                    v
             Decision Context (full authorized result)
                    |
                    v
      Context Packet (bounded subset + omission disclosure)
                    |
          +---------+----------+
          |                    |
          v                    v
  Context Health          Decision Brief
  "why not?"              request kept separate from facts
          |
          v
 Evidence Read Receipt -> correction/revalidation proposal

fixed product result -> durable artifact outbox -> independently retried external deliveries
```

All records preserve provenance and scope. None grants merge, deployment, policy, or runbook
authority.

## Records and safety rules

| Record | What it proves | What it does not prove or authorize |
|---|---|---|
| `DecisionContext` | The full principal-scoped, qualified result for one world-model query | A public audience may read its source locators or relationship labels |
| `ContextPacket` | The deterministic bounded subset used by one consumer step, its byte/count budget, digest, and every omission | A model-token budget, a new retrieval query, or a complete result when `omissions` is non-empty |
| `EvidenceReadReceipt` | A short-lived, <span title="Hash-based Message Authentication Code">HMAC</span>-signed binding of tenant, product, scope, correlation, principal fingerprint, packet digest, and exact evidence revisions | A human approval, a permission grant, or a substitute for source authorization |
| `DecisionBrief` | The human request, decision scope, derived owner IDs, and packet digest remain reviewable together | That an owner approved the request or that the packet is fit for autonomous use |
| `ContextHealthReport` | Whether the packet is ready, limited, conflicted, or unqualified and why | A hidden retry or a guessed answer to fill the gap |
| `CorrectionProposal` / `CorrectionReview` | An authenticated human requested source revalidation and a separately authenticated reviewer dispositioned it | A direct edit to a Company Brain fact, source document, or external ticket |
| `ProductArtifact` / delivery intent | The source-safe external check/comment payload was durably recorded before delivery | That GitHub accepted it, or that a failed delivery was lost |

### Bounded Context Packets

`DecisionContext` remains the authoritative in-process result of an already-authorized query.
`ContextPacket` is a deterministic working subset; it does not re-query storage or widen the
requesting principal's access. The default reference budget is 20 relationships, 40 evidence
references, 12 limitations, 12 conflicts, and 12,000 canonical UTF-8 bytes.
Hard source-level ceilings are 100 relationships, 200 evidence references, 100 limitations, 100
conflicts, and 65,536 bytes; a product may tighten but cannot widen those limits.

An included relationship retains every evidence reference that supports it. If all of those
references do not fit, the entire relationship is omitted. The packet records why material did
not fit (`relationship_limit`, `evidence_limit`, `item_limit`, or `byte_limit`) and exposes a
stable digest. Consumers must treat `complete = false` as incomplete context, not as permission
to infer the missing material.

The byte cap is deliberately not a claimed model-token budget. A model adapter must add its own
stricter tokenizer-aware boundary before prompt construction.

### Evidence read before proposal

`EvidenceReadReceiptAuthority` issues a receipt only for the deterministic packet projection of
the supplied Decision Context. The receipt includes source kind and revision plus a digest of the
locator for each evidence reference retained in that packet; it deliberately does not copy the
locator, source body, or context-only evidence into a broader record.

The authority rejects a proposal when the receipt is expired, forged, bound to another tenant,
product, scope, correlation, principal, context version, or packet digest. It also rejects
unqualified, incomplete, or evidence-empty packets. The maximum receipt lifetime is 15 minutes;
the default is 10 minutes. This is a read-before-write evidence control, not an approval control.

### Decision Briefs and `why not?`

`DecisionBrief` keeps a human objective and question separate from evidence-backed facts. Owner
IDs are derived only from qualified `owns` relationships present in the packet. It requires human
review whenever the context is unqualified, incomplete, limited, or conflicted.

`context_health_report()` gives a consumer a source-safe reason not to proceed. A `ready` report
is the narrow condition for an advisory proposal; `limited`, `conflicted`, and `unqualified`
reports block that progression and name the category of missing context without leaking a source.

### Governed human corrections

Corrections are not free-form writes to organizational memory. A submitter must be an authenticated
user contained in the principal bound to a current, complete evidence-read receipt. A reviewer must
likewise be an authenticated user supplied by the caller's identity boundary. Both proposal and
review are append-only. Even `accept_for_revalidation` means only that a separately authorized
source-reconciliation workflow may investigate; it does not mutate a fact automatically.

### Why-answer evaluation corpus

The reviewed corpus at [`../eval/company_brain_why_cases.json`](../eval/company_brain_why_cases.json)
and `evaluate_why_answer()` check machine-verifiable explanation properties: exact packet binding,
relationship and citation support, required limitation disclosure, and abstention when context is
unqualified or incomplete. It does not claim to judge prose quality, causal truth beyond supplied
evidence, or user satisfaction.

### Durable external publication

Products first record an immutable `ProductArtifact` and all intended delivery payloads in one
SQLite transaction. A dispatcher leases exactly one delivery, acknowledges it after the external
call returns, or returns it to `pending` with bounded backoff and a source-safe error class. A
stale worker cannot acknowledge a later worker's lease.

PR Guardian uses two independent deliveries: a GitHub check and a sticky GitHub comment. The check
uses the delivery's stable external ID to look up and update a prior matching check run after a
crash; the comment already uses its controlled marker. Therefore a comment failure does not replay
a completed check, and a process failure after GitHub accepts a delivery remains recoverable.

For local/reference recovery, an operator can run
`python scripts/recover_pr_guardian_publications.py --state-dir "$EIP_STATE_DIR"` with
`EIP_GITHUB_TOKEN` present. The command drains only a bounded set of already-due deliveries; it
does not re-evaluate a pull request, alter a mode, or create new authority.

The SQLite outbox is deliberately reference-only. A managed runtime must preserve atomic recording,
lease fencing, idempotent external delivery, retry/<span title="Dead-Letter Queue">DLQ</span> policy, tenant isolation, and operator
recovery evidence. It is not a replacement for the Company Brain state store, Temporal, or a
general-purpose job queue.

## Consumer sequence

1. Authenticate the human or workload identity and obtain an authorized, tenant-scoped Decision
   Context.
2. Build a Context Packet using an explicit product/model budget; surface its health report.
3. Create a Decision Brief for a human decision; do not derive ownership outside the packet.
4. Issue an evidence-read receipt only when a later proposal needs to be tied to that exact read.
5. Reject incomplete, unqualified, stale, or foreign receipts before accepting a correction or
   other proposal.
6. Record any external product artifact before calling its adapter; use bounded recovery to drain
   due deliveries.
7. Reconcile accepted corrections through the source lifecycle, not by editing Company Brain
   records in place.

## Non-goals and remaining work

- There is no authenticated, per-reader Decision Brief API or browser interface yet. A GitHub
  comment remains a deliberately non-disclosing summary.
- These reference SQLite stores do not establish managed durability, backup/restore, tenancy
  isolation, retention, or production operational evidence.
- The receipt does not replace plan-hash approvals for consequential remediation.
- The correction path does not infer a human identity from a label, merge, or silence, and it does
  not execute revalidation by itself.
- The why corpus is a contract-quality gate, not pilot quality evidence or a claim of model
  reasoning quality.

## Verification

- [`tests/test_company_brain_context_packet.py`](../tests/test_company_brain_context_packet.py)
  verifies deterministic bounds, omission disclosure, and complete relationship citations.
- [`tests/test_company_brain_evidence_receipts.py`](../tests/test_company_brain_evidence_receipts.py)
  verifies expiry, scope/principal binding, revision retention, signatures, and forged-packet
  rejection.
- [`tests/test_company_brain_decision_brief.py`](../tests/test_company_brain_decision_brief.py),
  [`tests/test_company_brain_context_health.py`](../tests/test_company_brain_context_health.py),
  and [`tests/test_company_brain_corrections.py`](../tests/test_company_brain_corrections.py)
  verify the human-decision and correction boundaries.
- [`tests/test_company_brain_why_evaluation.py`](../tests/test_company_brain_why_evaluation.py)
  verifies the reviewed corpus and refusal of unsupported claims.
- [`tests/test_company_brain_artifact_outbox.py`](../tests/test_company_brain_artifact_outbox.py)
  and [`tests/test_pr_guardian_publication_outbox.py`](../tests/test_pr_guardian_publication_outbox.py)
  verify durable recovery, lease fencing, and independent PR Guardian check/comment retry.
