from ingestion.models import ACL, Chunk, SourceIdentity
from ingestion.search_schema import build_index
from ingestion.vector_search import AzureHybridRetriever


def test_chunk_indexes_stable_citation_source():
    source = SourceIdentity(
        provider="github",
        repository="acme/payments",
        branch="main",
        commit_sha="abc123",
        path="services/payments/auth.py",
    )
    chunk = Chunk(
        id="c1",
        document_id=source.document_id,
        source=source,
        content="def verify_token(): pass",
        ordinal=0,
        acl=ACL(groups=("payments",)),
        embedding=(0.1, 0.2, 0.3),
    )
    doc = chunk.as_index_document()
    assert doc["source"] == "github:acme/payments@abc123:services/payments/auth.py"
    assert doc["acl_groups"] == ["payments"]


def test_vector_schema_uses_requested_dimensions():
    index = build_index("eip", dimensions=1536)
    embedding = next(field for field in index.fields if field.name == "embedding")
    assert embedding.vector_search_dimensions == 1536
    assert embedding.vector_search_profile_name == "eip-vector-profile"
    assert index.semantic_search.configurations[0].name == "default"


def test_acl_filter_is_fail_closed_and_escapes_values():
    assert AzureHybridRetriever.acl_filter([], []) == "false"
    expression = AzureHybridRetriever.acl_filter(["eng", "o'hare"], ["alice"])
    assert "acl_groups/any" in expression
    assert "o''hare" in expression
    assert "acl_users/any" in expression
