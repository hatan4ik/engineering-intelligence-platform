"""Ingest a checked-out repository into a knowledge index.

The ``in-memory`` index runs the whole pipeline in-process and is what CI
exercises as a smoke test. The ``azure`` index requires complete configuration
and fails closed with the full list of missing variables — it never falls back
to a placeholder endpoint or an unauthenticated client.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Mapping

from ingestion.index import Index, InMemoryIndex
from ingestion.runner import ingest_checkout

#: Always required by ``--index azure``.
AZURE_REQUIRED: tuple[str, ...] = ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX")

#: One of these must supply the Azure AI Search credential. ``AZURE_SEARCH_API_KEY``
#: builds a key credential; ``AZURE_CLIENT_ID`` selects the workload identity that
#: ``DefaultAzureCredential`` resolves, which is how the deployed platform runs.
AZURE_CREDENTIAL_ALTERNATIVES: tuple[str, ...] = ("AZURE_SEARCH_API_KEY", "AZURE_CLIENT_ID")

INDEX_CHOICES: tuple[str, ...] = ("in-memory", "azure")


def _identity_credential() -> object:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def resolve_index(kind: str, environ: Mapping[str, str]) -> Index:
    """Build the requested index, or raise ``RuntimeError`` naming every gap."""

    if kind == "in-memory":
        return InMemoryIndex()
    if kind != "azure":
        raise RuntimeError(f"unknown index {kind!r}; expected one of {', '.join(INDEX_CHOICES)}")

    missing = [name for name in AZURE_REQUIRED if not str(environ.get(name, "")).strip()]
    api_key = str(environ.get("AZURE_SEARCH_API_KEY", "")).strip()
    client_id = str(environ.get("AZURE_CLIENT_ID", "")).strip()
    if not api_key and not client_id:
        missing.append(" or ".join(AZURE_CREDENTIAL_ALTERNATIVES))
    if missing:
        raise RuntimeError(
            "--index azure is not configured; missing required environment: " + ", ".join(missing)
        )

    from ingestion.azure_search import AzureSearchIndex

    if api_key:
        from azure.core.credentials import AzureKeyCredential

        credential: object = AzureKeyCredential(api_key)
    else:
        credential = _identity_credential()
    return AzureSearchIndex(
        endpoint=str(environ["AZURE_SEARCH_ENDPOINT"]).strip(),
        index_name=str(environ["AZURE_SEARCH_INDEX"]).strip(),
        credential=credential,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="path to the checked-out repository")
    parser.add_argument("--repository", required=True, help="owner/name of the repository")
    # Document identity vs provenance. The branch keys document_id, so ingesting a
    # branch replaces its documents; the commit sha only appears in the citation.
    parser.add_argument("--branch", required=True, help="branch being ingested; keys document identity")
    parser.add_argument("--commit-sha", required=True, help="commit SHA for the chunk citation")
    parser.add_argument(
        "--groups",
        required=True,
        help="comma-separated ACL groups granted read access to the indexed chunks",
    )
    parser.add_argument("--index", choices=INDEX_CHOICES, default="in-memory")
    parser.add_argument("--ledger", default="ingestion-ledger.db", help="durable event ledger path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    groups = [group.strip() for group in args.groups.split(",") if group.strip()]
    try:
        index = resolve_index(args.index, os.environ)
        counts = ingest_checkout(
            args.root,
            repository=args.repository,
            branch=args.branch,
            commit_sha=args.commit_sha,
            index=index,
            ledger_path=args.ledger,
            groups=groups,
        )
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    payload = {
        "repository": args.repository,
        "branch": args.branch,
        "commit_sha": args.commit_sha,
        "index": args.index,
        "groups": groups,
        **counts,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
