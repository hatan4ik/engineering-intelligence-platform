from dataclasses import dataclass

@dataclass
class Finding:
    severity: str
    file: str
    message: str
    evidence: str

class PRGuardianAgent:
    """PR review skeleton. AI proposes findings; deterministic policy decides merge gates."""

    def review(self, diff: str, repo_context: str) -> list[Finding]:
        # TODO: combine static analysis, policy results and RAG over standards/incidents.
        return []

    def should_block(self, findings: list[Finding]) -> bool:
        # Keep blocking logic deterministic and policy-driven.
        return any(f.severity.lower() == "critical" for f in findings)
