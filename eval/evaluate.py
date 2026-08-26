from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


@dataclass(frozen=True)
class EvalCase:
    question: str
    groups: tuple[str, ...]
    expected_sources: frozenset[str] = frozenset()
    forbidden_sources: frozenset[str] = frozenset()
    repository: str | None = None
    expect_refusal: bool = False


CASES = [
    EvalCase(
        "How should production remediation work?",
        ("engineering",),
        frozenset({"architecture/azure-devops-self-healing-reference.md"}),
        repository="engineering-intelligence-platform",
    ),
    EvalCase(
        "When should self-healing begin?",
        ("engineering",),
        frozenset({"roadmap/technical-roadmap-24-months.md"}),
    ),
    EvalCase(
        "Which FinOps cost controls apply?",
        ("finance",),
        frozenset({"finops/cfo-roi-model.md"}),
        repository="finance-planning",
    ),
    EvalCase(
        "Which FinOps cost controls apply?",
        ("engineering",),
        forbidden_sources=frozenset({"finops/cfo-roi-model.md"}),
        expect_refusal=True,
    ),
    EvalCase(
        "How should production remediation work?",
        ("engineering",),
        forbidden_sources=frozenset({"architecture/azure-devops-self-healing-reference.md"}),
        repository="unrelated-repository",
        expect_refusal=True,
    ),
    EvalCase(
        "What are the orbital kiwi migration rituals?",
        ("engineering",),
        expect_refusal=True,
    ),
]

INSUFFICIENT_EVIDENCE = "I do not have enough authorized evidence to answer."


def precision_at_k(retrieved: list[str], expected: set[str], k: int = 3) -> float:
    top = retrieved[:k]
    return sum(1 for s in top if s in expected) / max(1, len(top))


def recall_at_k(retrieved: list[str], expected: set[str], k: int = 3) -> float:
    top = set(retrieved[:k])
    return len(top & expected) / max(1, len(expected))


def evaluate_case(client: TestClient, case: EvalCase) -> dict[str, object]:
    response = client.post(
        "/v1/query",
        headers={"x-eip-groups": ",".join(case.groups)},
        json={"question": case.question, "repo": case.repository},
    )
    if response.status_code != 200:
        raise RuntimeError(f"gateway returned {response.status_code}: {response.text}")

    payload = response.json()
    sources = [str(item["source"]) for item in payload["evidence"]]
    expected = set(case.expected_sources)
    forbidden = set(case.forbidden_sources)
    refusal_correct = (payload["answer"] == INSUFFICIENT_EVIDENCE and payload["model"] == "none")
    citation_coverage = all(source in payload["answer"] for source in sources)
    acl_isolated = not bool(set(sources).intersection(forbidden))
    expected_refusal = refusal_correct if case.expect_refusal else not refusal_correct
    precision = precision_at_k(sources, expected) if expected else 1.0
    recall = recall_at_k(sources, expected) if expected else 1.0
    passed = all((
        expected.issubset(sources),
        acl_isolated,
        citation_coverage,
        expected_refusal,
        precision >= 1.0,
        recall >= 1.0,
    ))
    return {
        "question": case.question,
        "groups": list(case.groups),
        "repository": case.repository,
        "expected_sources": sorted(expected),
        "forbidden_sources": sorted(forbidden),
        "retrieved_sources": sources,
        "precision@3": precision,
        "recall@3": recall,
        "citation_coverage": citation_coverage,
        "acl_isolated": acl_isolated,
        "refusal_correct": refusal_correct,
        "expected_refusal": case.expect_refusal,
        "passed": passed,
    }


def main() -> None:
    original_backend = os.environ.get("EIP_BACKEND")
    original_header_identity = os.environ.get("EIP_ALLOW_HEADER_IDENTITY")
    os.environ["EIP_BACKEND"] = "deterministic"
    os.environ["EIP_ALLOW_HEADER_IDENTITY"] = "true"
    try:
        with TestClient(app) as client:
            rows = [evaluate_case(client, case) for case in CASES]
    finally:
        if original_backend is None:
            os.environ.pop("EIP_BACKEND", None)
        else:
            os.environ["EIP_BACKEND"] = original_backend
        if original_header_identity is None:
            os.environ.pop("EIP_ALLOW_HEADER_IDENTITY", None)
        else:
            os.environ["EIP_ALLOW_HEADER_IDENTITY"] = original_header_identity

    summary = {
        "cases": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "precision@3": sum(float(row["precision@3"]) for row in rows) / len(rows),
        "recall@3": sum(float(row["recall@3"]) for row in rows) / len(rows),
        "citation_coverage": all(bool(row["citation_coverage"]) for row in rows),
        "acl_isolation": all(bool(row["acl_isolated"]) for row in rows),
        "refusal_accuracy": all(
            bool(row["refusal_correct"]) == bool(row["expected_refusal"])
            for row in rows
        ),
    }
    if summary["passed"] != summary["cases"]:
        raise SystemExit(json.dumps({"summary": summary, "cases": rows}, indent=2))

    out = Path('eval/results.json')
    out.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2, sort_keys=True))
    print(json.dumps({"summary": summary, "cases": rows}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
