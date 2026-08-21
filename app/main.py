from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.observability import configure_tracing, tracer

configure_tracing()
trace = tracer()
app = FastAPI(title="Engineering Intelligence Platform", version="0.2.0")


class QueryRequest(BaseModel):
    question: str
    repo: str | None = None


class Evidence(BaseModel):
    source: str
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
    model: str


class Retriever(Protocol):
    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]: ...


@dataclass
class InMemoryRetriever:
    corpus: tuple[Evidence, ...] = (
        Evidence(source="architecture/azure-devops-self-healing-reference.md", text="Production mutation must be policy authorized and reversible.", score=0.94),
        Evidence(source="roadmap/technical-roadmap-24-months.md", text="Self-healing begins with low-blast-radius allow-listed runbooks.", score=0.91),
    )

    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]:
        return list(self.corpus)


def authorized_groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw or "engineering").split(",") if g.strip()]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/query", response_model=QueryResponse)
def query(req: QueryRequest, x_eip_groups: str | None = Header(default=None)) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    groups = authorized_groups(x_eip_groups)

    with trace.start_as_current_span("eip.query") as span:
        span.set_attribute("eip.repo", req.repo or "")
        span.set_attribute("eip.group_count", len(groups))

        if os.getenv("EIP_BACKEND", "deterministic") == "azure":
            from app.rag.azure_backend import AzureRagBackend

            backend = AzureRagBackend()
            docs = backend.retrieve(req.question, req.repo, groups)
            evidence = [Evidence(source=d.source, text=d.text, score=d.score) for d in docs]
            if not evidence:
                return QueryResponse(answer="I do not have enough authorized evidence to answer.", evidence=[], model="none")
            answer = backend.synthesize(req.question, docs)
            return QueryResponse(answer=answer, evidence=evidence, model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "azure"))

        evidence = InMemoryRetriever().search(req.question, req.repo, groups)
        citations = "; ".join(e.source for e in evidence)
        answer = f"Guardrailed automation should use policy-authorized, reversible runbooks. Sources: {citations}"
        return QueryResponse(answer=answer, evidence=evidence, model="deterministic-demo")
