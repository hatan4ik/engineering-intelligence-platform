from __future__ import annotations

from pathlib import Path

from intelligence.extractors import ServiceMetadata, build_graph, metadata_from_manifest
from intelligence.graph import ServiceGraph


def build_service_graph_from_checkout(root: str | Path = ".") -> ServiceGraph:
    root_path = Path(root)
    metadata: list[ServiceMetadata] = []
    for path in root_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        if any(part in {".git", ".venv", "node_modules"} for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        item = metadata_from_manifest(path.as_posix(), content)
        if item is not None:
            metadata.append(item)
    return build_graph(metadata)
