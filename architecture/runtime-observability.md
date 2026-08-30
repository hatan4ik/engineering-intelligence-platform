# Runtime Observability, AI Security and FinOps

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | source-level reference contract; OTLP export is configured only when an endpoint is set |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


Every material Engineering Intelligence operation is designed to carry a
correlation ID across retrieval, model synthesis, tool/runbook execution,
workflow state and audit events. The implemented HTTP boundary validates and
returns one correlation ID per request, accepts a valid W3C parent trace, and
emits a child trace context. The non-consequential Temporal proof workflow has
an explicit trace-context carrier. This is not evidence that a deployed
collector joins every production service trace yet.

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

## Trace propagation boundary

`telemetry.trace_context.TraceContext` is the serializable contract at an
integration edge. It canonicalizes valid `traceparent`/`tracestate` pairs with
the OpenTelemetry propagator and drops invalid metadata. `app.application`
binds it before any route runs; `app.request_context` supplies the separately
validated correlation ID to the route and durable workflow callers. Neither
trace headers nor correlation headers grant access or change a policy decision.

The next operational step is collector/dashboard wiring and a retained
trace-to-audit reconciliation record for a named environment. Do not infer
that evidence from the unit tests or response headers.

## Dependency failure boundary

Synchronous runtime integrations use explicit timeouts plus a per-process
bulkhead/circuit breaker. The boundary never applies a generic retry, because
it cannot establish that a publication or remediation-related call is
idempotent. The exact covered adapters, thresholds, safe HTTP/policy behavior,
and deliberately unimplemented fleet-wide controls are in the
[Runtime Dependency Resilience Contract](../docs/DEPENDENCY-RESILIENCE.md).
That source-level contract is not an operational latency, availability, or
recovery claim.
