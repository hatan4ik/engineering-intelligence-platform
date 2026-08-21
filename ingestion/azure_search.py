from __future__ import annotations

from dataclasses import dataclass

from .models import Chunk


@dataclass
class AzureSearchIndex:
    endpoint: str
    index_name: str
    credential: object

    def _client(self):
        from azure.search.documents import SearchClient
        return SearchClient(endpoint=self.endpoint, index_name=self.index_name, credential=self.credential)

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        client = self._client()
        # Delete existing chunks for this source document before uploading the replacement set.
        # This makes rename/edit reconciliation deterministic and prevents stale chunks surviving.
        existing = client.search(search_text="*", filter=f"document_id eq '{document_id.replace("'", "''")}'", select=["id"])
        deletes = [{"id": row["id"]} for row in existing]
        if deletes:
            client.delete_documents(documents=deletes)
        if chunks:
            client.upload_documents(documents=[c.as_index_document() for c in chunks])

    def delete_document(self, document_id: str) -> None:
        client = self._client()
        existing = client.search(search_text="*", filter=f"document_id eq '{document_id.replace("'", "''")}'", select=["id"])
        deletes = [{"id": row["id"]} for row in existing]
        if deletes:
            client.delete_documents(documents=deletes)

    def search(self, query: str, groups: list[str], users: list[str] | None = None) -> list[dict[str, object]]:
        client = self._client()
        users = users or []
        principals = [*(f"g:{g}" for g in groups), *(f"u:{u}" for u in users)]
        clauses = []
        if groups:
            escaped = [g.replace("'", "''") for g in groups]
            clauses.append(" or ".join(f"acl_groups/any(x: x eq '{g}')" for g in escaped))
        if users:
            escaped = [u.replace("'", "''") for u in users]
            clauses.append(" or ".join(f"acl_users/any(x: x eq '{u}')" for u in escaped))
        acl_filter = " or ".join(f"({c})" for c in clauses) if clauses else "false"
        results = client.search(search_text=query, filter=acl_filter, top=8)
        return [dict(r) for r in results]
