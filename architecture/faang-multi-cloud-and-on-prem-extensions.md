# FAANG Kubernetes, Multi-Cloud & On-Premises Extensions

| | |
|---|---|
| **Classification** | Target proposal — multi-cloud and on-premises extension architecture |
| **Primary owner** | Platform Engineering |
| **Current implementation state** | [`CAPABILITY-RECONCILIATION.md`](CAPABILITY-RECONCILIATION.md) |
| **Delivery decision** | Deferred until the Azure path has earned its product and evidence gates |

## Context

While the initial implementation of the Company Brain targets Azure-native services (Azure AI
Search, Azure OpenAI, AKS), multi-cloud portability (AWS EKS, GCP GKE) and hybrid/on-premises
deployments impose distinct constraints. This is a deliberately deferred extension: it describes
what would be needed after the Azure product path has earned its evidence gates, not an active
delivery commitment.

This extension details the required architectural shifts to support multi-cloud deployments, strict on-premises environments, complex low-level Kubernetes troubleshooting, and proactive cluster-level self-healing.

## 1. Multi-Cloud & Air-Gapped AI Operations

In multi-cloud or disconnected environments, the AI Gateway and Retrieval plane must swap out Azure dependencies for equivalent cloud-native or on-premises equivalents via the platform's abstraction interfaces.

- **Multi-Cloud LLM Routing**: A future AI Gateway would need dynamic routing to AWS Bedrock,
  GCP Vertex AI, or equivalent providers based on cost, latency, and data-sovereignty policy.
- **Local LLM Hosting**: In fully air-gapped scenarios, inference could be routed to a local
  cluster through vLLM or Ollama. This would require GPU-enabled nodes, scale-to-zero policy, and
  a queue/cold-start design that preserves bounded PR workflow latency.
- **Cloud-Agnostic Vector Database**: The retrieval projection would need a provider contract
  that can map Azure AI Search semantics to an approved alternative such as OpenSearch, pgvector,
  Qdrant, or Milvus without weakening ACL/provenance requirements.
- **Model Fallbacks**: A future gateway would need bounded degradation, prioritization, and
  fallback semantics before it can be considered portable.

## 2. Advanced Kubernetes Observability & Troubleshooting

Azure Monitor provides baseline metrics, but FAANG-level infrastructure debugging requires high-fidelity, low-level context.

### Required Ingests:
- **eBPF Tracing**: Incorporate agents like Cilium Hubble or Pixie to trace cross-node network packet drops, DNS resolution latencies, and kernel-level socket exhaustion.
- **Prometheus & Thanos/Cortex**: Direct querying of Prometheus Alertmanager events and high-cardinality metric traces during incident timeline reconstruction.
- **Kubelet & Containerd Logs**: Unstructured node-level logs are routed through FluentBit/Vector and parsed to identify storage mounting failures, container runtime OOMs, and sandbox creation deadlocks.

### Incident Correlation Workflow:
When an anomaly fires (e.g., widespread CoreDNS timeouts):
1. The **Incident Investigator** queries eBPF network graphs to verify if packets are leaving the pods.
2. Retrieves Kubelet logs to check for node resource pressure.
3. Retrieves recent `kubectl apply` changes from the Authoritative State store.
4. Generates an evidence-backed hypothesis that links the symptoms to an underlying configuration error (e.g., a bad `NetworkPolicy` applied 5 minutes ago).

## 3. Cluster-Level Self-Healing and Proactive Defense

### Admission Controllers
Reactive CI/CD checks (like PR Guardian) are insufficient for drift introduced outside the pipeline (e.g., manual `kubectl` usage). 
- The target platform would export deterministic policies into Kyverno or OPA Gatekeeper.
- The K8s API server intercepts and blocks unauthorized or risky changes before they materialize in the cluster.

### Node-Level Remediation
Only after scoped L3 evidence exists could L4 autonomy be considered beyond workload scaling (HPA)
for underlying infrastructure recovery:
- **Cordon and Drain**: Safe removal of a degraded node from the scheduling pool.
- **Volume Detach/Reattach**: Coordinated recovery for workloads stuck waiting for Azure Disk / PersistentVolume mounts.
- **Node Termination**: Issuing reboot or terminate commands to the underlying virtualization API or bare-metal hypervisor, allowing the cluster autoscaler to replace the tainted node.

## Conclusion
By preserving provider-neutral contracts for models and retrieval, the Company Brain could later
support isolated on-premises Kubernetes environments. Such a deployment still requires its own
security, reliability, cost, and evidence review; this proposal does not authorize it.
