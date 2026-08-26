# Private integration-proof runbook

| | |
|---|---|
| **Purpose** | Produce read-only evidence for a named integration environment |
| **Mutation authority** | None — this runner must not apply Terraform, Helm, schemas, or source changes |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## Preconditions

Run only from an approved private runner that can resolve the private AKS API and all private
service endpoints. Use two distinct, short-lived Entra access tokens mounted as files:

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

## Read-only execution

```bash
python -m validation.integration_probe
```

The probe verifies Azure/Kubernetes runner context, HTTPS API health, private DNS, an
evidence-backed authorized query with citations, and the required refusal for the denied
principal. It does not print tokens or query content. A failed probe exits nonzero and blocks the
claim; do not substitute a manual success record.

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
