# Azure DevOps + AKS Self-Healing Reference Architecture

## Control plane
- **AI Gateway / RAG Orchestrator**: authentication, RBAC-aware retrieval, reranking, prompt construction, model routing, audit and cost telemetry.
- **Ingestion Pipeline**: code, Terraform, YAML, ADRs, work items, runbooks, incident records, logs and deployment history.
- **Retrieval Layer**: Azure AI Search or PostgreSQL/pgvector plus metadata/lineage store.
- **SDLC Agents**: PR Guardian, Deployment Failure Investigator, Drift Detector and Remediation Agent.
- **Policy Engine**: Azure Policy and/or OPA authorizes mutations.
- **Runbook Engine**: deterministic, allow-listed remediation procedures.

## Closed-loop flow

`Event -> observe -> retrieve evidence -> reason -> propose -> policy check -> approve/execute -> verify -> audit -> PR/ticket`

## Azure reference components
- Entra ID and Managed Identity
- Private Endpoints and VNet integration
- Azure OpenAI or enterprise model gateway
- Azure AI Search / PostgreSQL pgvector
- Azure Container Apps or AKS for orchestration
- Azure Monitor, Log Analytics, Application Insights and OpenTelemetry
- Azure DevOps Repos, Boards and Pipelines
- AKS, Azure Resource Graph, Azure Policy and Key Vault

## Safety invariants
1. Authorization happens before retrieval.
2. The LLM recommends; policy authorizes mutation.
3. Production mutation is restricted to explicit allow-listed runbooks.
4. Every answer/action carries evidence and an audit trail.
5. Self-healing begins with reversible, low-blast-radius actions.
6. Verification is mandatory; failed remediation escalates rather than loops indefinitely.
7. Kill switch and human override remain available at every autonomous maturity level.

## Example AKS incident
An HPA configuration change causes CPU saturation and pod instability. The platform correlates the alert with the recent deployment, retrieves prior similar incidents, identifies the HPA diff, calculates blast radius, recommends rollback, checks policy, runs an approved rollback only if permitted, verifies SLO recovery, then opens a corrective PR and incident record.