# KPI System

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Engineering Intelligence lead |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | metric definitions; only metrics marked *collected* are emitted by code |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


## Measurement basis

Every number reported against these definitions carries one of three labels, matching the
product strategy and `portal/timeseries.py` (`MetricBasis`):

- **measured** — computed from retained source events with lineage;
- **derived** — computed from measured inputs by a stated formula;
- **modeled** — an assumption or projection; never quoted as an outcome.

Metrics marked *(collected)* below have an emitting code path today; the rest are definitions
awaiting a source.

## Engineering outcomes
- Median time to answer internal technical questions
- New-engineer time to first independent production change
- PR cycle time and reviewer wait time
- Change failure rate *(collected)* and escaped regression rate
- MTTR *(collected)*, MTTD and repeat-incident rate
- Percentage of incidents correlated automatically with recent changes

## AI quality
- Retrieval precision@k / recall@k
- Citation coverage and citation correctness
- Answer acceptance rate *(collected as recommendation acceptance)*
- Agent precision *(collected)* and false-positive rate
- Remediation success rate and rollback rate *(rollback rate collected)*

## Safety
- Unauthorized retrieval attempts blocked
- Prompt-injection detections
- Secret/PII redaction events *(collected as a gateway count and span attribute)*
- Autonomous actions by risk tier
- Human overrides and kill-switch events

## FinOps
- Cost per query, repo, team, workflow and agent
- Tokens per successful task
- Cache hit rate
- Premium-model routing percentage
- Infrastructure cost per active engineering user

## Suggested initial targets
Targets must be baselined empirically, but an executive program may aim for 30–50% faster internal knowledge retrieval, 20–30% shorter PR cycle time, 30–40% lower MTTR and materially fewer repeat incidents before expanding autonomy.