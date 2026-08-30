# Runtime Capability Contract

| | |
|---|---|
| **Status** | Current implementation contract — source-only, reference capability mapping; not deployment or production evidence |
| **Canonical source** | [`../requirements/runtime-capability-baseline.json`](../requirements/runtime-capability-baseline.json) |
| **Validation** | `python scripts/verify_runtime_capability_contract.py --check-rendered` |
| **Current position** | [`CURRENT-POSITION.md`](CURRENT-POSITION.md) |
| **Evidence rule** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## Purpose

This contract prevents source code, Helm, Terraform, and high-level status documentation from
quietly describing different runtime scopes. It checks that each declared environment variable is
either explicitly rendered by the applicable chart or explicitly absent from it, and that the
associated code, infrastructure foundation, and truthful documentation pointers still exist.

A passing check establishes only that the checked-in sources agree. It does **not** establish a
configured environment, a healthy deployment, secret delivery, network reachability, data-plane
isolation, or production readiness. Every row remains `not-collected` for operational evidence.

## Current source contract

<!-- BEGIN GENERATED RUNTIME CAPABILITY TABLE -->
| ID | Capability | Source state | Chart surface | Terraform support | Evidence |
|---|---|---|---|---|---|
| EIP-RUNTIME-API-QUERY | Azure-backed API query | chart-exposed-reference | exposes `EIP_BACKEND`, `EIP_ALLOW_HEADER_IDENTITY`, `EIP_AUTH_MODE`, `EIP_ENTRA_TENANT_ID`, `EIP_ENTRA_AUDIENCE`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` | `azurerm_search_service`, `azurerm_cognitive_account`, `azurerm_kubernetes_cluster`, `azurerm_user_assigned_identity` | not-collected |
| EIP-RUNTIME-API-CONTROLS | API safety-control reporting | chart-exposed-reference | exposes `EIP_CONTROL_PLANE_MODE`, `EIP_REQUIRE_OPA`, `EIP_AUTONOMY_KILL_SWITCH`, `EIP_PR_GUARDIAN_KILL_SWITCH` | none declared | not-collected |
| EIP-RUNTIME-PR-GUARDIAN | PR Guardian webhook product | code-reference-only | intentionally omits `EIP_PR_GUARDIAN_WEBHOOK`, `EIP_GITHUB_WEBHOOK_SECRET`, `GITHUB_TOKEN`, `EIP_STATE_DIR` | none declared | not-collected |
| EIP-RUNTIME-OPERATIONS | Operational-intelligence webhooks | code-reference-only | intentionally omits `EIP_OPERATIONS_WEBHOOK_SECRET`, `EIP_OPERATIONS_EVIDENCE`, `EIP_STATE_DIR` | none declared | not-collected |
| EIP-RUNTIME-TEMPORAL-EVIDENCE | Temporal evidence worker | chart-exposed-reference | exposes `EIP_CONTROL_PLANE_MODE`, `EIP_TEMPORAL_ENDPOINT`, `EIP_TEMPORAL_NAMESPACE`, `EIP_TEMPORAL_TASK_QUEUE`, `EIP_TEMPORAL_TLS_SERVER_NAME`, `EIP_TEMPORAL_TLS_CA_CERT_PATH`, `EIP_TEMPORAL_TLS_CLIENT_CERT_PATH`, `EIP_TEMPORAL_TLS_CLIENT_KEY_PATH` | `azurerm_postgresql_flexible_server`, `temporal_postgresql_host` | not-collected |
| EIP-RUNTIME-REMEDIATION | Plan-bound remediation workflow | code-reference-only | intentionally omits `EIP_TEMPORAL_REMEDIATION_WORKFLOWS`, `EIP_REMEDIATION_APPROVAL_SECRET`, `EIP_OPA_ENDPOINT`, `EIP_REMEDIATION_SOURCE_NAMESPACE`, `EIP_REMEDIATION_POLICY_PATH`, `EIP_REMEDIATION_EVIDENCE_PROVIDER` | none declared | not-collected |
<!-- END GENERATED RUNTIME CAPABILITY TABLE -->

## Interpretation and safety boundary

`chart-exposed-reference` means the chart deliberately renders the named configuration, while the
repository still has only reference behavior and no retained environment evidence. The API chart
can configure the authenticated Azure query path and initial safety-control state. Kill-switch
values are process environment values: a Helm change is explicitly **restart-required**, not a
live control-plane API.

`code-reference-only` means the source contains a bounded capability but the default API or worker
chart deliberately does not configure it. PR Guardian and operational-intelligence webhooks need
their own approved secret/configuration surface before they can be enabled. The Temporal worker
is limited to the non-consequential evidence workflow; the plan-bound remediation workflow remains
unconfigured, is not a deployed claim, and cannot obtain authority merely by adding environment
variables.

Terraform markers identify a foundation that the source can consume; Terraform does not deploy
the Helm release or prove any runtime integration. A new server, workload identity, secret,
network rule, or operator process must be reflected in its own reviewed deployment design and
retained evidence, not inferred from this table.

## Change rule

Update the JSON baseline and this generated view in the same pull request whenever a runtime
capability, environment variable, chart exposure, Terraform dependency, or status claim changes.
For a previously omitted variable, choose deliberately: add a reviewed chart/configuration
surface, or leave it omitted and state why. Do not promote a row's `evidence_status` from this
source file; operational evidence belongs in the immutable evidence registry after independent
review.
