from app.agents.control_loop import ControlLoop, Incident, Phase


def drive(incident: Incident, approved: bool = True, verified: bool = True) -> Phase:
    loop = ControlLoop()
    phase = Phase.DETECT
    for _ in range(8):
        phase = loop.advance(incident, approved=approved, verified=verified)
        if phase in {Phase.COMPLETE, Phase.ESCALATE}:
            return phase
    return phase


def test_low_risk_stage_auto_executes():
    incident = Incident("CrashLoopBackOff", "stage", "api", runbook="rollback-deployment")
    assert drive(incident) == Phase.COMPLETE
    assert Phase.APPROVE not in incident.history


def test_prod_requires_approval():
    incident = Incident("CrashLoopBackOff", "prod", "api", runbook="rollback-deployment")
    assert drive(incident, approved=False) == Phase.ESCALATE
    assert Phase.APPROVE in incident.history


def test_high_blast_radius_escalates():
    incident = Incident("node pressure", "stage", "api", blast_radius="high", reversible=False)
    assert drive(incident) == Phase.ESCALATE
