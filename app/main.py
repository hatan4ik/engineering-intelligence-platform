from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from app.observability import configure_tracing, tracer
from sdlc.github_events import parse_pull_request_event, verify_webhook_signature

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


@app.post("/v1/events/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, object]:
    body = await request.body()
    secret = os.getenv("EIP_GITHUB_WEBHOOK_SECRET", "")
    if not verify_webhook_signature(secret=secret, body=body, signature_header=x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid or missing webhook signature")
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event or "unknown"}
    event = parse_pull_request_event(json.loads(body), delivery_id=x_github_delivery)
    if event is None:
        return {"status": "ignored", "reason": "action does not trigger review"}
    guardian = getattr(app.state, "pr_guardian", None)
    if guardian is None:
        raise HTTPException(status_code=503, detail="PR Guardian is not configured on this deployment")
    with trace.start_as_current_span("eip.pr_guardian") as span:
        span.set_attribute("eip.repo", event.repository)
        span.set_attribute("eip.pr", event.pr_number)
        result = guardian.handle(event)
        span.set_attribute("eip.correlation_id", result.correlation_id)
        span.set_attribute("eip.risk_score", result.assessment.score)
    return {
        "status": "reviewed",
        "workflow_id": result.workflow_id,
        "correlation_id": result.correlation_id,
        "score": result.assessment.score,
        "band": result.assessment.band,
        "conclusion": result.check.conclusion,
    }


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
