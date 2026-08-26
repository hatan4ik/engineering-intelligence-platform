# FAANG Kubernetes & On-Premises Extensions

| | |
|---|---|
| **Status** | Proposed Target Architecture |
| **Primary owner** | Platform Engineering |

## Context

While the initial implementation of the Engineering Intelligence Platform targets Azure-native services (Azure AI Search, Azure OpenAI, AKS), FAANG-tier scale and hybrid/on-premises deployments impose unique constraints. Many highly regulated environments, air-gapped data centers, or edge clusters cannot stream source code or operational telemetry to managed cloud AI providers.

This extension details the required architectural shifts to support strict on-premises environments, complex low-level Kubernetes troubleshooting, and proactive cluster-level self-healing.

## 1. Air-Gapped AI Operations

In disconnected environments, the AI Gateway and Retrieval plane must swap out cloud dependencies for on-premises equivalents.

- **Local LLM Hosting**: The `AI Gateway` routes inference to a local cluster running models like Llama 3 or Mixtral via **vLLM** or **Ollama**. This requires dedicated GPU-enabled nodes (e.g., A100/H100) managed within the on-premise cluster.
- **On-Premise Vector Database**: `Azure AI Search` is replaced by an open-source vector datastore such as **Qdrant**, **Milvus**, or **pgvector**.
- **Model Fallbacks**: The gateway natively handles degraded LLM latency or localized GPU saturation, queuing non-critical requests (e.g., Knowledge Decay Agent) while prioritizing high-urgency remediation tasks.

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
- The platform exports its deterministic policies into **Kyverno** or **OPA Gatekeeper**. 
- The K8s API server intercepts and blocks unauthorized or risky changes before they materialize in the cluster.

### Node-Level Remediation
L4 Autonomy expands beyond workload scaling (HPA) to underlying infrastructure recovery:
- **Cordon and Drain**: Safe removal of a degraded node from the scheduling pool.
- **Volume Detach/Reattach**: Coordinated recovery for workloads stuck waiting for Azure Disk / PersistentVolume mounts.
- **Node Termination**: Issuing reboot or terminate commands to the underlying virtualization API or bare-metal hypervisor, allowing the cluster autoscaler to replace the tainted node.

## Conclusion
By abstracting the AI model and retrieval engines behind clean interfaces, the Engineering Intelligence Platform can run natively inside isolated, on-premises Kubernetes environments, combining deep infrastructure observability with rigorous, evidence-gated self-healing.

