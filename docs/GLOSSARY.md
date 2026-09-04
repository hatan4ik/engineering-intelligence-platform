# Company Brain Glossary and Hover Terms

| | |
|---|---|
| **Classification** | Reference terminology and documentation usability contract |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-04 against `main` at `615c402` |
| **Documentation governance** | [Documentation Governance and Register](DOCUMENT-STATUS.md) |
| **Current product state** | [Current Position](CURRENT-POSITION.md) |

This glossary is the canonical expansion of terms used across the Company Brain documentation.
It clarifies terminology only; it does not make a capability, deployment, or production claim.

## Hover behavior

GitHub-rendered Markdown preserves the native HTML `title` attribute on a `span`. A marked term
therefore uses this form:

```html
<span title="Azure Kubernetes Service">AKS</span>
```

On a desktop browser, hovering over the marked term shows the expansion. The tooltip is a
convenience, not the only definition: authors spell out an unfamiliar term on its first
meaningful use when the reader needs the definition to understand the decision. Keyboard and
touch readers can use this glossary directly.

Use hover terms in reader-facing prose and tables; do not add them inside code blocks, command
examples, environment-variable names, file paths, URLs, or identifiers. Reuse the exact expansion
from this glossary and add a new term here in the same pull request when introducing a new
domain-specific abbreviation.

## Product, delivery, and architecture

| Term | Expansion | Meaning in this repository |
|---|---|---|
| ACL | Access Control List | The groups and users permitted to retrieve a source or evidence item. |
| ACLs | Access Control Lists | Multiple access-control lists or their collective retrieval constraints. |
| ADR | Architecture Decision Record | A durable record of an architecture decision, context, and consequences. |
| ADRs | Architecture Decision Records | Multiple durable records of architecture decisions. |
| ADO | Azure DevOps | Microsoft service family used here as a potential engineering-system integration. |
| AKS | Azure Kubernetes Service | Azure-managed Kubernetes used by the target runtime architecture. |
| API | Application Programming Interface | A programmatic interface between services or tools. |
| C4 | Context, Containers, Components, and Code | A hierarchy of architecture diagrams that explains a system at increasing levels of detail. |
| CI | Continuous Integration | Automated build and test integration of source changes. |
| CI/CD | Continuous Integration and Continuous Delivery | Automated build/test integration and the controlled delivery path; it is not proof of deployment. |
| CLI | Command-Line Interface | A versioned operator or developer command surface. |
| DLQ | Dead-Letter Queue | A durable holding area for events that cannot be processed normally. |
| DNS | Domain Name System | The naming layer that resolves service hostnames to network addresses. |
| DORA | DevOps Research and Assessment | A widely used set of software-delivery performance metrics. |
| DR | Disaster Recovery | Recovery planning and exercises for significant service or regional failure. |
| EIP | Engineering Intelligence Platform | The repository/reference implementation that delivers the Company Brain product. |
| HMAC | Hash-based Message Authentication Code | A shared-secret integrity check used for webhook verification. |
| HITL | Human in the Loop | A required human review, approval, or execution step in a workflow. |
| HPA | Horizontal Pod Autoscaler | Kubernetes control that adjusts workload replica counts. |
| IaC | Infrastructure as Code | Version-controlled infrastructure definitions, such as Terraform and Helm. |
| JWT | JSON Web Token | A signed token that carries authenticated identity claims. |
| JWKS | JSON Web Key Set | The published public-key set used to verify JSON Web Tokens. |
| KPI | Key Performance Indicator | A defined measure of product, operational, or business outcome. |
| LLM | Large Language Model | A model used to reason or synthesize, never the authorization boundary. |
| MTTA | Mean Time to Acknowledge | The elapsed time between an alert and its acknowledged response. |
| MTTR | Mean Time to Restore | The elapsed time needed to restore a service after a failure. |
| NFR | Non-Functional Requirement | A required quality attribute such as security, reliability, latency, or cost. |
| NFRs | Non-Functional Requirements | Multiple required quality attributes for a system or workflow. |
| OIDC | OpenID Connect | The identity layer commonly used with OAuth 2.0 and workload identity. |
| OPA | Open Policy Agent | The deterministic policy engine used as an authorization boundary. |
| OTel | OpenTelemetry | The standard instrumentation framework for traces, metrics, and logs. |
| OTLP | OpenTelemetry Protocol | The protocol used to export OpenTelemetry telemetry. |
| PaaS | Platform as a Service | A managed cloud platform service rather than a self-managed workload. |
| PII | Personally Identifiable Information | Data that can identify or be linked to an individual. |
| PR | Pull Request | A proposed source change and review unit in GitHub or Azure DevOps. |
| RAG | Retrieval-Augmented Generation | Model synthesis grounded in retrieved, authorized evidence. |
| RBAC | Role-Based Access Control | Authorization based on roles assigned to a principal. |
| RCA | Root Cause Analysis | Evidence-backed analysis of why an incident or failure occurred. |
| ROI | Return on Investment | Measured or modeled value relative to investment. |
| RPO | Recovery Point Objective | The maximum acceptable amount of data loss measured in time. |
| RTO | Recovery Time Objective | The maximum acceptable time to restore a service. |
| SBOM | Software Bill of Materials | An inventory of software components included in a build artifact. |
| SDK | Software Development Kit | A library supplied by an external platform for programmatic integration. |
| SDLC | Software Development Life Cycle | The process of designing, changing, delivering, and operating software. |
| SLI | Service Level Indicator | A measured signal used to assess a service objective. |
| SLO | Service Level Objective | The target value or range for a service-level indicator. |
| SLM | Small Language Model | A smaller model proposed for bounded, lower-cost inference or safety tasks. |
| SRE | Site Reliability Engineering | Engineering discipline responsible for reliable, operable systems. |
| SQL | Structured Query Language | The language used to query relational databases. |
| VNet | Azure Virtual Network | Azure's isolated virtual network boundary. |
| WORM | Write Once, Read Many | Storage retention that prevents records from being altered or deleted. |
| eBPF | Extended Berkeley Packet Filter | Kernel technology for constrained, programmable observability and networking. |

## Autonomy levels

| Level | Expansion | Meaning |
|---|---|---|
| L0 | Autonomy Level 0 — observe | Collect and correlate evidence only. |
| L1 | Autonomy Level 1 — recommend | Produce evidence-backed recommendations; no mutation. |
| L2 | Autonomy Level 2 — human execute | Prepare an exact, reviewable action; a human executes it. |
| L3 | Autonomy Level 3 — approve and execute | An authenticated human approval authorizes an allow-listed deterministic runbook. |
| L4 | Autonomy Level 4 — bounded autonomous | A certified service/environment/runbook combination may execute within strict policy and blast-radius limits. |
| L5 | Autonomy Level 5 — unrestricted autonomy | Unsupported and out of scope by design. |
