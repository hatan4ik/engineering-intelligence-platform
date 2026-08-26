# ADR 002: Prompt Injection Guardrails and Semantic Cache Lifecycle

## Status
**Proposed**

## Context
During the Principal Architecture Review, two target-state requirements were identified for the RAG and Retrieval planes:
1. **The Confused Deputy (Prompt Injection)**: In the RAG Q&A path (where the LLM produces user-facing summaries or text), adversarial instructions injected into a retrieved document could trick the LLM. 
2. **Data Governance in Caching**: A proposed Semantic Caching layer (currently only a target architectural concept) must satisfy strict data governance and GDPR requirements ("Right to be Forgotten") before it can be implemented.

## Decision

### 1. Mandatory Input Guardrail for RAG Path
We will inject a **Guardrail Classifier** (e.g., Lakera Guard or Llama-Guard) *before* the primary LLM is invoked, strictly scoped to the **RAG Q&A path** (`app/rag/azure_backend.py`).
- **Mechanism**: Every retrieved chunk and user prompt is scanned for adversarial patterns.
- **Fail Closed**: If prompt injection is detected, the gateway immediately returns an explicit refusal.
- **Exclusion**: PR Guardian (roadmap Stages 0–3) uses a deterministic verdict (`assess_change`) with no LLM in the critical path, so this guardrail is not required there.

### 2. Ephemeral Semantic Caching (Max 24h TTL)
When Semantic Caching is implemented, it will be strictly ephemeral and tenant-isolated.
- **Mechanism**: The cache is purely an optimization layer. It must enforce a hard Time-To-Live (TTL) of **24 hours**. 
- **Compliance**: This ensures that if a user requests data deletion, the source is deleted from the primary index, and any cached semantic representations of that data naturally age out within one business day.

## Consequences
- **Positive**: Hardens the RAG path against social engineering. Sets strict pre-requisite compliance requirements before a Semantic Cache can be built.
- **Negative**: The Guardrail classifier adds latency to RAG queries.
