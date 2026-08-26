# Operational Intelligence Runbook (L1 analysis, L2 proposals)

This runbook covers the two operational-intelligence triggers: the API routes that
turn a deployment failure or a fired alert into an evidence-backed analysis, and the
two CLIs that run the same composition offline.

**What this does:** collects evidence, correlates it into hypotheses (L1), and emits
proposals with an exact action and a rollback path (L2).

**What this refuses to do:** execute a proposal, restart or roll back a workload,
open a pull request that changes code, change a threshold, or grant autonomy. Every
proposal carries `requires_human: true`, and that flag is a module constant in
`product/l2_proposals.py`, not a configuration value.

---

## Routes

Both routes live in `app/operations_api.py` and are mounted by `app/main.py`.

| Route | Payload | Service |
| --- | --- | --- |
| `POST /v1/events/deployment` | Azure DevOps service hook (build/release completed) | `DeploymentFailureInvestigatorService` |
| `POST /v1/events/incident` | Azure Monitor common alert schema | `IncidentIntelligenceService` |

### Authentication

Both routes require the shared secret `EIP_OPERATIONS_WEBHOOK_SECRET` in the
`X-EIP-Operations-Secret` header. The comparison is constant-time
(`hmac.compare_digest`).

| Condition | Status |
| --- | --- |
| `EIP_OPERATIONS_WEBHOOK_SECRET` unset | `503` — capability is not configured |
| Header missing or wrong | `401` |
| Secret matches, capability not wired on this process | `503` |
| Payload not parseable as its schema | `400` |
| Deployment payload references evidence the provider cannot produce | `422` |
| Otherwise | `200` |

`GET /healthz` reports `capabilities.operations` as `configured` or `unconfigured`.

### Payload expectations

`POST /v1/events/deployment` is parsed by
`integrations/azure_devops/deployment_failure.normalize_service_hook`. It accepts a
run whose `resource.result` is `failed`, `canceled`, or `partiallysucceeded`, and
rejects anything else with `400`. The deployment id is
`ado:<project>:<pipeline>:<run>`.

`POST /v1/events/incident` is parsed by `normalize_common_alert`. Azure Monitor does
not carry a service or environment in the common alert schema, so both must be set
as **alert-rule custom properties**:

```jsonc
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": { "alertId": ".../alerts/INC-42", "monitorCondition": "Fired" },
    "customProperties": { "service": "payments", "environment": "prod" }
  }
}
```

Missing `service` or `environment` is a `400` naming the missing key — the platform
does not guess a service from a resource id, because attributing evidence to the
wrong service produces a confidently wrong analysis. A payload whose
`monitorCondition` is not `Fired` (a resolution notification) returns
`{"status": "ignored", ...}` without opening a workflow.

### Response

```jsonc
{
  "status": "investigated",
  "autonomy_level": "L2-propose",
  "executed": false,
  "correlation_id": "...",          // the control-plane workflow correlation id
  "workflow_id": "incident:INC-42",
  "service": "payments",
  "environment": "prod",
  "impacted_services": ["checkout", "payments"],   // incident route only
  "analysis": { "hypotheses": [...], "timeline": [...] },
  "proposals": [ { "kind": "...", "requires_human": true, ... } ]
}
```

The response is the entire delivery mechanism for the API path. Nothing is written
to GitHub, Azure DevOps, or Kubernetes.

---

## Configuration

The capability is **enabled** when either `EIP_OPERATIONS_WEBHOOK_SECRET` or
`EIP_OPERATIONS_EVIDENCE` is set. Enabled-but-incomplete raises a `RuntimeError` at
startup listing every missing name — the process refuses to start half-configured
rather than answering `503` forever.

| Variable | Required | Meaning |
| --- | --- | --- |
| `EIP_OPERATIONS_WEBHOOK_SECRET` | API only | Shared secret for both routes |
| `EIP_OPERATIONS_EVIDENCE` | yes | `azure-monitor` or `fixture:<path>` |
| `EIP_STATE_DIR` | yes | Directory for `state.db`, `audit.db`, `topology.db` |
| `EIP_TOPOLOGY_DB` | no | Overrides `<EIP_STATE_DIR>/topology.db` |

### Evidence mode `azure-monitor`

Live Azure Monitor Logs through `integrations/azure/monitor.AzureMonitorEvidenceClient`,
which builds a `DefaultAzureCredential` and queries a Log Analytics workspace.

| Variable | Required | Meaning |
| --- | --- | --- |
| `AZURE_TENANT_ID` | yes | Entra tenant for `DefaultAzureCredential` |
| `AZURE_CLIENT_ID` | yes | Workload identity / app registration client id |
| `EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID` | yes | Workspace the evidence query runs against |
| `EIP_OPERATIONS_EVIDENCE_KQL` | no | Overrides the default query; `{service}` is substituted |
| `EIP_OPERATIONS_EVIDENCE_LOOKBACK_MINUTES` | no | Query window, default `120` |

The default KQL projects `TimeGenerated, Kind, SeverityLevel, Message, Id` from
`KubeEvents`, `AppExceptions`, and `AppTraces`. Every deployment has a different
table layout; set `EIP_OPERATIONS_EVIDENCE_KQL` rather than relying on the default
for anything that matters.

### Evidence mode `fixture:<path>`

A JSON file of evidence events. This is what reference deployments, demos, and the
two CLIs use. It never reaches the network. A path that does not exist is a startup
`RuntimeError`.

The file is a list of event objects, or an object with any of these keys:

| Key | Used by |
| --- | --- |
| `events` | both paths |
| `deployment_events` | `POST /v1/events/deployment` and `investigate_deployment_failure.py` |
| `incident_events` | `POST /v1/events/incident` and `correlate_incident.py` |

Each event maps onto `intelligence.incidents.EvidenceEvent`. String fields may
contain `${service}`, `${environment}`, `${incident_id}`, and `${deployment_id}`;
tokens that do not apply to the current path are left untouched.

```jsonc
{
  "deployment_events": [
    {
      "id": "deploy-previous",
      "kind": "deployment",
      "service": "${service}",
      "timestamp": "2026-08-21T10:00:00Z",
      "summary": "release v1",
      "source": "azure-devops",
      "severity": 1,
      "attributes": { "commit": "aaa1111" }
    },
    {
      "id": "${deployment_id}",
      "kind": "deployment",
      "service": "${service}",
      "timestamp": "2026-08-22T10:00:00Z",
      "summary": "release v2",
      "source": "azure-devops",
      "severity": 1,
      "attributes": { "commit": "bbb2222" }
    }
  ],
  "events": [
    {
      "id": "alert-1",
      "kind": "alert",
      "service": "${service}",
      "timestamp": "2026-08-22T10:04:00Z",
      "summary": "readiness probe failed for ${service}",
      "source": "azure-monitor",
      "severity": 4
    }
  ]
}
```

`kind` is one of `alert`, `metric`, `log`, `trace`, `k8s_event`, `deployment`,
`incident`. The deployment path needs an event whose `id` equals the incoming
deployment id (hence `${deployment_id}`) and whose `kind` is `deployment`, or the
analysis fails with `422`.

---

## CLIs

Both read a saved payload, run the same composition as the API, and print the same
document to stdout as JSON. They do not need the webhook secret.

```bash
python -m scripts.investigate_deployment_failure \
  --payload ado-service-hook.json \
  --evidence fixture:operations-evidence.json \
  --state-dir .eip

python -m scripts.correlate_incident \
  --payload common-alert.json \
  --evidence fixture:operations-evidence.json \
  --state-dir .eip
```

`--evidence` and `--state-dir` default to `EIP_OPERATIONS_EVIDENCE` and
`EIP_STATE_DIR`; `--state-dir` falls back to `.eip`.

`--publish github --repository owner/name` opens or updates a single issue marked
`<!-- eip-operations-intelligence -->` carrying the analysis and the proposals. It
requires `GITHUB_TOKEN` and raises `RuntimeError` without it. It opens an **issue**
— it does not open a pull request, push a branch, or run a runbook.

---

## What an L2 proposal is

`product/l2_proposals.build_proposals` is a pure function over the analysis. Every
proposal has:

- `kind` — `corrective-pr`, `runbook`, or `ticket`
- `title`
- `exact_action` — the precise thing a human should do, with real identifiers in it
- `rollback_path` — how to undo it if it turns out to be wrong
- `evidence_refs` — the evidence ids that support it
- `requires_human` — always `true`

### Mapping

| Condition | Kind |
| --- | --- |
| Two deployment events with different commits (or a `last_good_commit` / `previous_commit` attribute) | `corrective-pr` naming the exact `<last-good>..<current>` range |
| A hypothesis matching a known failure class with an allow-listed runbook | `runbook` |
| Neither | `ticket` |

Failure-class precedence mirrors `remediation/planner.py`: CrashLoopBackOff,
readiness regression, and OOM/memory pressure each beat the generic
deployment-correlation class.

The allow-listed runbook ids in `ALLOW_LISTED_RUNBOOKS` are **copied** from
`remediation/catalog.py`. The `remediation` package is intentionally not in the API
image closure (see `.dockerignore` and `app/import_closure.py`), so `l2_proposals`
must not import it. `tests/test_l2_proposals.py` imports the real catalog and
asserts each copied id still exists there with the same failure class and rollback
id, so the copy cannot drift silently.

### What an L2 proposal is not

- It is **not** an execution. Nothing in this path calls a Kubernetes adapter, a
  runbook executor, or a digital twin.
- It is **not** an approval. A `runbook` proposal names an allow-listed runbook; the
  operator still has to confirm the runbook's live preconditions before running it.
- It is **not** a merged pull request. A `corrective-pr` proposal describes the
  `git revert` a human runs and the PR they open for service-owner review.
- It is **not** evidence that the platform is at L2. It is the mechanism L2 would
  use; whether the stage has been exited is decided by the evidence registry, not
  by this code existing.

---

## Image closure

`product/incident_service.py` ships in the release image, and `topology/` is in
`SHIPPED_PACKAGES` and the Dockerfile `COPY` list because the incident service
resolves a blast radius from the topology store. `product/self_healing_service.py`
and `product/durable_self_healing.py` remain in `.dockerignore`: they import the
execution plane, which this stage deliberately does not ship.
