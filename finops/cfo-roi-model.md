# CFO / FinOps ROI Model

## Value equation
Annual value = reclaimed engineering capacity + avoided incident cost + reduced onboarding cost + avoided regression/security cost - platform operating cost.

## Illustrative capacity case
For 300 engineers saving 30 minutes per working day:
- 150 engineering hours/day
- ~3,000 hours/month at 20 working days
- ~36,000 hours/year

Convert to loaded labor cost using finance-approved assumptions; do not represent all reclaimed time as direct headcount reduction. Treat it primarily as capacity returned to roadmap delivery.

## Cost buckets
- Model inference and embeddings
- Vector/hybrid search
- Orchestrator compute
- Observability/log retention
- Engineering/platform staffing
- Security/evaluation tooling

## Cost controls
- Route routine tasks to smaller models.
- Reserve premium models for high-value reasoning.
- Cache deterministic/repeated results.
- Incrementally re-embed only changed content.
- Enforce context/token budgets.
- Track cost per user, team, repository and agent.
- Apply monthly budget alerts and anomaly detection.

## Investment gates
### Gate 1 — 90 days
Prove retrieval quality, security boundary and measurable developer usefulness.
### Gate 2 — 6–8 months
Prove PR quality and reduced review friction without unacceptable false positives.
### Gate 3 — 12 months
Prove incident/MTTR benefit.
### Gate 4 — 16+ months
Fund autonomous remediation only for failure classes with demonstrated safety and positive ROI.

## CFO dashboard
Show platform run rate, cost per active user, cost per successful task, capacity reclaimed, incident hours avoided and forecast payback range.