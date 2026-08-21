# Engineering Intelligence Platform

A VP-level transformation blueprint and portfolio-grade reference implementation for evolving enterprise software delivery from AI-assisted engineering to supervised autonomous and self-healing infrastructure.

## What is included

- Executive transformation narrative, KPI model and CFO/FinOps case
- Azure/Azure DevOps + AKS self-healing reference architecture
- 18–24 month technical roadmap
- Runnable FastAPI RAG service with retrieval-before-model authorization boundary
- Optional Azure AI Search + Azure OpenAI backend using Managed Identity
- Deterministic retrieval evaluation harness
- Terraform Azure baseline for network, AKS, Azure AI Search and Log Analytics
- PR Guardian and remediation agent skeletons
- Deterministic self-healing control loop with explicit production approval gate
- OpenTelemetry tracing bootstrap
- OPA remediation policies and tests
- AKS fault/remediation scenarios
- Docker image and Helm chart for AKS deployment
- CI validation for Python, evaluation, Terraform, Helm and container build
- Reproducible 12-slide board deck generator and GitHub Actions artifact build

## Repository map

- `architecture/` — target-state, self-healing architecture and vertical-slice design
- `roadmap/` — 18–24 month execution roadmap
- `docs/` — executive memo, board narrative, KPI system
- `governance/` — operating model and security threat model
- `finops/` — CFO/ROI model
- `app/` — Engineering Intelligence API, Azure RAG adapter, agent control loop and telemetry
- `eval/` — retrieval evaluation harness
- `src/` — RAG orchestrator and agent components
- `infra/terraform/` — Azure reference infrastructure
- `infra/policy/` — policy-as-code and tests
- `demo/aks/` — failure and remediation demonstrations
- `helm/eip/` — AKS deployment chart
- `slides/` — PowerPoint generator
- `.github/workflows/` — CI, deck build and PR intelligence workflows

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

Authentication uses `DefaultAzureCredential`; the search index is expected to expose `source`, `content`, `repo`, and `acl_groups`. ACL filtering is performed in search before any context is sent to the model.

## Milestone 2 vertical slice

`Developer/CI event → authorized retrieval → Azure AI Search → Azure OpenAI → agent plan → policy gate → runbook → verification → telemetry/audit`

See `architecture/vertical-slice.md` for the demo and security invariants.

## Transformation path

1. Secure knowledge and RAG foundation
2. AI-assisted developer workflows
3. PR and architecture guardrails
4. Incident intelligence
5. Predictive change-risk scoring
6. Guardrailed remediation
7. Supervised self-healing infrastructure

The target is not unrestricted autonomy. The control model is: **AI recommends and correlates; deterministic policy authorizes; allow-listed automation executes; verification closes the loop; humans retain authority over high-blast-radius production changes.**
