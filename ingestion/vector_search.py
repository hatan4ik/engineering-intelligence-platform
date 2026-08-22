from __future__ import annotations

import os
from dataclasses import dataclass

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI


def _odata_escape(value: str) -> str:
    return value.replace("'", "''")


@dataclass(frozen=True)
class HybridHit:
    source: str
    content: str
    score: float
    repository: str | None = None
    path: str | None = None
    service: str | None = None


class AzureOpenAIEmbedder:
    def __init__(self, credential: DefaultAzureCredential | None = None) -> None:
        self.credential = credential or DefaultAzureCredential()
        self.deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
        self.client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_ad_token_provider=self._token,
        )

    def _token(self) -> str:
        return self.credential.get_token("https://cognitiveservices.azure.com/.default").token

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.deployment, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


class AzureHybridRetriever:
    """ACL-trimmed lexical + vector retrieval with semantic reranking.

    Security filtering is part of the Search request and therefore occurs before
    returned evidence can enter model context.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        index_name: str,
        embedder: AzureOpenAIEmbedder,
        credential: DefaultAzureCredential | None = None,
        semantic_configuration: str = "default",
    ) -> None:
        self.credential = credential or DefaultAzureCredential()
        self.client = SearchClient(endpoint, index_name, self.credential)
        self.embedder = embedder
        self.semantic_configuration = semantic_configuration

    @staticmethod
    def acl_filter(groups: list[str], users: list[str] | None = None) -> str:
        users = users or []
        clauses: list[str] = []
        if groups:
            clauses.extend(f"acl_groups/any(g: g eq '{_odata_escape(g)}')" for g in groups)
        if users:
            clauses.extend(f"acl_users/any(u: u eq '{_odata_escape(u)}')" for u in users)
        return " or ".join(f"({c})" for c in clauses) if clauses else "false"

    def retrieve(
        self,
        question: str,
        *,
        groups: list[str],
        users: list[str] | None = None,
        repository: str | None = None,
        top: int = 8,
    ) -> list[HybridHit]:
        vector = self.embedder.embed([question])[0]
        filters = [f"({self.acl_filter(groups, users)})"]
        if repository:
            filters.append(f"repository eq '{_odata_escape(repository)}'")
        query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=max(top * 2, top),
            fields="embedding",
        )
        results = self.client.search(
            search_text=question,
            vector_queries=[query],
            query_type="semantic",
            semantic_configuration_name=self.semantic_configuration,
            filter=" and ".join(filters),
            select=["source", "content", "repository", "path", "service"],
            top=top,
        )
        hits: list[HybridHit] = []
        for item in results:
            score = float(item.get("@search.reranker_score") or item.get("@search.score") or 0.0)
            hits.append(
                HybridHit(
                    source=str(item.get("source") or item.get("path") or "unknown"),
                    content=str(item.get("content", "")),
                    score=score,
                    repository=item.get("repository"),
                    path=item.get("path"),
                    service=item.get("service"),
                )
            )
        return hits
