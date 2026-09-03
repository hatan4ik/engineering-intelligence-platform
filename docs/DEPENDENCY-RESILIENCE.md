# Runtime Dependency Resilience Contract

| | |
|---|---|
| **Classification** | Reference contract — source and automated-test evidence only |
| **Owner** | Platform Engineering |
| **Scope** | Synchronous runtime adapters composed by the API, PR Guardian, and operational-intelligence services |
| **Non-claim** | This is not an availability SLO, load test, multi-process rate limiter, or production-recovery record |

## Purpose

Every external dependency needs a bounded failure mode. The shared
`resilience.dependencies.DependencyBoundary` gives a composed adapter a
small, explicit bulkhead and circuit breaker. It deliberately does **not**
retry an operation: a generic retry could duplicate a GitHub publication,
replay a webhook-derived action, or hide an unsafe policy failure. Only an
operation owner that has independently proved idempotency may add a retry
policy at its own boundary.

The boundary has three states:

- **closed** — up to the adapter's `max_in_flight` calls run;
- **open** — calls fail fast after the configured transient-failure threshold
  until the recovery interval expires;
- **half-open** — exactly one recovery probe may run. A success closes the
  breaker; another transient failure reopens it.

Late completions from an earlier concurrency generation cannot close a circuit
that another request has opened. This prevents one slow success from removing
protection during an outage.

## Implemented runtime boundaries

| Dependency | Adapter | Timeout/retries | Bulkhead and breaker | Safe caller behavior |
|---|---|---|---|---|
| GitHub REST | `integrations/github/pr_guardian.py` | 20 s; no wrapper retry | 8 in flight; 3 transient failures; 30 s recovery | PR Guardian webhook returns a sanitized retryable `503`; it never claims that a check/comment was published. |
| OPA remediation policy | `remediation/opa_policy.py` | 3 s; no wrapper retry | 16 in flight; 3 transient failures; 15 s recovery | The policy decision is denied. There is no model or local permissive fallback. |
| Azure Monitor Logs and managed identity | `integrations/azure/monitor.py` | 30 s; no wrapper retry | 8 in flight; 3 transient failures; 30 s recovery | Operational webhook returns a sanitized retryable `503`; no proposal is returned as authoritative. |
| Azure Resource Graph and managed identity | `integrations/azure/resource_graph.py` | 30 s; no wrapper retry | 4 in flight; 3 transient failures; 30 s recovery | The drift adapter raises a typed dependency failure; callers must not infer current state from stale/missing data. |
| Azure AI Search | `app/rag/azure_backend.py` | 20 s; Azure SDK retries disabled | 12 in flight; 3 transient failures; 30 s recovery | Governed query returns a sanitized retryable `503`; no answer is synthesized from incomplete retrieval. |
| Azure OpenAI and its token provider | `app/rag/azure_backend.py` | 20 s; OpenAI SDK retries disabled | 8 in flight; 3 transient failures; 30 s recovery | Governed query returns a sanitized retryable `503`; it does not substitute a guessed answer. |

Only transport failures, timeouts, malformed dependency responses, throttling,
and server-side failures contribute to opening a circuit. A non-transient
caller/configuration response is surfaced without being treated as proof that
the service is healthy or unhealthy.

`AzureRagBackendFactory` owns Azure RAG clients and their boundaries for one
ASGI process. A request does not construct a fresh breaker, so the bound has
meaning across concurrent requests and configured model tiers.

## Deliberate limits

- Limits are **per process**, not globally distributed. They are a local
  blast-radius control, not a tenant quota or fleet-wide rate limiter.
- `DependencyHealth` is available for a future authenticated operational
  projection, but `/healthz` does not yet expose dependency state. A health
  response must not become an unauthenticated dependency inventory.
- Temporal, Cosmos DB, ingestion scripts, validation CLIs, and digital-twin
  subprocess adapters are outside this specific synchronous HTTP contract.
  They require their own workload-specific retry, idempotency, and recovery
  designs before a production claim.
- No deployment, load, chaos, or alerting evidence exists in this repository.
  Do not turn these source-level bounds into an SLI/SLO assertion without
  retained evidence for a named environment.

## Verification

```bash
pytest -q tests/test_dependency_boundary.py tests/test_dependency_adapters.py tests/test_azure_rag_resilience.py
```

The tests prove fail-fast behavior after a transient failure, bulkhead
saturation, half-open recovery, protection from late-success races, adapter
failure mapping, Azure RAG client reuse, and disabled SDK retries. They do not
measure real provider latency, quota, availability, or recovery.
