# Runtime Observability, AI Security and FinOps

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | design; OTLP export is configured only when an endpoint is set |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


Every material Engineering Intelligence operation carries a correlation ID across retrieval, model synthesis, tool/runbook execution, workflow state and audit events.

## Runtime event contract

`OperationEvent` captures:

- correlation ID, operation, component and outcome;
- latency;
- service/repository/agent/user attribution;
- model identity and input/output token usage;
- retrieval document counts;
- suspicious-evidence counts;
- model/search/tool cost attribution.

Configured unit rates are explicit inputs. The platform does not hard-code provider pricing; measured usage and assumed rates remain separable.

## RAG security path

`authorized search -> evidence classification -> suspicious-source quarantine -> model context`

Query-time ACL trimming still happens before this step. Content classification is defense in depth against indirect prompt injection, not an authorization mechanism.

## Required production dashboards/SLOs

- retrieval and synthesis latency/error rate;
- token usage and model/search/tool cost by service/repo/agent;
- no-evidence and security-quarantine rates;
- workflow queue age/retries/DLQ;
- remediation authorization/verification/rollback outcomes;
- human approval latency;
- AI recommendation acceptance, rejection and revert rates.

OTel spans and cost events must use the same correlation identity as authoritative workflow/audit records.
