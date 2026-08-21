from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Engineering Intelligence Platform", version="0.1.0")


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
        Evidence(source="architecture/self-healing.md", text="Production mutation must be policy authorized and reversible.", score=0.94),
        Evidence(source="roadmap/technical-roadmap-24-months.md", text="Self-healing begins with low-blast-radius allow-listed runbooks.", score=0.91),
    )

    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]:
        # Demo retriever. Replace with Azure AI Search using the same authorization boundary.
        return list(self.corpus)


retriever: Retriever = InMemoryRetriever()


def authorized_groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw or "engineering").split(",") if g.strip()]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/query", response_model=QueryResponse)
def query(req: QueryRequest, x_eip_groups: str | None = Header(default=None)) -> QueryResponse:
    groups = authorized_groups(x_eip_groups)
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    evidence = retriever.search(req.question, req.repo, groups)
    if not evidence:
        return QueryResponse(answer="I do not have enough authorized evidence to answer.", evidence=[], model="none")

    # Reference implementation deliberately keeps synthesis deterministic/offline.
    # Production adapter should call Azure OpenAI only after authorized retrieval.
    citations = "; ".join(e.source for e in evidence)
    answer = f"Guardrailed automation should use policy-authorized, reversible runbooks. Sources: {citations}"
    return QueryResponse(answer=answer, evidence=evidence, model=os.getenv("EIP_MODEL", "deterministic-demo"))
