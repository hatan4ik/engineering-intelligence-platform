from __future__ import annotations

from dataclasses import dataclass

from app.agents.control_loop import ControlLoop, Incident, Phase


@dataclass(frozen=True)
class Scenario:
    name: str
    signal: str
    runbook: str | None
    reversible: bool
    blast_radius: str


SCENARIOS = (
    Scenario("crashloop", "CrashLoopBackOff after config rollout", "rollback-deployment", True, "low"),
    Scenario("oom", "OOMKilled repeatedly", "scale-out", True, "low"),
    Scenario("readiness", "readiness probe failing", "restart-deployment", True, "low"),
    Scenario("node-pressure", "node memory pressure across pool", None, False, "high"),
)


def run(scenario: Scenario, environment: str = "stage") -> list[str]:
    incident = Incident(
        signal=scenario.signal,
        environment=environment,
        service="demo-api",
        blast_radius=scenario.blast_radius,
        reversible=scenario.reversible,
        runbook=scenario.runbook,
    )
    loop = ControlLoop()
    for _ in range(8):
        phase = loop.advance(incident, approved=True, verified=True)
        if phase in {Phase.COMPLETE, Phase.ESCALATE}:
            break
    return [p.value for p in incident.history]


if __name__ == "__main__":
    for scenario in SCENARIOS:
        print(scenario.name, "->", " -> ".join(run(scenario)))
