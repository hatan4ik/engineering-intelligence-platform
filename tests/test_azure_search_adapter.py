from ingestion.azure_search import AzureSearchIndex, _odata_escape


def test_odata_escape_quotes():
    assert _odata_escape("repo'o") == "repo''o"


def test_document_filter_escapes_id():
    index = AzureSearchIndex("https://example.search.windows.net", "idx", object())
    assert index._document_filter("doc'o") == "document_id eq 'doc''o'"
