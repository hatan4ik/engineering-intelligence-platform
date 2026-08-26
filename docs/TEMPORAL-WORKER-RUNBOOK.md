# Temporal Worker Runbook

| | |
|---|---|
| **Status** | Implemented worker boundary; no Temporal environment has been deployed or certified |
| **Scope** | L0 durable-scheduling evidence only; no business state, audit export, or remediation mutation |
| **Decision** | [`../architecture/ADR-001-temporal-control-plane.md`](../architecture/ADR-001-temporal-control-plane.md) |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## What is implemented

`orchestration.temporal_worker` starts a pinned Temporal Python SDK worker only when
`EIP_CONTROL_PLANE_MODE=temporal` and every managed dependency is explicit. It registers exactly
one deterministic workflow: `eip.control-plane-evidence.v1`.

That workflow returns the caller's bounded request/correlation identifiers and its Temporal
workflow ID. Its result is explicitly `mutation_performed: false`. It does not call Cosmos, write
the EIP audit log, execute a runbook, or approve/block a PR. This small slice proves the worker
registration, mTLS connection contract, task-queue binding, and restart boundary without creating
a false claim that the control plane is ready for consequential work.

The worker is enabled separately through `helm/eip` under `temporalWorker.enabled`; it defaults to
`false`. The deployment has a distinct Azure Workload Identity service account, at least two
replicas, a disruption budget, non-root/read-only filesystem settings, and a writable `emptyDir`
only for `/tmp`.

## Mandatory configuration

All values below are required when the worker is enabled. No local default or environment fallback
exists.

| Input | Source | Requirement |
|---|---|---|
| Temporal endpoint/namespace/task queue | reviewed worker values | Cluster-private `host:port`, dedicated namespace and queue |
| mTLS server name and Secret | approved certificate delivery | Existing Secret; no PEM material in Helm values or environment variables |
| `ca.crt`, `tls.crt`, `tls.key` | mounted Secret keys | CA, client certificate, and private key read from fixed mounted paths |
| Cosmos endpoint/database/container | reviewed worker values + Workload Identity RBAC | Required prerequisite for the future authoritative-state activity bridge |
| Immutable audit evidence URI | reviewed worker values | Remote URI only; a `file:` URI is rejected |
| Image | reviewed worker values | Existing digest-pinned image; the worker never accepts a mutable tag |

The worker exits rather than connecting if any setting or PEM file is absent/malformed. The chart
does not create the certificate Secret, PostgreSQL user, Temporal databases, or schemas.

## Render-only preflight

Use the CI fixture only to validate template shape; it contains `example.invalid` identifiers and
cannot be applied:

```bash
helm lint helm/eip --values helm/eip/values.ci.yaml
helm template eip helm/eip --values helm/eip/values.ci.yaml
```

Before any private integration release, use an approved private runner to verify the rendered
image digest, Workload Identity client IDs, private DNS resolution, mTLS chain/server name, the
separately migrated Temporal server, and the least-privilege Cosmos access. Do not use `--set` for
certificate material, database credentials, or audit endpoints.

## Integration proof and stop conditions

The first private proof is a read-only Temporal evidence workflow. Retain its request ID, Temporal
workflow ID/run ID, namespace, queue, worker image digest, mTLS/DNS verification, worker restart
observation, and independent reviewer approval in the immutable evidence system.

From an approved private runner with the reviewed worker environment and mounted client
certificate files, assign retained identifiers and run the probe once:

```bash
EIP_TEMPORAL_PROBE_REQUEST_ID='proof-2026-08-26-001' \
EIP_TEMPORAL_PROBE_CORRELATION_ID='integration-proof-2026-08-26-001' \
EIP_TEMPORAL_PROBE_EVIDENCE='/approved-evidence/temporal-control-plane-evidence.json' \
python -m validation.temporal_control_plane_probe
```

The command starts a Temporal workflow record by design, but the registered workflow is
non-consequential and rejects a result that reports a mutation. It must not run from a public
workstation or with unreviewed client certificates. Copy the resulting SHA-256 and the Temporal
workflow run reference into the immutable evidence record; do not rely on the local JSON file.

Stop immediately if mTLS validation fails, the endpoint resolves publicly, the worker requires a
SQLite fallback, an evidence result reports a mutation, or an artifact cannot be tied to the
deployed image/namespace/task queue. A GitHub Actions run, chart rendering, or local test is not
integration evidence.

## Deliberately deferred

The next implementation slice must add the authoritative Cosmos state activity and immutable audit
export adapter together, with idempotency, replay, cancellation, restore, and worker-failover
tests. Only after that proof can a PR, incident, approval, or remediation workflow be considered
for Temporal execution. This worker must not be repurposed as a generic task executor in the
meantime.
