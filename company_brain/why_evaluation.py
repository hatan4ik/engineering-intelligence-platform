"""Evaluation contracts for evidence-backed Company Brain *why* answers.

The evaluator does not grade prose quality or infer truth from a model answer.
It verifies the enforceable properties of a useful explanation: the response is
bound to the supplied context packet, cites only authorized retained evidence,
names only supplied relationships, discloses required limitations, and abstains
when the packet is incomplete or unqualified.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping, assert_never

from .context_packet import ContextPacket
from .decision_context import DecisionContextRelationship
from .product_contracts import ProductContractError


class WhyEvaluationError(ProductContractError):
    """Raised when an evaluation corpus or answer has an ambiguous contract."""


class WhyAnswerDisposition(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"


class WhyEvaluationFailure(StrEnum):
    CONTEXT_MISMATCH = "context_mismatch"
    WRONG_DISPOSITION = "wrong_disposition"
    UNSAFE_CONTEXT_ANSWER = "unsafe_context_answer"
    UNSUPPORTED_RELATIONSHIP = "unsupported_relationship"
    UNSUPPORTED_EVIDENCE = "unsupported_evidence"
    MISSING_REQUIRED_RELATIONSHIP = "missing_required_relationship"
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    LIMITATIONS_NOT_DISCLOSED = "limitations_not_disclosed"


def describe_why_evaluation_failure(failure: WhyEvaluationFailure) -> str:
    """Describe each machine-checkable explanation failure exhaustively."""

    match failure:
        case WhyEvaluationFailure.CONTEXT_MISMATCH:
            return "The response was prepared from a different Company Brain context packet."
        case WhyEvaluationFailure.WRONG_DISPOSITION:
            return "The response did not answer or abstain as the evaluation case requires."
        case WhyEvaluationFailure.UNSAFE_CONTEXT_ANSWER:
            return "The response answered from an unqualified or incomplete context packet."
        case WhyEvaluationFailure.UNSUPPORTED_RELATIONSHIP:
            return "The response named a relationship outside the supplied context packet."
        case WhyEvaluationFailure.UNSUPPORTED_EVIDENCE:
            return "The response cited evidence outside the supplied context packet."
        case WhyEvaluationFailure.MISSING_REQUIRED_RELATIONSHIP:
            return "The response omitted a required relationship claim."
        case WhyEvaluationFailure.MISSING_REQUIRED_EVIDENCE:
            return "The response omitted a required evidence citation."
        case WhyEvaluationFailure.LIMITATIONS_NOT_DISCLOSED:
            return "The response did not disclose required context limitations."
        case _ as unreachable:
            assert_never(unreachable)


@dataclass(frozen=True)
class WhyAnswer:
    """A product or model answer with its explicit factual support set."""

    context_version: str
    context_packet_digest: str
    disposition: WhyAnswerDisposition
    explanation: str
    relationship_keys: tuple[str, ...]
    cited_evidence_ids: tuple[str, ...]
    limitations_disclosed: bool

    def __post_init__(self) -> None:
        _text(self.context_version, "why answer context_version", maximum=240)
        _digest(self.context_packet_digest, "why answer context_packet_digest")
        if not isinstance(self.disposition, WhyAnswerDisposition):
            raise WhyEvaluationError("why answer disposition is invalid")
        _text(self.explanation, "why answer explanation", maximum=4_000)
        _sorted_relationship_keys(self.relationship_keys, "why answer relationship_keys")
        _sorted_identifiers(self.cited_evidence_ids, "why answer cited_evidence_ids")
        if type(self.limitations_disclosed) is not bool:
            raise WhyEvaluationError("why answer limitations_disclosed is invalid")
        if self.disposition is WhyAnswerDisposition.ABSTAIN and (
            self.relationship_keys or self.cited_evidence_ids
        ):
            raise WhyEvaluationError("an abstaining why answer cannot make relationship or evidence claims")


@dataclass(frozen=True)
class WhyAnswerExpectation:
    """The deterministic parts of a pre-registered explanation expectation."""

    disposition: WhyAnswerDisposition
    required_relationship_keys: tuple[str, ...] = ()
    required_evidence_ids: tuple[str, ...] = ()
    require_limitations_disclosed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, WhyAnswerDisposition):
            raise WhyEvaluationError("why answer expectation disposition is invalid")
        _sorted_relationship_keys(self.required_relationship_keys, "why answer required_relationship_keys")
        _sorted_identifiers(self.required_evidence_ids, "why answer required_evidence_ids")
        if type(self.require_limitations_disclosed) is not bool:
            raise WhyEvaluationError("why answer expectation require_limitations_disclosed is invalid")
        if self.disposition is WhyAnswerDisposition.ABSTAIN and (
            self.required_relationship_keys or self.required_evidence_ids
        ):
            raise WhyEvaluationError("an abstention expectation cannot require factual claims")
        if self.disposition is WhyAnswerDisposition.ANSWER and not self.required_evidence_ids:
            raise WhyEvaluationError("an answer expectation requires at least one evidence citation")


@dataclass(frozen=True)
class WhyEvaluationCase:
    """A versioned corpus case with no source body or hidden rationale."""

    case_id: str
    question: str
    expectation: WhyAnswerExpectation

    def __post_init__(self) -> None:
        _identifier(self.case_id, "why evaluation case_id")
        _text(self.question, "why evaluation question", maximum=1_000)


@dataclass(frozen=True)
class WhyEvaluationResult:
    """Machine-checkable outcome for one supplied answer and context packet."""

    case_id: str
    passed: bool
    citation_coverage: float
    failures: tuple[WhyEvaluationFailure, ...]

    def __post_init__(self) -> None:
        _identifier(self.case_id, "why evaluation result case_id")
        if type(self.passed) is not bool:
            raise WhyEvaluationError("why evaluation result passed is invalid")
        if not 0.0 <= self.citation_coverage <= 1.0:
            raise WhyEvaluationError("why evaluation result citation_coverage is invalid")
        if not all(isinstance(failure, WhyEvaluationFailure) for failure in self.failures):
            raise WhyEvaluationError("why evaluation result failures are invalid")
        if self.failures != tuple(sorted(set(self.failures), key=lambda item: item.value)):
            raise WhyEvaluationError("why evaluation result failures must be sorted and unique")
        if self.passed != (not self.failures):
            raise WhyEvaluationError("why evaluation result passed must match its failures")


def relationship_key(relationship: DecisionContextRelationship) -> str:
    """Return an unambiguous key for an evidence-backed relationship claim."""

    return "|".join(
        (str(relationship.source_id), relationship.relationship.value, str(relationship.target_id))
    )


def evaluate_why_answer(
    case: WhyEvaluationCase,
    answer: WhyAnswer,
    packet: ContextPacket,
) -> WhyEvaluationResult:
    """Verify an answer against one known-safe context packet and expectation."""

    failures: set[WhyEvaluationFailure] = set()
    if answer.context_version != packet.context_version or answer.context_packet_digest != packet.digest:
        failures.add(WhyEvaluationFailure.CONTEXT_MISMATCH)
    if answer.disposition is not case.expectation.disposition:
        failures.add(WhyEvaluationFailure.WRONG_DISPOSITION)
    if (not packet.qualified or not packet.complete) and answer.disposition is WhyAnswerDisposition.ANSWER:
        failures.add(WhyEvaluationFailure.UNSAFE_CONTEXT_ANSWER)
    available_relationships = {relationship_key(item) for item in packet.relationships}
    available_evidence = {str(item.evidence_id) for item in packet.evidence}
    if not set(answer.relationship_keys).issubset(available_relationships):
        failures.add(WhyEvaluationFailure.UNSUPPORTED_RELATIONSHIP)
    if not set(answer.cited_evidence_ids).issubset(available_evidence):
        failures.add(WhyEvaluationFailure.UNSUPPORTED_EVIDENCE)
    if not set(case.expectation.required_relationship_keys).issubset(answer.relationship_keys):
        failures.add(WhyEvaluationFailure.MISSING_REQUIRED_RELATIONSHIP)
    if not set(case.expectation.required_evidence_ids).issubset(answer.cited_evidence_ids):
        failures.add(WhyEvaluationFailure.MISSING_REQUIRED_EVIDENCE)
    requires_disclosure = case.expectation.require_limitations_disclosed or bool(
        packet.limitations or packet.conflict_ids or packet.omissions
    )
    if requires_disclosure and not answer.limitations_disclosed:
        failures.add(WhyEvaluationFailure.LIMITATIONS_NOT_DISCLOSED)
    required_evidence = set(case.expectation.required_evidence_ids)
    citation_coverage = (
        len(required_evidence.intersection(answer.cited_evidence_ids)) / len(required_evidence)
        if required_evidence
        else 1.0
    )
    ordered_failures = tuple(sorted(failures, key=lambda item: item.value))
    return WhyEvaluationResult(
        case_id=case.case_id,
        passed=not ordered_failures,
        citation_coverage=citation_coverage,
        failures=ordered_failures,
    )


def load_why_evaluation_cases(path: str | Path) -> tuple[WhyEvaluationCase, ...]:
    """Load a reviewed, source-body-free explanation corpus from JSON."""

    try:
        payload: object = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WhyEvaluationError("why evaluation corpus could not be read") from error
    if not isinstance(payload, list):
        raise WhyEvaluationError("why evaluation corpus must be a JSON list")
    cases = tuple(_case_from_payload(item) for item in payload)
    if cases != tuple(sorted(cases, key=lambda item: item.case_id)):
        raise WhyEvaluationError("why evaluation corpus cases must be sorted")
    if len({item.case_id for item in cases}) != len(cases):
        raise WhyEvaluationError("why evaluation corpus case_ids must be unique")
    return cases


def _case_from_payload(value: object) -> WhyEvaluationCase:
    if not isinstance(value, Mapping):
        raise WhyEvaluationError("why evaluation corpus case must be an object")
    expectation = value.get("expectation")
    if not isinstance(expectation, Mapping):
        raise WhyEvaluationError("why evaluation corpus expectation must be an object")
    return WhyEvaluationCase(
        case_id=_required_text(value, "case_id", "why evaluation corpus case"),
        question=_required_text(value, "question", "why evaluation corpus case"),
        expectation=WhyAnswerExpectation(
            disposition=WhyAnswerDisposition(_required_text(expectation, "disposition", "why evaluation expectation")),
            required_relationship_keys=_string_tuple(
                expectation, "required_relationship_keys", "why evaluation expectation"
            ),
            required_evidence_ids=_string_tuple(expectation, "required_evidence_ids", "why evaluation expectation"),
            require_limitations_disclosed=_required_bool(
                expectation, "require_limitations_disclosed", "why evaluation expectation"
            ),
        ),
    )


def _required_text(payload: Mapping[str, object], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise WhyEvaluationError(f"{label}.{field} must be a string")
    return value


def _required_bool(payload: Mapping[str, object], field: str, label: str) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise WhyEvaluationError(f"{label}.{field} must be a boolean")
    return value


def _string_tuple(payload: Mapping[str, object], field: str, label: str) -> tuple[str, ...]:
    value = payload.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise WhyEvaluationError(f"{label}.{field} must be a list of strings")
    return tuple(value)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}", value):
        raise WhyEvaluationError(f"{label} is invalid")
    return value


def _sorted_identifiers(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise WhyEvaluationError(f"{label} must be sorted and unique")
    for value in values:
        _identifier(value, label)


def _sorted_relationship_keys(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise WhyEvaluationError(f"{label} must be sorted and unique")
    for value in values:
        parts = value.split("|")
        if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}", part) for part in parts):
            raise WhyEvaluationError(f"{label} is invalid")


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WhyEvaluationError(f"{label} is invalid")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise WhyEvaluationError(f"{label} is invalid")
    return value
