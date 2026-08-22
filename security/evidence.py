from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .adversarial import ContentAssessment, assess_retrieved_content


class EvidenceLike(Protocol):
    source: str
    text: str


@dataclass(frozen=True)
class EvidenceSecurityResult:
    safe_sources: tuple[str, ...]
    suspicious_sources: tuple[str, ...]
    matches: tuple[tuple[str, tuple[str, ...]], ...]


def classify_evidence(documents: Iterable[EvidenceLike]) -> EvidenceSecurityResult:
    safe: list[str] = []
    suspicious: list[str] = []
    matches: list[tuple[str, tuple[str, ...]]] = []
    for document in documents:
        assessment: ContentAssessment = assess_retrieved_content(document.text)
        if assessment.suspicious:
            suspicious.append(document.source)
            matches.append((document.source, assessment.matches))
        else:
            safe.append(document.source)
    return EvidenceSecurityResult(tuple(safe), tuple(suspicious), tuple(matches))
