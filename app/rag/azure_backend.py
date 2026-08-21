from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI


@dataclass(frozen=True)
class RetrievedDocument:
    source: str
    text: str
    score: float


class AzureRagBackend:
    """Azure AI Search + Azure OpenAI adapter.

    Security trimming is applied in Azure AI Search before context is sent to the model.
    Documents are expected to contain an `acl_groups` collection field.
    """

    def __init__(self) -> None:
        endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
        index = os.environ["AZURE_SEARCH_INDEX"]
        self.credential = DefaultAzureCredential()
        self.search = SearchClient(endpoint=endpoint, index_name=index, credential=self.credential)
        self.openai = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_ad_token_provider=self._token,
        )
        self.deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

    def _token(self) -> str:
        return self.credential.get_token("https://cognitiveservices.azure.com/.default").token

    @staticmethod
    def _acl_filter(groups: list[str]) -> str:
        if not groups:
            return "false"
        escaped = [g.replace("'", "''") for g in groups]
        clauses = [f"acl_groups/any(g: g eq '{g}')" for g in escaped]
        return " or ".join(clauses)

    def retrieve(self, question: str, repo: str | None, groups: list[str], top: int = 5) -> list[RetrievedDocument]:
        filters = [f"({self._acl_filter(groups)})"]
        if repo:
            filters.append(f"repo eq '{repo.replace(chr(39), chr(39) * 2)}'")
        result = self.search.search(
            search_text=question,
            query_type="semantic",
            semantic_configuration_name=os.getenv("AZURE_SEARCH_SEMANTIC_CONFIG", "default"),
            filter=" and ".join(filters),
            select=["source", "content"],
            top=top,
        )
        docs: list[RetrievedDocument] = []
        for item in result:
            docs.append(RetrievedDocument(
                source=str(item.get("source", "unknown")),
                text=str(item.get("content", "")),
                score=float(item.get("@search.reranker_score") or item.get("@search.score") or 0.0),
            ))
        return docs

    def synthesize(self, question: str, docs: list[RetrievedDocument]) -> str:
        context = "\n\n".join(f"SOURCE: {d.source}\n{d.text}" for d in docs)
        response = self.openai.chat.completions.create(
            model=self.deployment,
            temperature=0,
            messages=[
                {"role": "system", "content": "Answer only from supplied authorized evidence. If evidence is insufficient, say so. Cite source paths."},
                {"role": "user", "content": f"QUESTION:\n{question}\n\nEVIDENCE:\n{context}"},
            ],
        )
        return response.choices[0].message.content or "I do not have enough authorized evidence to answer."
