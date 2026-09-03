# Secure Azure Foundation Slice

| | |
|---|---|
| **Classification** | Historical implementation milestone — reference IaC, not current deployment status |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | reference IaC; never planned or applied against a subscription |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../../docs/CURRENT-POSITION.md) |
| **Current capability detail** | [`CAPABILITY-RECONCILIATION.md`](../CAPABILITY-RECONCILIATION.md) |


This slice closes the largest implementation gap identified in the historical [alignment review](../ALIGNMENT-REVIEW.md) (its correction wave "P1", unrelated to finding severities elsewhere): the original architecture required a private Azure trust boundary, while the initial Terraform only created a VNet, AKS, Search and Log Analytics with default public service access.

## Implemented in this slice

- Dedicated Private Endpoint subnet.
- Azure AI Search with public network access disabled and API-key authentication disabled.
- Azure OpenAI cognitive account with a custom subdomain, public access disabled and restricted outbound access.
- Azure Key Vault using RBAC authorization with public access disabled.
- Private DNS zones and VNet links for Search, OpenAI and Key Vault.
- Private Endpoints for Search (`searchService`), OpenAI (`account`) and Key Vault (`vault`).
- Terraform declarations for a private, zone-redundant PostgreSQL Flexible Server with separate
  Temporal persistence and visibility databases. It is a configuration artifact only until an
  approved private runner applies it and the required migration/restore evidence is retained.
- AKS OIDC issuer and Workload Identity.
- Private AKS API, Entra/Azure RBAC, Azure Policy add-on, no local admin account,
  and no public private-cluster FQDN. The deployment runner must therefore have an
  approved private network path to the cluster.
- User-assigned workload identity federated to the `eip/eip-api` Kubernetes service account by default.
- Explicit least-privilege runtime roles: Search Index Data Reader, Cognitive Services OpenAI User and Key Vault Secrets User.
- Helm ServiceAccount and pod labels required by Azure Workload Identity.
- Terraform outputs for application endpoint/client configuration.

## Trust boundary

```text
AKS EIP workload
  |
  | Entra workload identity
  v
Private DNS inside VNet
  |
  +--> Azure AI Search Private Endpoint
  +--> Azure OpenAI Private Endpoint
  +--> Key Vault Private Endpoint

Public PaaS data-plane ingress: disabled
API keys for Search runtime: disabled
```

Clients must continue using the normal Search/OpenAI/Key Vault service hostnames. Private DNS resolves those names to Private Link addresses for clients inside the VNet.

## Deliberately not claimed complete

The following target-state controls remain follow-on work:

1. Private ingress/API gateway in front of the EIP API.
2. Cosmos authoritative state, immutable audit export, and a Temporal worker deployment wired to
   the declared private PostgreSQL foundation.
3. Controlled outbound egress/NAT/firewall and explicit network policy.
4. Azure OpenAI model deployments and embedding deployment configuration; deployments are capacity/region dependent and should be explicit variables/modules rather than assumed.
5. Separate deployment/index-management identity with Search Index Data Contributor/Search Service Contributor as needed. The runtime is read-only by design.
6. Diagnostic settings for all PaaS resources and end-to-end OTel correlation.
7. An approved private deployment-runner operating model for Terraform, Helm,
   break-glass, and cluster administration.

## Validation

```bash
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
helm lint helm/eip --values helm/eip/values.ci.yaml
```

After deployment, validate DNS and public-access denial from both inside and outside the VNet before treating the environment as compliant with the target trust boundary.
