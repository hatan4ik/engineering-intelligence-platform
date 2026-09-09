# FAANG/MANGA Kubernetes On-Premises Troubleshooting & Architecture Guide

This comprehensive reference guide is designed for Principal/Staff Infrastructure and Production Engineering candidates preparing for FAANG/MANGA technical interviews, focusing on **on-premises Kubernetes**, **Linux kernel internals**, **disaster recovery**, and **catastrophic incident triage**.

---

## 1. The FAANG 5-Step Incident Triage Framework

When confronted with a live production outage in a FAANG interview ("Your multi-tenant on-prem cluster is experiencing cascading 503s; where do you start?"), do **not** jump straight into ad-hoc kubectl commands. Use this structured 5-tier methodology:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   FAANG INCIDENT INVESTIGATION LOOP                    │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Triage & Impact Assessment                                          │
│    Identify blast radius, SLA violation rate, and traffic impact.      │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Blast Radius Containment (Stop the Bleeding)                        │
│    Isolate failure domain (BGP withdraw, cordon nodes, circuit break). │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Deep Telemetry & Hypothesis Generation                              │
│    Correlate kernel metrics, audit logs, eBPF traces, and state dumps. │
├────────────────────────────────────────────────────────────────────────┤
│ 4. Deterministic Surgical Remediation                                  │
│    Execute reversible, pre-verified runbook with canary verification.  │
├────────────────────────────────────────────────────────────────────────┤
│ 5. Post-Incident Hardening & Systemic Prevention                       │
│    Root cause analysis, architectural guardrails, and automated tests. │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Linux Kernel & Kubernetes Internals

### A. Memory Management: cgroup v1 vs cgroup v2
* **cgroup v1 Issues**: Separate hierarchies for CPU, memory, blkio. The memory controller struggled to account for buffered page cache I/O, leading to priority inversions and unexpected OOMs.
* **cgroup v2 (Unified Hierarchy)**:
  - `memory.min`: Hard memory guarantee. Never reclaimed by kernel unless all other memory is exhausted.
  - `memory.low`: Best-effort guarantee. Protected from reclaim before unprotected memory.
  - `memory.high`: The throttling threshold. When exceeded, the process threads are throttled and forced into direct reclaim rather than immediately killed.
  - `memory.max`: Hard limit. Crossing this triggers direct reclaim; if insufficient, the Linux kernel OOM killer terminates a process.
  - **Pressure Stall Information (PSI)**: Monitors CPU, memory, and I/O stall times (`/proc/pressure/memory`), providing early indicators of thrashing before an OOM occurs.
* **OOM Score Calculation**:
  $$\text{oom\_score} = \frac{\text{memory\_usage}}{\text{total\_memory}} \times 1000 + \text{oom\_score\_adj}$$
  - Pods with `Guaranteed` QoS have `oom_score_adj = -997` (killed last).
  - Pods with `BestEffort` QoS have `oom_score_adj = 1000` (killed first).
  - Pods with `Burstable` QoS have $2 \le \text{oom\_score\_adj} \le 999$ based on memory request percentage.

---

### B. Networking: The On-Prem Packet Traversal Path
Understanding the exact path of a packet from physical NIC to container is critical for on-prem networking interviews:

```
[Physical NIC]
      │ (Hardware Offloads: LRO, GRO, RSS)
      ▼
  [Kernel Ring Buffer / DMA]
      │
      ▼
  [eBPF XDP (eXpress Data Path)]  <-- Dropped / redirected at driver level
      │
      ▼
  [Traffic Control (tc) / eBPF]   <-- Calico / Cilium host endpoint filtering
      │
      ▼
  [Linux Netfilter / conntrack]   <-- NAT tracking table (overflow causes silent drops)
      │
      ▼
  [Bridge / Routing Engine / BGP] <-- Calico Felix / MetalLB BGP Anycast routing
      │
      ▼
  [veth pair (host side)]
      │
      ▼
  [veth pair (container netns)]
      │
      ▼
  [Container Socket Buffer]
```

* **MTU & Encapsulation Overhead**:
  - Standard Ethernet MTU = 1500 bytes.
  - VXLAN adds a 50-byte header (Outer Ethernet [14] + Outer IP [20] + Outer UDP [8] + VXLAN [8]). Pod interface MTU must be configured to $\le 1450$.
  - Geneve adds 58+ bytes.
  - **PMTUD Blackhole**: If an intermediate switch or firewall drops ICMP "Fragmentation Needed" (Type 3, Code 4) packets, TCP handshakes (small packets) succeed, but data transfers (MSS sized) hang indefinitely.

---

### C. etcd Architecture & Raft Consensus
* **The Raft Algorithm**:
  - Quorum formula: $Q = \lfloor N/2 \rfloor + 1$. For 3 members, quorum is 2; for 5 members, quorum is 3.
  - Even cluster sizes (e.g., 4 or 6) provide zero additional fault tolerance while increasing network traffic.
* **Storage Engine: bbolt**:
  - B+tree based copy-on-write database.
  - MVCC (Multi-Version Concurrency Control): Writes create new revision keys rather than overwriting in place.
  - **The Compaction & Defrag Cycle**:
    - `compaction`: Marks obsolete historical revisions as free space inside bbolt.
    - `defragmentation`: Required to reclaim the filesystem disk space. Running defragmentation on an active etcd cluster blocks read/write locks; it must be executed sequentially member by member.
* **Disk I/O Requirements**:
  - etcd requires sequential WAL (Write-Ahead Log) writes with `fsync`.
  - WAL `fsync` latency must remain strictly under 10ms. If fsync latency exceeds 100ms, the leader cannot replicate logs in time, causing heartbeats to time out and triggering constant leader elections.

---

## 3. Top 10 High-Stakes On-Premises Disaster Recovery Drills

### Drill 1: etcd Quorum Loss & Split-Brain Recovery
* **Scenario**: 2 out of 3 etcd nodes experienced catastrophic hardware failure. The remaining node is read-only because it cannot achieve a quorum ($1 < 2$).
* **Root Diagnosis**:
  ```bash
  ETCDCTL_API=3 etcdctl --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    endpoint status --write-out=table
  ```
* **Recovery Procedure**:
  1. Stop the failing etcd service on the remaining survivor node.
  2. Backup the current data directory:
     ```bash
     cp -r /var/lib/etcd /var/lib/etcd.bak
     ```
  3. Force a new single-member cluster from the existing state:
     ```bash
     etcd --force-new-cluster \
       --data-dir=/var/lib/etcd \
       --listen-peer-urls=https://10.0.0.1:2380 \
       --listen-client-urls=https://10.0.0.1:2379,https://127.0.0.1:2379
     ```
  4. Once healthy, re-add new members sequentially using `etcdctl member add`.

---

### Drill 2: Broken Admission Webhook Failing Closed (Control Plane Deadlock)
* **Scenario**: A third-party security webhook (`ValidatingWebhookConfiguration`) was deployed with `failurePolicy: Fail`. The webhook pod crashed. Now, no pods can be created, updated, or scheduled across the entire cluster, including the webhook pod itself!
* **Root Diagnosis**:
  ```bash
  kubectl get events -A --sort-by='.metadata.creationTimestamp' | grep -i webhook
  # Error: Internal error occurred: failed calling webhook "sec-gate.example.com": Post "...": dial tcp: connect: connection refused
  ```
* **Emergency Bypass**:
  ```bash
  # Step 1: Temporarily switch the failure policy to Ignore
  kubectl patch validatingwebhookconfiguration sec-gate \
    --type='json' -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'

  # Step 2: If the API server is completely unresponsive to webhook patches,
  # modify kube-apiserver manifest (/etc/kubernetes/manifests/kube-apiserver.yaml)
  # to disable admission plugins temporarily:
  # --disable-admission-plugins=ValidatingAdmissionWebhook,MutatingAdmissionWebhook
  ```

---

### Drill 3: CNI IPAM Pool Exhaustion & Leaked veth Interfaces
* **Scenario**: Pods are stuck indefinitely in `ContainerCreating`. `dmesg` reports `no IP addresses available in pool` or `device veth... already exists`.
* **Root Diagnosis**:
  ```bash
  # Inspect Calico / Cilium IPAM allocation
  calicoctl ipam show --show-blocks
  # Check for leaked veth interfaces in the root network namespace
  ip link show | grep veth | wc -l
  ```
* **Remediation**:
  1. Release leaked IPs belonging to dead pods:
     ```bash
     calicoctl ipam check
     calicoctl ipam release --ip=<leaked-ip>
     ```
  2. Expand the pod CIDR subnet mask in the CNI IPPool configuration (e.g., from `/24` to `/22`).
  3. Ensure container runtime (`containerd`) is configured with proper CNI teardown hooks on pod deletion.

---

### Drill 4: CoreDNS Latency Storms & `ndots:5` Query Amplification
* **Scenario**: Service latency spikes cluster-wide. CoreDNS pods show high CPU saturation and packet drops.
* **Root Cause**:
  In `/etc/resolv.conf`, Kubernetes injects `options ndots:5` and 3 search domains:
  1. `<namespace>.svc.cluster.local`
  2. `svc.cluster.local`
  3. `cluster.local`
  When a pod queries an external domain (e.g., `api.stripe.com`, which has only 2 dots $< 5$), the resolver fires 4 sequential queries:
  1. `api.stripe.com.<namespace>.svc.cluster.local` $\to$ NXDOMAIN
  2. `api.stripe.com.svc.cluster.local` $\to$ NXDOMAIN
  3. `api.stripe.com.cluster.local` $\to$ NXDOMAIN
  4. `api.stripe.com.` $\to$ SUCCESS
* **Remediation**:
  1. Deploy **NodeLocal DNSCache** as a DaemonSet to serve local cache over link-local IP (`169.254.20.10`).
  2. Append trailing dots to external domain lookups in application code (`api.stripe.com.`).
  3. Enable `autopath` plugin in CoreDNS Corefile to return CNAME responses in a single round-trip.

---

### Drill 5: Kubelet Eviction from Inode Exhaustion vs Disk Capacity
* **Scenario**: Worker nodes enter `NotReady` or trigger massive pod eviction storms. However, `df -h` shows only 40% disk capacity used!
* **Root Diagnosis**:
  ```bash
  df -i /var/lib/kubelet
  # Filesystem Inodes IUsed IFree IUse%
  # /dev/sda1 10485760 10485760 0 100%
  ```
* **Root Cause**:
  Microservices writing hundreds of thousands of tiny un-rotated log files or temporary cache files exhaust available filesystem inodes before filling disk capacity. Kubelet's `nodefs.inodesFree` eviction threshold is breached.
* **Remediation**:
  1. Identify offending containers:
     ```bash
     find /var/log/pods -type f | cut -d/ -f5 | sort | uniq -c | sort -nr | head -10
     ```
  2. Enforce strict `emptyDir.sizeLimit` and container log rotation in `kubelet.yaml`:
     ```yaml
     containerLogMaxSize: "50Mi"
     containerLogMaxFiles: 5
     ```

---

### Drill 6: PodDisruptionBudget (PDB) Node Drain Deadlocks
* **Scenario**: An operator runs `kubectl drain <node>`. The command hangs indefinitely, and workloads cannot be evacuated.
* **Root Cause**:
  A Deployment of 2 replicas has a `PodDisruptionBudget` configured with `minAvailable: 2` (or `maxUnavailable: 0`). Evicting even a single pod violates the budget, so the eviction API returns `429 Too Many Requests` in an infinite loop.
* **Remediation**:
  ```bash
  # Check blocking PDBs
  kubectl get pdb -A
  # Patch PDB temporarily during maintenance
  kubectl patch pdb <pdb-name> -p '{"spec":{"minAvailable":1}}'
  # Or force drain ignoring disruption budgets (if authorized)
  kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --force
  ```

---

### Drill 7: Netfilter `conntrack` Table Exhaustion
* **Scenario**: Sporadic TCP timeouts (`connection timed out`, 504 Gateway Timeout) with 0 CPU/memory pressure.
* **Root Diagnosis**:
  ```bash
  # Check current table size vs limit
  cat /proc/sys/net/netfilter/nf_conntrack_count
  cat /proc/sys/net/netfilter/nf_conntrack_max
  # Check kernel drop logs
  dmesg -T | grep -i "nf_conntrack: table full"
  ```
* **Remediation**:
  1. Increase conntrack table size immediately:
     ```bash
     sysctl -w net.netfilter.nf_conntrack_max=1048576
     ```
  2. Tune TCP FIN / TIME_WAIT timeout to reclaim closed connection sockets faster:
     ```bash
     sysctl -w net.netfilter.nf_conntrack_tcp_timeout_time_wait=30
     sysctl -w net.netfilter.nf_conntrack_tcp_timeout_close_wait=30
     ```

---

### Drill 8: Liveness Probe Cascading Death Spiral
* **Scenario**: Service A suffers transient latency under peak load. Suddenly, all pods across the cluster begin restarting in lockstep, turning a slight slowdown into a 100% outage.
* **Root Cause**:
  The liveness probe endpoint (`/healthz`) performs deep downstream database or cache checks. When the database slowed down, the liveness probes timed out simultaneously. Kubelet restarted all pods. On restart, cold-cache initialization flooded the already overloaded database, causing new liveness probe failures in an infinite loop.
* **Architecture Fix**:
  - **Rule of Separation**:
    - **Liveness Probe**: Only check if the container process is alive and not deadlocked (shallow check). Never query remote downstream databases in a liveness probe!
    - **Readiness Probe**: Check if the container is ready to receive traffic. If database is slow, fail readiness so the pod is removed from EndpointSlice, but do **not** kill the pod.
    - **Startup Probe**: Use `startupProbe` with high failure thresholds for slow-starting applications to prevent premature liveness kills.

---

## 4. Key FAANG Architecture Interview Questions & Answers

### Q1: "How do you design zero-downtime multi-tenant ingress for 100,000 requests/second on-premises?"
* **Model Answer**:
  1. **BGP Anycast with ECMP**:
     Deploy ingress controllers (Envoy / NGINX) across dedicated edge bare-metal nodes. Use BIRD/FRR or MetalLB in BGP mode to advertise the same virtual IP (VIP) to top-of-rack (ToR) switches. The switches distribute connections across ingress nodes using Equal-Cost Multi-Path (ECMP).
  2. **Consistent Hashing**:
     Use Maglev or Katran (eBPF-based L4 load balancer) in front of ingress nodes to ensure flow consistency even when an ingress node is added or removed during rolling upgrades.
  3. **Kernel Network Tuning**:
     Tune `so_max_conn`, `tcp_max_syn_backlog`, and increase `somaxconn` to $\ge 32768$. Enable `tcp_tw_reuse`.
  4. **Multi-Tenancy Isolation**:
     Separate tenant traffic using NetworkPolicies (Calico/Cilium), allocate dedicated Ingress Controller instances per tier-0 tenant, and enforce egress traffic shaping via bandwidth plugins.

---

### Q2: "How do you recover a cluster when the kube-apiserver TLS certificate has already expired?"
* **Model Answer**:
  1. If `kubeadm` was used:
     ```bash
     # Check expiration
     kubeadm certs check-expiration
     # Renew all control plane certificates using the existing cluster CA
     kubeadm certs renew all
     ```
  2. If running standalone or CA is expired:
     - Generate a new CA private key and self-signed root cert via `openssl`.
     - Re-sign `apiserver.crt`, `apiserver-kubelet-client.crt`, and `front-proxy-client.crt`.
     - Update `/etc/kubernetes/admin.conf` with the renewed client certificate and embed it into the operator's kubeconfig.
     - Restart `kube-apiserver`, `kube-controller-manager`, and `kube-scheduler` static pods by touching the manifests in `/etc/kubernetes/manifests/`.

---

## 5. Cheat Sheet: Must-Know Diagnostic Commands

| Target | Command | Purpose |
| :--- | :--- | :--- |
| **Container Engine** | `crictl ps -a` / `crictl logs <id>` | Inspect container state when kubelet is unresponsive |
| **Network Tracing** | `tcpdump -i any -nn port 53` | Trace DNS request/response round-trips |
| **conntrack Drops** | `conntrack -S` | Show real-time conntrack drops and early drop counters |
| **etcd Latency** | `etcdctl check perf` | Benchmark etcd disk fsync and network latency |
| **Kernel Profiling**| `perf top` | Trace CPU kernel-space hotspots and lock contention |
| **Socket Queues** | `ss -tulpn` | Identify listen socket backlog overflows |
| **Inode Usage** | `df -i` | Detect inode exhaustion before disk capacity fills |
| **PDB Budget** | `kubectl get pdb -A` | Identify budgets blocking graceful drains |

