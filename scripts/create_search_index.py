from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient

from ingestion.search_schema import build_index


def main() -> None:
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX"]
    dimensions = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))
    client = SearchIndexClient(endpoint=endpoint, credential=DefaultAzureCredential())
    index = build_index(index_name, dimensions=dimensions)
    client.create_or_update_index(index)
    print(f"configured Azure AI Search index {index_name} with {dimensions} vector dimensions")


if __name__ == "__main__":
    main()
