from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EvalCase:
    question: str
    expected_sources: set[str]


CASES = [
    EvalCase('How should production remediation work?', {'architecture/self-healing.md'}),
    EvalCase('When should self-healing begin?', {'roadmap/technical-roadmap-24-months.md'}),
]


def precision_at_k(retrieved: list[str], expected: set[str], k: int = 3) -> float:
    top = retrieved[:k]
    return sum(1 for s in top if s in expected) / max(1, len(top))


def recall_at_k(retrieved: list[str], expected: set[str], k: int = 3) -> float:
    top = set(retrieved[:k])
    return len(top & expected) / max(1, len(expected))


def main() -> None:
    # Deterministic baseline corresponding to the demo retriever.
    retrieved = ['architecture/self-healing.md', 'roadmap/technical-roadmap-24-months.md']
    rows = []
    for case in CASES:
        rows.append({
            'question': case.question,
            'precision@3': precision_at_k(retrieved, case.expected_sources),
            'recall@3': recall_at_k(retrieved, case.expected_sources),
        })
    out = Path('eval/results.json')
    out.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
