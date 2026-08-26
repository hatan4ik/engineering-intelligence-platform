from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from app.auth_mode import header_identity_permitted
from app.gateway import ApiKeyPrincipalStore, GatewayAuthError, GatewayPolicyError, authorize_request
from app.observability import configure_tracing, tracer
from app.operations_api import router as operations_router
from app.portal_api import router as portal_router
from app.runtime_wiring import capability_report, configure_capabilities, release_capabilities
from feedback.outcome_capture import normalize_github_pr_outcome
from integrations.github.pr_guardian import normalize_pull_request_event
from integrations.github.webhook import REVIEW_ACTIONS, verify_webhook_signature

configure_tracing()
trace = tracer()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configured = configure_capabilities(application)
    try:
        yield
    finally:
        release_capabilities(application, configured)


app = FastAPI(title="Engineering Intelligence Platform", version="0.6.0", lifespan=lifespan)
app.include_router(portal_router)
app.include_router(operations_router)


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
class DemoDocument:
    evidence: Evidence
    groups: tuple[str, ...]
    repository: str
    keywords: tuple[str, ...]


@dataclass
class InMemoryRetriever:
    """Deterministic local retriever used by the demo, API tests, and CI evaluation.

    This is intentionally small, but it still preserves the two properties that
    matter to the gateway contract: evidence must match the request and callers
    must be authorized before the evidence is returned.
    """

    corpus: tuple[DemoDocument, ...] = (
        DemoDocument(
            evidence=Evidence(
                source="architecture/azure-devops-self-healing-reference.md",
                text="Production remediation must be policy-authorized and reversible.",
                score=0.94,
            ),
            groups=("engineering",),
            repository="engineering-intelligence-platform",
            keywords=("production", "remediation", "policy", "reversible", "rollback"),
        ),
        DemoDocument(
            evidence=Evidence(
                source="roadmap/technical-roadmap-24-months.md",
                text="Self-healing begins with low-blast-radius allow-listed runbooks.",
                score=0.91,
            ),
            groups=("engineering",),
            repository="engineering-intelligence-platform",
            keywords=("self", "healing", "begin", "runbook", "autonomy"),
        ),
        DemoDocument(
            evidence=Evidence(
                source="finops/cfo-roi-model.md",
                text="FinOps controls include model routing, token budgets, caching, and anomaly alerts.",
                score=0.92,
            ),
            groups=("finance",),
            repository="finance-planning",
            keywords=("finops", "finance", "cost", "budget", "roi", "routing"),
        ),
    )

    def search(self, question: str, repo: str | None, groups: list[str]) -> list[Evidence]:
        authorized_groups = {group.strip() for group in groups if group.strip()}
        terms = {term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) >= 3}
        matches: list[Evidence] = []
        for document in self.corpus:
            if not authorized_groups.intersection(document.groups):
                continue
            if repo is not None and repo != document.repository:
                continue
            matched_keywords = len(terms.intersection(document.keywords))
            if matched_keywords == 0:
                continue
            matches.append(document.evidence.model_copy(update={"score": document.evidence.score + matched_keywords / 100}))
        return sorted(matches, key=lambda item: (-item.score, item.source))


def authorized_groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw or "engineering").split(",") if g.strip()]


def _gateway_identity(
    *,
    question: str,
    api_key: str | None,
    authorization: str | None,
    requested_model_tier: str | None,
    fallback_groups: str | None,
    fallback_user: str | None,
) -> tuple[str, list[str], str, str]:
    header_ok, _ = header_identity_permitted()
    if header_ok:
        return question, authorized_groups(fallback_groups), fallback_user or "local-demo", "standard"

    auth_mode = os.getenv("EIP_AUTH_MODE", "entra").lower()
    try:
        if auth_mode == "entra":
            from app.entra_identity import EntraPrincipalStore, EntraSettings
            store = EntraPrincipalStore(EntraSettings.from_environment())
            credential = authorization
        elif auth_mode == "api-key":
            store = ApiKeyPrincipalStore.from_environment()
            credential = api_key
        else:
            raise GatewayAuthError("unsupported production auth mode")

        decision = authorize_request(
            question=question,
            api_key=credential,
            requested_model_tier=requested_model_tier,
            estimated_cost_usd=float(os.getenv("EIP_ESTIMATED_REQUEST_USD", "0.05")),
            store=store,  # type: ignore[arg-type]
        )
    except (GatewayAuthError, GatewayPolicyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401 if isinstance(exc, GatewayAuthError) else 403, detail=str(exc)) from exc
    return (
        decision.sanitized_question,
        list(decision.principal.groups),
        decision.principal.subject,
        decision.model_tier,
    )


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "capabilities": capability_report(app)}


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
    try:
        payload = json.loads(body)
        event = normalize_pull_request_event(payload)
        terminal = normalize_github_pr_outcome(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if terminal is not None:
        recorder = getattr(app.state, "feedback_recorder", None)
        if recorder is not None:
            recorder.record_pr_closed(
                repository=str(terminal["repository"]),
                pr_number=int(terminal["pr_number"]),
                service=None,
                merged=bool(terminal["merged"]),
            )
        return {"status": "outcome-recorded", "merged": bool(terminal["merged"])}

    if event.action not in REVIEW_ACTIONS:
        return {"status": "ignored", "reason": "action does not trigger review"}
    guardian = getattr(app.state, "pr_guardian", None)
    if guardian is None:
        raise HTTPException(status_code=503, detail="PR Guardian is not configured on this deployment")
    with trace.start_as_current_span("eip.pr_guardian") as span:
        span.set_attribute("eip.repo", event.repository)
        span.set_attribute("eip.pr", event.number)
        span.set_attribute("eip.delivery_id", x_github_delivery or "")
        result = guardian.evaluate(event)
        span.set_attribute("eip.risk_score", result.assessment.score)
    return {
        "status": "reviewed",
        "workflow_id": result.workflow_id,
        "score": result.assessment.score,
        "band": result.assessment.band,
        "conclusion": result.conclusion,
        "changed_services": list(result.changed_services),
    }


@app.post("/v1/query", response_model=QueryResponse)
def query(
    req: QueryRequest,
    authorization: str | None = Header(default=None),
    x_eip_groups: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
    x_eip_api_key: str | None = Header(default=None),
    x_eip_model_tier: str | None = Header(default=None),
) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    question, groups, user, model_tier = _gateway_identity(
        question=req.question,
        api_key=x_eip_api_key,
        authorization=authorization,
        requested_model_tier=x_eip_model_tier,
        fallback_groups=x_eip_groups,
        fallback_user=x_eip_user,
    )
    correlation_id = (x_correlation_id or str(uuid.uuid4())).strip()
    if not correlation_id or len(correlation_id) > 128:
        raise HTTPException(status_code=400, detail="invalid correlation id")

    with trace.start_as_current_span("eip.query") as span:
        span.set_attribute("eip.correlation_id", correlation_id)
        span.set_attribute("eip.repo", req.repo or "")
        span.set_attribute("eip.service", req.service or "")
        span.set_attribute("eip.group_count", len(groups))
        span.set_attribute("eip.model_tier", model_tier)
        span.set_attribute("eip.user", user)
        span.set_attribute("eip.redacted", question != req.question)

        if os.getenv("EIP_BACKEND", "deterministic") == "azure":
            from app.rag.azure_backend import AzureRagBackend

            deployment = (
                os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ADVANCED")
                if model_tier == "advanced"
                else os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_STANDARD")
            ) or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            backend = AzureRagBackend(deployment=deployment)
            docs = backend.retrieve(
                question,
                req.repo,
                groups,
                correlation_id=correlation_id,
                service=req.service,
                user=user,
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
                question,
                docs,
                correlation_id=correlation_id,
                service=req.service,
                repo=req.repo,
                user=user,
            )
            return QueryResponse(
                answer=answer,
                evidence=evidence,
                model=deployment or "azure",
                correlation_id=correlation_id,
            )

        evidence = InMemoryRetriever().search(question, req.repo, groups)
        if not evidence:
            return QueryResponse(
                answer="I do not have enough authorized evidence to answer.",
                evidence=[],
                model="none",
                correlation_id=correlation_id,
            )
        citations = "; ".join(e.source for e in evidence)
        answer = f"{' '.join(e.text for e in evidence)} Sources: {citations}"
        return QueryResponse(
            answer=answer,
            evidence=evidence,
            model="deterministic-demo",
            correlation_id=correlation_id,
        )
