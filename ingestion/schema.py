from __future__ import annotations


def azure_search_fields():
    from azure.search.documents.indexes.models import SearchField, SearchFieldDataType, SimpleField

    return [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="provider", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="repository", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="branch", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="commit_sha", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="path", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="ordinal", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchField(name="symbol", type=SearchFieldDataType.String, searchable=True, filterable=True),
        SimpleField(name="language", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="owner", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="service", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(
            name="acl_groups",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
        ),
        SearchField(
            name="acl_users",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
        ),
    ]
