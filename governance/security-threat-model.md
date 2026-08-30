# Security Threat Model

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Security |
| **Reviewed** | 2026-08-30 — source-control reconciliation; not a security audit |
| **Assertions are** | threat model and required controls; not an audit result |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


## Primary threats
1. Prompt injection through retrieved code, tickets or documentation (The Confused Deputy).
2. Cross-repository or cross-team data exfiltration.
3. Secret/PII leakage through ingestion, prompts or logs.
4. Hallucinated remediation presented as fact.
5. Excessive agent permissions and confused-deputy behavior.
6. Model/token abuse causing cost or availability impact.
7. Poisoned or stale knowledge influencing decisions.
8. Automation loops causing repeated harmful mutations.
9. Stale or replayed human approvals authorizing a changed plan.
10. Retrieval/index poisoning altering evidence presented to operators.
11. Retention, residency, or deletion failures exposing engineering knowledge beyond its approved lifecycle.

## Control-status vocabulary

This model separates a design requirement from the evidence that proves it.

- **Reference-implemented** means a source path and automated regression tests
  exist in this repository. It is not a deployed-control claim.
- **Reference-partial** means a useful mechanism exists but a material boundary
  is still absent or deliberately deferred.
- **Planned** means the requirement is retained because no implementation may
  be inferred from documentation alone.
- All rows remain **not operationally proven** until an approved evidence record
  exists for the named scope. See
  [`../docs/PRODUCTION-EVIDENCE.md`](../docs/PRODUCTION-EVIDENCE.md).

## Current source-control status

| Control requirement | Status | Current boundary | Material limit before a real-data or production claim |
|---|---|---|---|
| Authenticate callers and authorize before Azure retrieval | Reference-implemented | `app/authentication.py`, `app/gateway.py`, and typed startup settings reject incomplete Azure identity configuration | The deterministic demo permits a clearly configured header-identity path; Entra group-overage resolution and real identity evidence are not present. |
| Preserve repository/document ACLs as retrieval filters | Reference-implemented | `app/rag/azure_backend.py` builds an ACL filter before retrieval | Requires real index/schema and authorized/denied path evidence. |
| Scan/redact sensitive inputs before embedding/logging | Reference-implemented | ingestion access-control/redaction paths and telemetry contracts | Coverage is source/test evidence, not a source-data inventory or DLP audit. |
| Treat retrieved content as untrusted data and quarantine suspicious evidence | Reference-partial | Azure RAG prompt contract plus `security.evidence.classify_evidence` | No dedicated deterministic Guardrail SLM exists; classifier coverage and a larger adversarial corpus remain required. |
| Ground operational recommendations in evidence | Reference-implemented | typed evidence, finding, outcome, and provenance contracts; PR Guardian/operations presenters | A named pilot must prove citations are useful and complete for its source set. |
| Separate reasoning from mutation with deterministic authorization | Reference-implemented | OPA contract, policy conformance corpus, plan-bound approval and allow-listed remediation path | No production policy-bundle distribution or live authorization evidence exists. |
| Use managed/workload identity and least privilege | Reference-partial | Azure adapters use `DefaultAzureCredential`; IaC/chart contain reference workload-identity surfaces | No provisioned identity, role-assignment, network, or scope evidence exists. |
| Bound synchronous dependency failures | Reference-implemented | explicit timeouts and per-process bulkheads/circuit breakers on runtime HTTP/SDK adapters | Not a fleet-wide rate limiter, SLO, chaos test, or recovery record; see the [runtime dependency-resilience contract](../docs/DEPENDENCY-RESILIENCE.md). |
| Meter cost and admit requests by configured budget | Reference-partial | request-cost budget and model/search/tool cost telemetry primitives | Per-principal rate/concurrency enforcement, quota allocation, anomaly alerting, and measured cost control are not implemented. |
| Preserve freshness, ownership, and provenance | Reference-partial | Company Brain provenance contracts and source catalog metadata | Source-quality weighting and full lifecycle evidence require actual source integrations. |
| Record classification, purpose, retention, residency, legal hold, and deletion behavior | Planned | requirements/evidence schema states the required fields | No production source inventory or compliant retention/deletion operation exists. |
| Bound retries and autonomous action counts | Reference-partial | durable orchestration contracts, action single-attempt rules, and synchronous dependency boundaries | No managed queue/worker deployment, fleet-wide quota, or operational proof exists. |
| Bind approval to the exact plan and expiry | Reference-implemented | plan-hash-bound approval and policy/terminal-state checks | Real approver-role integration and audited exercise evidence are still required. |
| Maintain audit records and emergency stops | Reference-partial | local/Cosmos reference audit paths, typed controls, and restart-required kill switches | No immutable external audit export, live control path, or deployed kill-switch exercise exists. |
| Independently verify, roll back, or escalate every autonomous mutation | Reference-implemented | digital-twin/reference remediation workflow and verification/rollback contracts | No certified runbook or real-cluster rehearsal evidence exists. |

## Explicitly planned controls

The following requirements are intentionally retained as gaps; they must not be
described as implemented in architecture, roadmap, or sales-facing material.

1. A deterministic Guardrail SLM (or independently reviewed equivalent) that
   can block prompt-injection/confused-deputy attempts before primary-model
   synthesis or action consideration.
2. Per-user, per-team, and per-agent rate limits, quotas, and concurrency
   admission at the API gateway, plus anomaly alerting.
3. A real-data governance inventory with approved purpose, classification,
   residency, retention, legal-hold, deletion, and reconciliation proof for
   every source.
4. A managed durable runtime with immutable audit export, tested recovery,
   policy-bundle distribution, and retained operational evidence.

No model output may approve, expand, or bypass any of these missing controls.

## Autonomy levels
- **L0 Observe:** collect/correlate only.
- **L1 Recommend:** evidence-backed recommendation; no mutation.
- **L2 Human execute:** system prepares an exact action and rollback; a human executes it.
- **L3 Approve and execute:** authenticated human approval authorizes an allow-listed deterministic runbook.
- **L4 Bounded autonomous:** only explicitly certified service + environment + runbook combinations may execute automatically within policy, blast-radius, error-budget, time and retry limits.
- **L5 Unrestricted autonomy:** intentionally unsupported and out of scope.

Autonomy is granted per service/action/environment, never globally to an agent or model.
