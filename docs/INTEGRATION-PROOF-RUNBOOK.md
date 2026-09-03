# Deferred private integration-validation runbook

| | |
|---|---|
| **Classification** | Operating runbook — deferred, manual, private-runner-only validation |
| **Purpose** | Produce read-only evidence for a named integration environment |
| **Mutation authority** | None — this runner must not apply Terraform, Helm, schemas, or source changes |
| **Current status** | Deferred operational-validation track; manual, opt-in only; do not run during the active product-build stage |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## Preconditions

Run only from an approved `self-hosted` runner carrying the `eip-private-integration` label that
can resolve the private AKS API and all private service endpoints. The GitHub workflow has no
schedule and cannot start its Azure job until a dispatcher explicitly sets
`run_private_integration=true`. A GitHub-hosted runner is never a substitute for this boundary.

Use two distinct, short-lived Entra access tokens mounted as files:

1. an **allowed** principal that can retrieve a seeded, non-sensitive evidence document; and
2. a **denied** principal that is authenticated but cannot read that same document.

Do not use the Terraform/deployment principal as either caller. Do not put a bearer token in an
environment variable, a shell history, or an output file.

## Required environment contract

| Variable | Meaning |
|---|---|
| `EIP_BASE_URL` | HTTPS private ingress URL for the deployed API |
| `EIP_INTEGRATION_ALLOWED_BEARER_FILE` | Mounted file containing the allowed principal's short-lived bearer token |
| `EIP_INTEGRATION_DENIED_BEARER_FILE` | Mounted file containing the denied principal's short-lived bearer token |
| `EIP_INTEGRATION_ALLOWED_QUERY` / `EIP_INTEGRATION_DENIED_QUERY` | The same governed test question; it must target the seeded document |
| `EIP_INTEGRATION_ALLOWED_REPOSITORY` / `EIP_INTEGRATION_DENIED_REPOSITORY` | Repository scope for that question, when applicable |
| `EIP_INTEGRATION_ALLOWED_SOURCE` | Expected source citation for the allowed result |
| `AZURE_SEARCH_HOST`, `AZURE_OPENAI_HOST`, `AZURE_KEYVAULT_HOST` | Normal service hostnames; each must resolve to private IPs from this runner |
| `EIP_COSMOS_HOST`, `AZURE_POSTGRESQL_HOST`, `EIP_TEMPORAL_HOST` | Managed-state and Temporal dependency hostnames; each must resolve privately |
| `EIP_INTEGRATION_SCOPE` | Named environment, tenant/data classification, Git SHA and image digest summary |
| `EIP_INTEGRATION_EVIDENCE` | Approved writable evidence path, outside the source checkout |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | GitHub `integration` environment identity for the workflow's Azure federated login |
| `AKS_RESOURCE_GROUP`, `AKS_CLUSTER_NAME` | The private AKS context that the approved runner is permitted to inspect |

## Read-only execution

First verify the invocation contract without authenticating to Azure or calling any private
endpoint. A failure writes a `configuration-refused` artifact and is deliberately not evidence of
an environment result:

```bash
python validation/integration_probe.py --check-configuration
```

The GitHub workflow uses the stricter workflow preflight, which also validates its Azure identity
and AKS context settings before it attempts `azure/login`:

```bash
python validation/integration_probe.py --check-workflow-configuration
```

Only after that check succeeds, and only from the approved private runner, run the full probe:

```bash
python -m validation.integration_probe
```

The probe verifies Azure/Kubernetes runner context, HTTPS API health, private DNS, an
evidence-backed authorized query with citations, and the required refusal for the denied
principal. It does not print tokens or query content. A failed probe exits nonzero and blocks the
claim; do not substitute a manual success record.

To dispatch the GitHub workflow, an authorized operator must use the explicit confirmation input:

```bash
gh workflow run integration-proof.yml --ref main -f run_private_integration=true
```

That command is a request to run a read-only probe; it does not create an evidence record or
authorize a promotion.

For the separate non-consequential Temporal worker proof, use
[`TEMPORAL-WORKER-RUNBOOK.md`](TEMPORAL-WORKER-RUNBOOK.md). That probe creates exactly one Temporal
evidence workflow record; it is not part of this HTTP retrieval probe and must be retained as a
separate evidence record.

## Evidence handling and stop conditions

The generated JSON is a scoped input, not production proof by itself. Copy it to the approved
immutable evidence system with its SHA-256, the private-runner identity, deployment/image/IaC
versions, and reviewer approval. Stop the promotion if any item below occurs:

- a dependency resolves to a public address;
- the allowed principal receives no cited evidence;
- the denied principal receives any evidence or model answer;
- identity, private AKS context, TLS, or API health cannot be verified; or
- the output cannot be retained with the required scope and reviewer metadata.

The next proof is ingestion idempotency/deletion/ACL propagation against a governed source, then
Temporal worker restart, audit export, backup/restore, rollback, and kill-switch drills.
