from __future__ import annotations

from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
)


def build_index(name: str, *, dimensions: int) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="provider", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="repository", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="branch", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="commit_sha", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="path", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="source", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="ordinal", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchableField(name="symbol", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="language", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="owner", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="service", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="acl_groups", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SearchField(name="acl_users", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name="eip-vector-profile",
        ),
        SimpleField(name="content_hash", type=SearchFieldDataType.String, filterable=True),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="eip-hnsw")],
        profiles=[VectorSearchProfile(name="eip-vector-profile", algorithm_configuration_name="eip-hnsw")],
    )
    semantic = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="default",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="path"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="symbol"), SemanticField(field_name="service")],
                ),
            )
        ]
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector_search, semantic_search=semantic)
