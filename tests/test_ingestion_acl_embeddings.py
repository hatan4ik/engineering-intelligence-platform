from ingestion.acl import StaticACLResolver, apply_resolved_acl
from ingestion.embeddings import DeterministicEmbedder, enrich_chunks
from ingestion.models import ACL, ChangeType, Chunk, FileChange, SourceIdentity


def test_acl_resolver_overrides_default_repo_acl():
    source = SourceIdentity("github", "acme/payments", "main", "abc", "app.py")
    change = FileChange(source=source, change_type=ChangeType.UPSERT, content="x")
    resolver = StaticACLResolver({"github:acme/payments": ACL(groups=("payments",), users=("alice",))})
    resolved = apply_resolved_acl(change, resolver)
    assert resolved.acl.groups == ("payments",)
    assert resolved.acl.users == ("alice",)


def test_embedding_enrichment_is_deterministic():
    source = SourceIdentity("github", "acme/payments", "main", "abc", "app.py")
    chunk = Chunk(id="1", document_id=source.document_id, source=source, content="def pay(): pass", ordinal=0)
    embedder = DeterministicEmbedder(dimensions=8)
    first = enrich_chunks([chunk], embedder)[0]
    second = enrich_chunks([chunk], embedder)[0]
    assert first.embedding == second.embedding
    assert len(first.embedding) == 8
    assert first.content_hash == second.content_hash
