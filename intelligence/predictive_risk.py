from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalChange:
    service: str
    risk_score: int
    failed: bool
    touched_iac: bool = False
    touched_security: bool = False
    blast_radius: int = 1


@dataclass(frozen=True)
class PredictiveRisk:
    probability: float
    confidence: float
    evidence: tuple[str, ...]


def predict_failure_probability(
    *,
    service: str,
    current_risk_score: int,
    touched_iac: bool,
    touched_security: bool,
    blast_radius: int,
    history: list[HistoricalChange],
) -> PredictiveRisk:
    comparable = [h for h in history if h.service == service]
    if not comparable:
        baseline = min(0.65, 0.05 + current_risk_score / 200.0)
        return PredictiveRisk(round(baseline, 3), 0.25, ("no service-specific historical calibration available",))

    weighted_failures = 0.0
    weight_total = 0.0
    evidence: list[str] = []
    for item in comparable:
        similarity = 1.0
        similarity += 0.5 if item.touched_iac == touched_iac else 0.0
        similarity += 0.5 if item.touched_security == touched_security else 0.0
        similarity += max(0.0, 1.0 - abs(item.blast_radius - blast_radius) / 10.0)
        similarity += max(0.0, 1.0 - abs(item.risk_score - current_risk_score) / 100.0)
        weight_total += similarity
        weighted_failures += similarity if item.failed else 0.0
    empirical = weighted_failures / weight_total if weight_total else 0.0
    prior = min(0.9, current_risk_score / 100.0)
    probability = 0.7 * empirical + 0.3 * prior
    confidence = min(0.95, 0.35 + 0.08 * len(comparable))
    evidence.append(f"{len(comparable)} historical changes calibrated for service {service}")
    evidence.append(f"weighted historical failure rate {empirical:.2f}")
    return PredictiveRisk(round(probability, 3), round(confidence, 3), tuple(evidence))
