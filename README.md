# Engineering Intelligence Platform

A VP-level transformation blueprint and portfolio-grade reference implementation for evolving enterprise software delivery from AI-assisted engineering to supervised autonomous and self-healing infrastructure.

## What is included

- Executive transformation narrative, KPI model and CFO/FinOps case
- Azure/Azure DevOps + AKS self-healing reference architecture
- 18–24 month technical roadmap
- Runnable FastAPI RAG service with retrieval-before-model authorization boundary
- Deterministic retrieval evaluation harness
- Terraform Azure baseline for network, AKS, Azure AI Search and Log Analytics
- PR Guardian and remediation agent skeletons
- OPA remediation policies and tests
- AKS OOM incident simulation plus reversible remediation runbook
- CI validation for Python tests, evaluation and Terraform
- Reproducible 12-slide board deck generator and GitHub Actions artifact build

## Repository map

- `architecture/` — target-state and self-healing architecture
- `roadmap/` — 18–24 month execution roadmap
- `docs/` — executive memo, board narrative, KPI system
- `governance/` — operating model and security threat model
- `finops/` — CFO/ROI model
- `app/` — runnable Engineering Intelligence API
- `eval/` — retrieval evaluation harness
- `src/` — RAG orchestrator and agent components
- `infra/terraform/` — Azure reference infrastructure
- `infra/policy/` — policy-as-code and tests
- `demo/aks/` — failure and remediation demonstration
- `slides/` — PowerPoint generator
- `.github/workflows/` — CI, deck build and PR intelligence workflows

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
uvicorn app.main:app --reload
```

Then query the local service:

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
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```

AKS demonstration after creating namespace `eip-demo`:

```bash
kubectl apply -f demo/aks/incident.yaml
kubectl -n eip-demo get pods -w
NAMESPACE=eip-demo bash demo/aks/remediate.sh
```

## Transformation path

1. Secure knowledge and RAG foundation
2. AI-assisted developer workflows
3. PR and architecture guardrails
4. Incident intelligence
5. Predictive change-risk scoring
6. Guardrailed remediation
7. Supervised self-healing infrastructure

The target is not unrestricted autonomy. The control model is: **AI recommends and correlates; deterministic policy authorizes; allow-listed automation executes; verification closes the loop; humans retain authority over high-blast-radius production changes.**
