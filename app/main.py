from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.observability import configure_tracing, tracer

configure_tracing()
trace = tracer()
app = FastAPI(title="Engineering Intelligence Platform", version="0.3.0")


class QueryRequest(BaseModel):
    question: str
    repo: str | None = None
    service: str | None = None


class Evidence(BaseModel):
    source: str
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
    model: str
    correlation_id: str


class Retriever(Protocol):
    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]: ...


@dataclass
class InMemoryRetriever:
    corpus: tuple[Evidence, ...] = (
        Evidence(
            source="architecture/azure-devops-self-healing-reference.md",
            text="Production mutation must be policy authorized and reversible.",
            score=0.94,
        ),
        Evidence(
            source="roadmap/technical-roadmap-24-months.md",
            text="Self-healing begins with low-blast-radius allow-listed runbooks.",
            score=0.91,
        ),
    )

    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]:
        return list(self.corpus)


def authorized_groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw or "engineering").split(",") if g.strip()]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/query", response_model=QueryResponse)
def query(
    req: QueryRequest,
    x_eip_groups: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    groups = authorized_groups(x_eip_groups)
    correlation_id = (x_correlation_id or str(uuid.uuid4())).strip()
    if not correlation_id or len(correlation_id) > 128:
        raise HTTPException(status_code=400, detail="invalid correlation id")

    with trace.start_as_current_span("eip.query") as span:
        span.set_attribute("eip.correlation_id", correlation_id)
        span.set_attribute("eip.repo", req.repo or "")
        span.set_attribute("eip.service", req.service or "")
        span.set_attribute("eip.group_count", len(groups))

        if os.getenv("EIP_BACKEND", "deterministic") == "azure":
            from app.rag.azure_backend import AzureRagBackend

            backend = AzureRagBackend()
            docs = backend.retrieve(
                req.question,
                req.repo,
                groups,
                correlation_id=correlation_id,
                service=req.service,
                user=x_eip_user,
            )
            evidence = [Evidence(source=d.source, text=d.text, score=d.score) for d in docs]
            if not evidence:
                return QueryResponse(
                    answer="I do not have enough authorized evidence to answer.",
                    evidence=[],
                    model="none",
                    correlation_id=correlation_id,
                )
            answer = backend.synthesize(
                req.question,
                docs,
                correlation_id=correlation_id,
                service=req.service,
                repo=req.repo,
                user=x_eip_user,
            )
            return QueryResponse(
                answer=answer,
                evidence=evidence,
                model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "azure"),
                correlation_id=correlation_id,
            )

        evidence = InMemoryRetriever().search(req.question, req.repo, groups)
        citations = "; ".join(e.source for e in evidence)
        answer = (
            "Guardrailed automation should use policy-authorized, reversible runbooks. "
            f"Sources: {citations}"
        )
        return QueryResponse(
            answer=answer,
            evidence=evidence,
            model="deterministic-demo",
            correlation_id=correlation_id,
        )
