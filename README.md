# Engineering Intelligence Platform

A VP-level transformation blueprint and portfolio-grade reference implementation for evolving enterprise software delivery from AI-assisted engineering to supervised autonomous and self-healing infrastructure.

> **Status:** this repository contains a working reference implementation plus target-state architecture. It is intentionally not presented as a production-ready autonomous control plane. See `architecture/ALIGNMENT-REVIEW.md` for the implemented-vs-target gap analysis and grooming priorities.

## What is included

- Executive transformation narrative, KPI model and CFO/FinOps case
- Azure/Azure DevOps + AKS self-healing target architecture
- 18–24 month technical roadmap and A–Z program backlog
- Runnable FastAPI RAG service with retrieval-before-model authorization boundary
- Optional Azure AI Search + Azure OpenAI backend using Managed Identity credentials
- Production-oriented code ingestion primitives: GitHub/ADO events, AST chunking, ACL metadata, ledger/DLQ/replay and embedding contract
- Service dependency graph, deterministic change-risk scoring and PR Guardian rendering primitives
- Incident evidence/timeline/RCA and SLO-awareness primitives
- Typed remediation catalog, bounded L0–L4 autonomy policy, verification/rollback and simulation primitives
- Workflow-state, plan-bound approval, security/provenance and FinOps/control-tower primitives
- Cloud-provider and degraded-mode contracts while Azure remains the reference implementation
- Terraform Azure baseline for network, AKS, Azure AI Search and Log Analytics
- OpenTelemetry tracing bootstrap
- OPA remediation policy examples and tests
- AKS fault/remediation scenarios
- Docker image and Helm chart for AKS deployment
- CI validation for Python, evaluation, Terraform, Helm and container build
- Reproducible 12-slide board deck generator and GitHub Actions artifact build

## Repository map

- `architecture/` — target-state architecture, alignment review and vertical-slice design
- `roadmap/` — 18–24 month roadmap and program backlog
- `docs/` — executive memo, board narrative, KPI system
- `governance/` — operating model and security threat model
- `finops/` — CFO/ROI model and attribution/outcome primitives
- `app/` — Engineering Intelligence API, Azure RAG adapter, agent control loop and telemetry
- `ingestion/` — source events, chunking, ACLs, indexing, ledger/DLQ and embeddings contracts
- `intelligence/` — service graph, change risk, PR Guardian and incident intelligence
- `remediation/` — runbook catalog, policy, execution and simulation
- `orchestration/` — workflow state and approval primitives
- `security/` — adversarial and software-provenance controls
- `providers/` and `resilience/` — cloud-neutral interfaces and degraded-mode policy
- `portal/` — service/control-tower view models
- `eval/` — retrieval evaluation harness
- `src/` — early RAG/agent prototypes retained for reference
- `infra/terraform/` — Azure infrastructure baseline; private production foundation is still a target gap
- `infra/policy/` — policy-as-code examples and tests
- `demo/aks/` — failure and remediation demonstrations
- `helm/eip/` — AKS deployment chart
- `slides/` — PowerPoint generator
- `.github/workflows/` — current CI and board-deck build workflows; PR Guardian deployment wiring is still pending

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
uvicorn app.main:app --reload
```

Query local deterministic mode:

```bash
curl -s http://127.0.0.1:8000/v1/query \
  -H 'content-type: application/json' \
  -H 'x-eip-groups: engineering' \
  -d '{"question":"How should production remediation work?"}'
```

Run validation:

```bash
pytest -q
python eval/evaluate.py
python demo/aks/scenario_runner.py
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
helm lint helm/eip
docker build -t eip:local .
```

## Azure-backed mode

Set `EIP_BACKEND=azure` plus:

- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`

Authentication uses `DefaultAzureCredential`; the search index is expected to expose source/content/repository/ACL metadata. ACL filtering is performed before retrieved context is sent to the model.

The target production Azure design additionally requires private endpoints/DNS, workload identity, explicit RBAC, Key Vault, an authoritative metadata/workflow/audit store, controlled egress and production observability. These are tracked in the architecture alignment review rather than implied to already exist.

## North-star control flow

`Events → governed ingestion → knowledge/service graph → authorized retrieval/reasoning → deterministic policy → approval/runbook → execute → verify → rollback/escalate → audit/PR/ticket`

## Transformation path

1. Secure knowledge and RAG foundation
2. AI-assisted developer workflows
3. PR and architecture guardrails
4. Incident intelligence
5. Predictive change-risk scoring
6. Guardrailed remediation
7. Supervised self-healing infrastructure

The target is not unrestricted autonomy. **AI recommends and correlates; deterministic policy authorizes; allow-listed automation executes; verification closes the loop; humans retain authority over high-blast-radius production changes.** L5 unrestricted autonomy is out of scope.
