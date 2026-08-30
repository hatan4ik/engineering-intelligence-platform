"""Azure RAG composition and dependency-boundary contract tests."""

from __future__ import annotations

import pytest
from azure.core.exceptions import ServiceRequestError

from app.rag.azure_backend import (
    DEFAULT_AZURE_RAG_TIMEOUT_SECONDS,
    AzureRagBackendFactory,
    AzureRagDependencyControls,
)
from app.settings import AzureRagSettings
from resilience.dependencies import DependencyBoundary, DependencyLimits, DependencyUnavailable


class _Credential:
    def get_token(self, *scopes: str) -> object:
        return object()


class _SearchClient:
    constructed: list[dict[str, object]] = []
    calls = 0

    def __init__(self, **kwargs: object) -> None:
        self.constructed.append(kwargs)

    def search(self, **kwargs: object) -> object:
        type(self).calls += 1
        raise ServiceRequestError("Azure Search unavailable")


class _OpenAIClient:
    constructed: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructed.append(kwargs)


def _settings() -> AzureRagSettings:
    return AzureRagSettings(
        search_endpoint="https://search.invalid",
        search_index="company-brain",
        openai_endpoint="https://openai.invalid",
        chat_deployment="standard",
        advanced_chat_deployment="advanced",
        embedding_deployment=None,
        openai_api_version="2024-10-21",
        search_semantic_configuration="default",
        input_per_million_tokens_usd=0.0,
        output_per_million_tokens_usd=0.0,
        search_per_1000_queries_usd=0.0,
        tool_call_usd=0.0,
    )


def _controls() -> AzureRagDependencyControls:
    return AzureRagDependencyControls(
        search=DependencyBoundary(
            "azure-ai-search",
            DependencyLimits(failure_threshold=1, recovery_seconds=30),
        ),
        openai=DependencyBoundary(
            "azure-openai",
            DependencyLimits(failure_threshold=1, recovery_seconds=30),
        ),
    )


def test_factory_reuses_process_owned_clients_and_has_no_hidden_sdk_retries(monkeypatch):
    _SearchClient.constructed = []
    _OpenAIClient.constructed = []
    monkeypatch.setattr("app.rag.azure_backend.DefaultAzureCredential", _Credential)
    monkeypatch.setattr("app.rag.azure_backend.SearchClient", _SearchClient)
    monkeypatch.setattr("app.rag.azure_backend.AzureOpenAI", _OpenAIClient)
    factory = AzureRagBackendFactory(_settings(), dependency_controls=_controls())

    standard = factory.for_model_tier("standard")
    assert factory.for_model_tier("standard") is standard
    factory.for_model_tier("advanced")

    assert len(_SearchClient.constructed) == 2
    assert len(_OpenAIClient.constructed) == 2
    assert _SearchClient.constructed[0]["retry_total"] == 0
    assert _SearchClient.constructed[0]["connection_timeout"] == DEFAULT_AZURE_RAG_TIMEOUT_SECONDS
    assert _OpenAIClient.constructed[0]["max_retries"] == 0
    assert _OpenAIClient.constructed[0]["timeout"] == DEFAULT_AZURE_RAG_TIMEOUT_SECONDS


def test_search_boundary_rejects_repeated_requests_after_a_transient_sdk_failure(monkeypatch):
    _SearchClient.calls = 0
    monkeypatch.setattr("app.rag.azure_backend.DefaultAzureCredential", _Credential)
    monkeypatch.setattr("app.rag.azure_backend.SearchClient", _SearchClient)
    monkeypatch.setattr("app.rag.azure_backend.AzureOpenAI", _OpenAIClient)
    backend = AzureRagBackendFactory(_settings(), dependency_controls=_controls()).for_model_tier("standard")

    with pytest.raises(DependencyUnavailable, match="azure-ai-search"):
        backend.retrieve("What changed?", None, ["engineering"])
    with pytest.raises(DependencyUnavailable, match="circuit is open"):
        backend.retrieve("What changed?", None, ["engineering"])

    assert _SearchClient.calls == 1
