"""Governed query route and its deterministic reference retrieval adapter."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.authentication import configured_authenticator
from app.gateway import GatewayAuthError, GatewayPolicyError, authorize_request
from app.observability import tracer
from app.settings import ApplicationSettings, SettingsError, settings_for_application
from control_plane.correlation import resolve_correlation_id


router = APIRouter(prefix="/v1", tags=["governed-query"])
trace = tracer()


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


@dataclass(frozen=True)
class DemoDocument:
    evidence: Evidence
    groups: tuple[str, ...]
    repository: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class InMemoryRetriever:
    """Deterministic reference retrieval for demo, API tests, and CI evaluation.

    It preserves the two properties that matter to the gateway contract:
    evidence must match the request and callers must be authorized before it is
    returned.
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
        authorized = {group.strip() for group in groups if group.strip()}
        terms = {
            term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) >= 3
        }
        matches: list[Evidence] = []
        for document in self.corpus:
            if not authorized.intersection(document.groups):
                continue
            if repo is not None and repo != document.repository:
                continue
            matched_keywords = len(terms.intersection(document.keywords))
            if matched_keywords:
                matches.append(
                    document.evidence.model_copy(
                        update={"score": document.evidence.score + matched_keywords / 100}
                    )
                )
        return sorted(matches, key=lambda item: (-item.score, item.source))


def authorized_groups(raw: str | None) -> list[str]:
    return [group.strip() for group in (raw or "engineering").split(",") if group.strip()]


def _gateway_identity(
    *,
    settings: ApplicationSettings,
    question: str,
    api_key: str | None,
    authorization: str | None,
    requested_model_tier: str | None,
    fallback_groups: str | None,
    fallback_user: str | None,
) -> tuple[str, list[str], str, str]:
    if settings.query.header_identity_permitted:
        return question, authorized_groups(fallback_groups), fallback_user or "local-demo", "standard"

    authentication = settings.query.authentication
    try:
        store = configured_authenticator(authentication)
        if authentication.mode == "entra":
            credential = authorization
        else:
            credential = api_key
        decision = authorize_request(
            question=question,
            api_key=credential,
            requested_model_tier=requested_model_tier,
            estimated_cost_usd=settings.query.estimated_request_usd,
            store=store,
        )
    except (GatewayAuthError, GatewayPolicyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=401 if isinstance(exc, GatewayAuthError) else 403,
            detail=str(exc),
        ) from exc
    return (
        decision.sanitized_question,
        list(decision.principal.groups),
        decision.principal.subject,
        decision.model_tier,
    )


@router.post("/query", response_model=QueryResponse)
def query(
    req: QueryRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_eip_groups: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
    x_eip_api_key: str | None = Header(default=None),
    x_eip_model_tier: str | None = Header(default=None),
) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        settings = settings_for_application(request.app)
    except SettingsError as exc:
        raise HTTPException(status_code=503, detail=f"invalid application configuration: {exc}") from exc
    question, groups, user, model_tier = _gateway_identity(
        settings=settings,
        question=req.question,
        api_key=x_eip_api_key,
        authorization=authorization,
        requested_model_tier=x_eip_model_tier,
        fallback_groups=x_eip_groups,
        fallback_user=x_eip_user,
    )
    try:
        correlation_id = resolve_correlation_id(x_correlation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with trace.start_as_current_span("eip.query") as span:
        span.set_attribute("eip.correlation_id", correlation_id)
        span.set_attribute("eip.repo", req.repo or "")
        span.set_attribute("eip.service", req.service or "")
        span.set_attribute("eip.group_count", len(groups))
        span.set_attribute("eip.model_tier", model_tier)
        span.set_attribute("eip.user", user)
        span.set_attribute("eip.redacted", question != req.question)

        if settings.query.backend == "azure":
            from app.rag.azure_backend import AzureRagBackend

            azure_rag = settings.query.azure_rag
            if azure_rag is None:
                raise HTTPException(
                    status_code=503,
                    detail="Azure backend configuration is unavailable",
                )
            deployment = azure_rag.deployment_for(model_tier)
            backend = AzureRagBackend(settings=azure_rag, deployment=deployment)
            docs = backend.retrieve(
                question,
                req.repo,
                groups,
                correlation_id=correlation_id,
                service=req.service,
                user=user,
            )
            evidence = [Evidence(source=document.source, text=document.text, score=document.score) for document in docs]
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
        citations = "; ".join(item.source for item in evidence)
        return QueryResponse(
            answer=f"{' '.join(item.text for item in evidence)} Sources: {citations}",
            evidence=evidence,
            model="deterministic-demo",
            correlation_id=correlation_id,
        )
