import re

filepath = 'architecture/design.md'
with open(filepath, 'r') as f:
    content = f.read()

# Replace the "gateway also implements" with a target state block
old_block = """To meet FAANG-level latency and unit economic requirements, the gateway also implements:
- **Materialized ACL Cache**: Resolving complex, nested Entra ID/Active Directory groups at query time introduces unacceptable latency. The gateway leverages a **Zanzibar-inspired materialized permissions cache** to resolve ACLs in single-digit milliseconds before compiling them into the search query.
- **SLM Routing & Semantic Caching**: The gateway implements **Semantic Caching** to serve repeat questions instantly, and dynamically routes >80% of routine tasks (like basic PR linting) to fast, local **Small Language Models (SLMs)** (e.g., Llama 3 8B), reserving heavy frontier models purely for complex Root Cause Analysis."""

new_block = """> [!NOTE]
> **[PROPOSED TARGET STATE]** To meet FAANG-level latency and unit economic requirements in the future, the target architecture proposes adding:
> - **Materialized ACL Cache**: A Zanzibar-inspired materialized permissions cache to resolve ACLs in single-digit milliseconds before compiling them into the search query.
> - **SLM Routing & Semantic Caching**: Ephemeral **Semantic Caching** to serve repeat questions instantly, and dynamic routing to fast, local **Small Language Models (SLMs)** (e.g., Llama 3 8B) for routine tasks."""

content = content.replace(old_block, new_block)

# Fix the Qdrant/Milvus mentions
old_qdrant = """applied to both arms. In strictly isolated or air-gapped environments, on-prem vector databases (e.g., Qdrant, Milvus) can be swapped in for the retrieval layer.

Runtime modes: `EIP_BACKEND=deterministic` (local/CI, no cloud dependency),
`EIP_BACKEND=azure` (Azure AI Search + Azure OpenAI via `DefaultAzureCredential`), and
`EIP_BACKEND=onprem` (Qdrant/Milvus + Local LLM like vLLM/Ollama for air-gapped FAANG deployments)."""

new_qdrant = """applied to both arms. 

> [!NOTE]
> **[PROPOSED TARGET STATE]** In strictly isolated or air-gapped environments, the target architecture proposes allowing on-prem vector databases (e.g., Qdrant, Milvus) to be swapped in for the retrieval layer.

Runtime modes: `EIP_BACKEND=deterministic` (local/CI, no cloud dependency), and 
`EIP_BACKEND=azure` (Azure AI Search + Azure OpenAI via `DefaultAzureCredential`). (Note: `EIP_BACKEND=onprem` is a proposed future state, not currently implemented)."""

content = content.replace(old_qdrant, new_qdrant)

# Also fix the Classification of design.md itself at the top of the file
content = content.replace('| **Classification** | Current design — target architecture with referenced implementation contracts |', 
                          '| **Classification** | Current design — mixing implemented architecture and explicitly-labeled proposed target architecture |')

with open(filepath, 'w') as f:
    f.write(content)
