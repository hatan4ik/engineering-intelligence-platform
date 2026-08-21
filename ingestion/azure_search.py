from __future__ import annotations

from dataclasses import dataclass

from .models import Chunk


def _odata_escape(value: str) -> str:
    return value.replace("'", "''")


@dataclass
class AzureSearchIndex:
    endpoint: str
    index_name: str
    credential: object

    def _client(self):
        from azure.search.documents import SearchClient
        return SearchClient(endpoint=self.endpoint, index_name=self.index_name, credential=self.credential)

    def _document_filter(self, document_id: str) -> str:
        return f"document_id eq '{_odata_escape(document_id)}'"

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        client = self._client()
        existing = client.search(
            search_text="*",
            filter=self._document_filter(document_id),
            select=["id"],
        )
        deletes = [{"id": row["id"]} for row in existing]
        if deletes:
            client.delete_documents(documents=deletes)
        if chunks:
            client.upload_documents(documents=[c.as_index_document() for c in chunks])

    def delete_document(self, document_id: str) -> None:
        client = self._client()
        existing = client.search(
            search_text="*",
            filter=self._document_filter(document_id),
            select=["id"],
        )
        deletes = [{"id": row["id"]} for row in existing]
        if deletes:
            client.delete_documents(documents=deletes)

    def search(self, query: str, groups: list[str], users: list[str] | None = None) -> list[dict[str, object]]:
        client = self._client()
        users = users or []
        clauses: list[str] = []
        if groups:
            escaped_groups = [_odata_escape(g) for g in groups]
            clauses.append(" or ".join(f"acl_groups/any(x: x eq '{g}')" for g in escaped_groups))
        if users:
            escaped_users = [_odata_escape(u) for u in users]
            clauses.append(" or ".join(f"acl_users/any(x: x eq '{u}')" for u in escaped_users))

        acl_filter = " or ".join(f"({clause})" for clause in clauses) if clauses else "false"
        results = client.search(search_text=query, filter=acl_filter, top=8)
        return [dict(result) for result in results]
