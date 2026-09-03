# Production Readiness & Autonomy Certification

| | |
|---|---|
| **Classification** | Certification requirements — a completed document is not a passed certification |
| **Evidence records** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |
| **NFRs** | [`../architecture/non-functional-requirements.md`](../architecture/non-functional-requirements.md) |

No agent or remediation is promoted because it appears intelligent. Promotion requires evidence.

## Certification gates

### Gate 1 — Functional
- Contract tests pass.
- Golden-set quality threshold passes.
- Deterministic fallback behavior is defined.
- Idempotency and duplicate-event handling tested.

### Gate 2 — Security
- Identity and ACL boundaries tested.
- Prompt-injection and poisoned-context tests pass.
- Tool/action allow-list enforced outside the model.
- Secrets/PII redaction and audit behavior verified.

### Gate 3 — Reliability
- [SLO and timeout budget defined per workflow](PERFORMANCE-EVIDENCE-CONTRACT.md).
- Retry/backoff and circuit breaker behavior tested.
- Dependency outage behavior tested.
- Rollback/compensation path exercised.

### Gate 4 — Operational safety
- Blast radius quantified.
- Exact allowed environments/services/actions documented.
- Verification signal independent from the action path where practical.
- Kill switch tested.
- Escalation owner/on-call route exists.

### Gate 5 — Economics
- Token/model/tool/search unit costs measured.
- Per-agent budget and rate limits configured.
- Cost anomaly alert exists.

## Autonomy certification

| Level | Mutation | Required control |
|---|---|---|
| L0 | none | observability/audit |
| L1 | none | evidence + confidence |
| L2 | human | exact proposed action + rollback |
| L3 | automated after approval | policy + approval + allow-listed runbook + verify |
| L4 | bounded automatic | all L3 controls + service certification + blast-radius/error-budget limits |

L4 approval is action-specific, not a blanket permission for an agent.

## Mandatory audit event

Each decision/action records: correlation ID, actor/service identity, evidence IDs, model/version if used, policy decision, proposed action, approver when applicable, execution result, verification result, rollback result, latency and estimated cost.
