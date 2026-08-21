from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Protocol

from .models import Chunk


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicEmbedder:
    """Credential-free test embedder. Not for semantic production retrieval."""

    def __init__(self, dimensions: int = 16) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [digest[i % len(digest)] / 255.0 for i in range(self.dimensions)]
            vectors.append(raw)
        return vectors


def enrich_chunks(chunks: list[Chunk], embedder: Embedder) -> list[Chunk]:
    if not chunks:
        return []
    vectors = embedder.embed([c.content for c in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("embedder returned unexpected vector count")
    enriched: list[Chunk] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        enriched.append(
            replace(
                chunk,
                embedding=tuple(float(v) for v in vector),
                content_hash=hashlib.sha256(chunk.content.encode()).hexdigest(),
            )
        )
    return enriched
