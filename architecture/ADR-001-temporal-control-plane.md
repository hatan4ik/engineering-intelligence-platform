# ADR-001: Temporal with private PostgreSQL for durable control-plane workflows

| | |
|---|---|
| **Status** | Accepted for the integration-environment implementation path |
| **Decision date** | 2026-08-26 |
| **Scope** | Durable workflow execution only; not a production certification or deployment record |

## Context

SQLite preserves useful local contracts for workflow state, audit chaining, retry, and DLQ tests,
but it is not a multi-worker production control plane. Remediation and approvals can wait for
minutes or hours and must survive worker loss without a lease-based queue becoming the source of
truth.

## Decision

Use **Temporal Server** deployed to the private AKS environment with a private, zone-redundant
Azure PostgreSQL Flexible Server. PostgreSQL holds Temporal's separate `temporal` and
`temporal_visibility` databases. Cosmos remains the authoritative application-state adapter;
neither Temporal visibility nor Azure AI Search is the system of record for service and workflow
records.

The pinned Helm wrapper at [`../helm/temporal`](../helm/temporal) uses upstream Temporal chart
`1.6.0` and has no deployable defaults. It requires a private database hostname and pre-created
Kubernetes Secret; the normal server release has `createDatabase: false` and
`manageSchema: false`. Database/user bootstrap and schema migration are distinct, reviewable
release actions.

## Consequences

- `EIP_CONTROL_PLANE_MODE=temporal` rejects construction of the local SQLite state, audit, and
  queue implementations. The worker must supply Temporal, Cosmos, and immutable-audit settings.
- A dedicated Temporal worker adapter and worker deployment are still required before any agent
  workflow can execute through Temporal.
- Secrets must arrive through the approved private secret-delivery path; no password is a Helm
  value or committed Terraform value.
- Before integration use, validate private DNS/TLS, least-privilege DB user, schema migration,
  backup/restore, Temporal worker restart, and immutable audit evidence.

## Alternatives considered

| Alternative | Decision |
|---|---|
| Continue with SQLite lease queue | Rejected: reference-only and unsafe for distributed long-running remediation |
| Service Bus plus custom state machine | Rejected for the durable workflow authority: it leaves replay/long-await/compensation correctness in custom code |
| Azure Durable Functions | Not selected: it would require a separate execution model and does not match the confirmed Temporal decision |
