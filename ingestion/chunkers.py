from __future__ import annotations

import ast
import hashlib
from typing import Protocol

from .models import Chunk, FileChange


class Chunker(Protocol):
    def chunk(self, change: FileChange) -> list[Chunk]: ...


def _chunk_id(change: FileChange, ordinal: int, symbol: str | None, content: str) -> str:
    raw = "|".join([
        change.source.document_id,
        change.source.commit_sha,
        str(ordinal),
        symbol or "",
        hashlib.sha256(content.encode("utf-8")).hexdigest(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PythonASTChunker:
    def chunk(self, change: FileChange) -> list[Chunk]:
        content = change.content or ""
        tree = ast.parse(content)
        lines = content.splitlines()
        chunks: list[Chunk] = []

        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        if not nodes:
            return TextChunker().chunk(change)

        for ordinal, node in enumerate(nodes):
            start = max(node.lineno - 1, 0)
            end = getattr(node, "end_lineno", node.lineno)
            text = "\n".join(lines[start:end]).strip()
            if not text:
                continue
            chunks.append(Chunk(
                id=_chunk_id(change, ordinal, node.name, text),
                document_id=change.source.document_id,
                source=change.source,
                content=text,
                ordinal=ordinal,
                symbol=node.name,
                language="python",
                owner=change.owner,
                service=change.service,
                acl=change.acl,
            ))
        return chunks


class TextChunker:
    def __init__(self, max_chars: int = 1800):
        self.max_chars = max_chars

    def chunk(self, change: FileChange) -> list[Chunk]:
        content = (change.content or "").strip()
        if not content:
            return []
        parts: list[str] = []
        buf: list[str] = []
        size = 0
        for block in content.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if buf and size + len(block) + 2 > self.max_chars:
                parts.append("\n\n".join(buf))
                buf, size = [], 0
            buf.append(block)
            size += len(block) + 2
        if buf:
            parts.append("\n\n".join(buf))

        return [Chunk(
            id=_chunk_id(change, ordinal, None, text),
            document_id=change.source.document_id,
            source=change.source,
            content=text,
            ordinal=ordinal,
            symbol=None,
            language=change.language,
            owner=change.owner,
            service=change.service,
            acl=change.acl,
        ) for ordinal, text in enumerate(parts)]


def chunk_change(change: FileChange) -> list[Chunk]:
    if (change.language or "").lower() in {"py", "python"} or change.source.path.endswith(".py"):
        try:
            return PythonASTChunker().chunk(change)
        except SyntaxError:
            return TextChunker().chunk(change)
    return TextChunker().chunk(change)
