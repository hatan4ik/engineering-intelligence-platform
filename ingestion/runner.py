"""Drive the ingestion pipeline over a checked-out repository working tree.

This is the batch entry point for the knowledge plane. ``ingestion.events``
normalizes *webhook* payloads; this module normalizes a *checkout*, so a
repository can be indexed from CI without a webhook delivery.

Document identity is the *branch*: ``SourceIdentity.document_id`` is
``git:<repository>:<branch>:<path>``, so re-ingesting a branch replaces its
documents instead of accumulating one per commit. The commit sha is provenance
— it is carried in ``SourceIdentity.commit_sha`` and therefore in the chunk
citation ``git:<repository>@<commit>:<path>``.

Idempotency comes from the durable event ledger, not from this module: every
eligible file becomes one :class:`~ingestion.events.NormalizedEvent` whose
``event_id`` is derived from ``(repository, branch, path, content, acl)``. Re-running
over an unchanged checkout therefore replays event ids the ledger has already
completed and writes nothing, and a later commit re-ingests only the files whose
content actually changed. A file's citation consequently names the commit at
which its content was last ingested, which is the commit that content came from.

The caller supplies the :class:`~ingestion.index.Index` instance. This module
never constructs an Azure client and never reads Azure configuration.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .events import NormalizedEvent
from .index import Index
from .models import ACL, ChangeType, FileChange, SourceIdentity
from .pipeline import IngestionPipeline
from .worker import sqlite_worker

#: Directory *names* pruned during the walk (matched against each path segment).
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".terraform",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site-packages",
        "venv",
    }
)

#: File suffixes the existing chunkers can turn into useful evidence.
INGESTIBLE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".bicep",
        ".cfg",
        ".cs",
        ".go",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".md",
        ".proto",
        ".ps1",
        ".py",
        ".rb",
        ".rego",
        ".rs",
        ".rst",
        ".sh",
        ".sql",
        ".tf",
        ".tfvars",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)

#: Extension-less files that are still source knowledge.
INGESTIBLE_NAMES: frozenset[str] = frozenset({"Dockerfile", "Makefile", "CODEOWNERS", "LICENSE"})

#: Files larger than this are skipped; chunking them produces noise, not evidence.
DEFAULT_MAX_FILE_BYTES: int = 512 * 1024


def _is_ingestible(path: Path) -> bool:
    return path.suffix.lower() in INGESTIBLE_SUFFIXES or path.name in INGESTIBLE_NAMES


def _read_text(path: Path, limit: int) -> str | None:
    """Return the file's text, or ``None`` when it is not decodable UTF-8."""

    data = path.read_bytes()[: limit + 1]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _walk(root: Path) -> Iterator[Path]:
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in EXCLUDED_DIRECTORIES
        )
        for filename in sorted(filenames):
            yield Path(directory) / filename


def _event_id(repository: str, branch: str, relative_path: str, content: str, acl: ACL) -> str:
    # Deliberately excludes the commit sha: the unit of work is "this content at
    # this path on this branch, readable by these principals". Including the sha
    # would re-ingest every file on every commit and defeat the ledger; excluding
    # the ACL would let the ledger swallow an access change, which
    # docs/PRODUCTION-EVIDENCE.md requires to propagate.
    digest = hashlib.sha256(
        "|".join(
            [repository, branch, relative_path, content, *sorted(acl.groups), *sorted(acl.users)]
        ).encode("utf-8")
    ).hexdigest()
    return f"checkout:{repository}:{branch}:{relative_path}:{digest}"


def resolve_acl(repository: str, groups: Sequence[str]) -> ACL:
    """Compose the checkout ACL from the repository contract plus caller groups.

    ``ingestion.events`` grants ``repo:<repository>:read`` to everything it
    normalizes; checkout ingestion keeps that contract so the same principals
    see the same repository whichever path indexed it.
    """

    cleaned = [group.strip() for group in groups if group and group.strip()]
    if not cleaned:
        raise ValueError(
            "ingest_checkout requires a non-empty groups list; refusing to index "
            "chunks with no ACL groups because an empty ACL is readable by every caller"
        )
    return ACL(groups=tuple(dict.fromkeys([f"repo:{repository}:read", *cleaned])))


def ingest_checkout(
    root: str | os.PathLike[str],
    *,
    repository: str,
    branch: str,
    commit_sha: str,
    index: Index,
    ledger_path: str | os.PathLike[str],
    groups: Iterable[str],
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, int]:
    """Ingest every eligible file under ``root`` into ``index``.

    Returns the run counts:

    ``documents``
        Documents written to the index by this run.
    ``chunks``
        Chunks written to the index by this run.
    ``skipped``
        Files that are not ingestible source knowledge (unsupported suffix,
        oversize, or not decodable as UTF-8).
    ``failed``
        Files that could not be read or that the pipeline rejected. A failure
        does not abort the run. Read failures never reach the ledger (no event
        exists yet), so they are not in its dead-letter queue; every failed
        path is listed in ``failed_paths`` so a silently dropped file is visible.
    ``failed_paths``
        The checkout-relative paths counted in ``failed``, in walk order.
    ``duplicates``
        Files whose event id the ledger had already completed — the idempotency
        signal. A re-run over an unchanged checkout reports ``documents == 0``.

    ``branch`` is document identity; ``commit_sha`` is provenance. Ingesting the
    same branch at a later commit replaces the documents whose content changed
    and leaves the rest untouched.
    """

    if not str(branch).strip():
        raise ValueError("ingest_checkout requires a branch; it is the document identity")
    if not str(commit_sha).strip():
        raise ValueError("ingest_checkout requires a commit_sha; it is the citation provenance")
    acl = resolve_acl(repository, list(groups))
    checkout = Path(root).resolve()
    if not checkout.is_dir():
        raise ValueError(f"checkout root is not a directory: {checkout}")

    pipeline = IngestionPipeline(index=index)
    worker = sqlite_worker(pipeline, str(ledger_path))

    counts: dict[str, object] = {
        "documents": 0, "chunks": 0, "skipped": 0, "failed": 0, "duplicates": 0,
    }
    failed_paths: list[str] = []
    counts["failed_paths"] = failed_paths

    def _bump(key: str) -> None:
        counts[key] = int(counts[key]) + 1  # type: ignore[call-overload]

    for path in _walk(checkout):
        if not _is_ingestible(path):
            _bump("skipped")
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                _bump("skipped")
                continue
            content = _read_text(path, max_file_bytes)
        except OSError:
            _bump("failed")
            failed_paths.append(path.relative_to(checkout).as_posix())
            continue
        if content is None:
            _bump("skipped")
            continue

        relative_path = path.relative_to(checkout).as_posix()
        suffix = path.suffix.lstrip(".").lower()
        change = FileChange(
            source=SourceIdentity("git", repository, branch, commit_sha, relative_path),
            change_type=ChangeType.UPSERT,
            content=content,
            language=suffix or None,
            acl=acl,
        )
        event = NormalizedEvent(
            event_id=_event_id(repository, branch, relative_path, content, acl),
            changes=(change,),
        )
        try:
            result = worker.handle(event)
        except Exception:  # noqa: BLE001 - one bad file must not abort the checkout
            _bump("failed")
            failed_paths.append(relative_path)
            continue
        if result.get("duplicate"):
            _bump("duplicates")
            continue
        counts["documents"] = int(counts["documents"]) + int(result.get("upserted", 0))  # type: ignore[call-overload]
        counts["chunks"] = int(counts["chunks"]) + int(result.get("chunks", 0))  # type: ignore[call-overload]
    return counts
