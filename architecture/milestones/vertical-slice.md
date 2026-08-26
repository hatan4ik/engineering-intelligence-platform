# Milestone 2 — End-to-End Vertical Slice

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | reference E2E slice; not deployed |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../../docs/CURRENT-POSITION.md) |


## Flow

`Developer/CI event → authorized retrieval → Azure AI Search → Azure OpenAI → agent plan → policy gate → runbook → verification → telemetry/audit`

## Runtime modes

- `EIP_BACKEND=deterministic`: local/CI mode with no cloud dependency.
- `EIP_BACKEND=azure`: Azure AI Search + Azure OpenAI using `DefaultAzureCredential`.

## Security invariants

1. ACL filtering occurs in Azure AI Search before evidence reaches the LLM.
2. Empty authorized retrieval returns an explicit insufficient-evidence answer.
3. Production mutation requires approval even for low-risk allow-listed runbooks.
4. High-blast-radius or irreversible actions always escalate.
5. Every query/control-loop step is designed to emit OpenTelemetry traces.

## Demonstration

1. Run API locally with deterministic backend.
2. Execute tests and `demo/aks/scenario_runner.py`.
3. Build the container and install the Helm chart.
4. Switch to Azure backend with Managed Identity and required endpoint/deployment variables.
5. Send a repo-scoped query with `X-EIP-Groups` and inspect evidence/citations.
6. Run safe and unsafe remediation scenarios and compare `COMPLETE` vs `ESCALATE` paths.
