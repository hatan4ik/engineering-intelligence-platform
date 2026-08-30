# HTTP Application Configuration Contract

| | |
|---|---|
| **Classification** | Current implementation contract |
| **Owner** | Platform Engineering |
| **Implementation** | [`../app/settings.py`](../app/settings.py) and [`../app/application.py`](../app/application.py) |
| **Evidence boundary** | This describes source behavior and automated tests. It does not prove a deployed environment or production readiness. |

## Purpose

The HTTP process parses its request-serving environment once into an immutable
`ApplicationSettings` record at ASGI lifespan startup. Routes and adapter
factories receive that record rather than independently reading environment
variables during a request. A narrow OTLP endpoint bootstrap happens before
router import so tracing can attach to the process provider; it is also owned
by `app/settings.py`. The outcome is a visible, testable answer to three
questions: which capability is enabled, which inputs it needs, and which
configurations are refused before serving traffic.

Embedding hosts and tests can call `create_app(settings)` with an already-built
record. This is the supported way to make a test configuration explicit; it
also avoids a test accidentally depending on the developer shell environment.
An application that has neither entered its lifespan nor received explicit
settings returns an unavailable response; it never reparses `os.environ` on a
request path.

## Safety rules

- `EIP_BACKEND` is normalised once and may be only `deterministic` or `azure`.
  The deterministic reference corpus may accept development header identity;
  Azure-backed retrieval never does.
- If header identity is unavailable, the selected `entra` or `api-key`
  configuration must be complete before startup. Invalid JSON, missing Entra
  identifiers, and unsupported modes are rejected.
- An Azure query backend requires its Search endpoint/index, Azure OpenAI
  endpoint, and at least one chat deployment before the app starts.
- PR Guardian and operational intelligence stay optional. If either is enabled,
  its required state, trust, and evidence inputs are validated before its
  capability factory is called.
- `EIP_CONTROL_PLANE_MODE` is validated at startup. Outside reference mode,
  the external OPA evaluator is required even if `EIP_REQUIRE_OPA=false` is
  accidentally supplied. Both autonomy and PR Guardian kill switches are
  visible as non-secret health-control state.
- Secrets are excluded from settings' default representation and `/healthz`
  reports capability and safety-control state rather than secret values.
- The HTTP middleware validates one `X-Correlation-Id` (falling back to a
  GitHub delivery ID), returns it on the response, and creates a W3C
  `traceparent` child span. Trace headers are observability metadata only;
  malformed values are discarded rather than trusted or reflected.

## Configuration groups

| Group | Inputs parsed at startup | Consumer |
|---|---|---|
| Governed query | `EIP_BACKEND`, header-identity flag, auth mode, request-cost estimate | Query and portal routes |
| Trusted identity | `EIP_AUTH_MODE`, Entra identifiers/issuers/JWKS or API-key principal map | Authentication factory |
| Azure RAG | Azure Search/OpenAI endpoints, deployments, semantic configuration, FinOps rates | Azure RAG adapter |
| PR Guardian | enable flag, GitHub token, state/graph roots, policy version, optional qualified Company Brain context | Shadow Guardian factory |
| Operational intelligence | webhook secret, evidence mode, state/topology paths, Azure Monitor inputs | L1 analysis and L2-proposal factory |
| Feedback | `EIP_FEEDBACK_DB` | Outcome-feedback recorder |
| Runtime safety | control-plane mode, OPA requirement, autonomy and PR Guardian kill switches | `/healthz` control report and execution guardrails |

The exact fields and validation rules are intentionally authoritative in the
typed source record, not duplicated here. When a capability gets a new runtime
input, update `ApplicationSettings`, its factory, and its construction test in
the same change.

## Runtime semantics

Configuration is a process-start snapshot. A value change takes effect only
when the ASGI process restarts, unless a separate, documented live-control
mechanism owns that value. This document does not imply a hot-reload or
control-plane API.

The non-consequential Temporal evidence workflow can carry the same validated
W3C trace context in its typed request/result contract. That verifies the
transport contract, not a deployed cross-process trace export or a production
SLO; those remain operational-evidence work.

The lifecycle removes settings and capabilities it created if startup fails or
shuts down. That matters for test isolation and for an embedding host that
tries a corrected configuration after a rejected startup.

## Verification

```bash
pytest -q tests/test_application_settings.py tests/test_runtime_wiring.py
```

Those tests verify deterministic defaults, fail-closed Azure/auth parsing,
explicit injected settings, secret-redaction behavior, and capability startup
rules. They are source-level evidence only; use the
[production-evidence registry](PRODUCTION-EVIDENCE.md) for a real deployment
claim.
