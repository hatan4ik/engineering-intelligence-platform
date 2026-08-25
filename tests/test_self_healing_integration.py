from datetime import datetime, timedelta, timezone

from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from product.self_healing_service import SelfHealingService
from remediation.catalog import AutonomyLevel, default_catalog
from remediation.policy import ServiceAutonomy


class Adapter:
    def __init__(self, verify=True):
        self.verify_result = verify
        self.calls = []

    def execute(self, runbook_id, request):
        self.calls.append(("execute", runbook_id))
        return "exec-1"

    def verify(self, signal, request):
        self.calls.append(("verify", signal))
        return self.verify_result

    def rollback(self, rollback_id, request):
        self.calls.append(("rollback", rollback_id))
        return "rollback-1"


def incident():
    deployed = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    return analyze_incident([
        EvidenceEvent("deploy-1", EvidenceKind.DEPLOYMENT, "payments", deployed, "release v2", "ado", 1),
        EvidenceEvent("alert-1", EvidenceKind.ALERT, "payments", deployed + timedelta(minutes=4), "readiness failures", "azure-monitor", 4),
    ], service="payments")


def policy(level=AutonomyLevel.APPROVE_AND_EXECUTE):
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=level,
        certified_runbooks=("aks.rollout.undo", "aks.rollback.readiness", "aks.restart.workload"),
        max_blast_radius=5,
    )


def test_l3_self_healing_requires_approval():
    service = SelfHealingService(catalog=default_catalog(), policy=policy(), adapter=Adapter(), sandbox_adapter=Adapter())
    result = service.handle_incident(incident(), blast_radius=2, approval_token=None)
    assert result.status == "simulation-blocked"
    assert result.simulation is not None
    assert result.simulation.execution.status == "denied"


def test_l3_simulates_then_executes_certified_runbook():
    prod = Adapter()
    sandbox = Adapter()
    service = SelfHealingService(catalog=default_catalog(), policy=policy(), adapter=prod, sandbox_adapter=sandbox)
    result = service.handle_incident(incident(), blast_radius=2, approval_token="approved:plan", approval_verified=True)
    assert result.status == "succeeded"
    assert result.plan.runbook_id == "aks.rollback.readiness"
    assert sandbox.calls[0] == ("execute", "aks.rollback.readiness")
    assert prod.calls[0] == ("execute", "aks.rollback.readiness")


def test_failed_production_verification_rolls_back():
    prod = Adapter(verify=False)
    service = SelfHealingService(catalog=default_catalog(), policy=policy(), adapter=prod, sandbox_adapter=Adapter())
    result = service.handle_incident(incident(), blast_radius=2, approval_token="approved:plan", approval_verified=True)
    assert result.status == "rolled_back"
    assert result.execution.rollback_ref == "rollback-1"


def test_missing_sandbox_blocks_when_simulation_required():
    service = SelfHealingService(catalog=default_catalog(), policy=policy(), adapter=Adapter())
    result = service.handle_incident(incident(), blast_radius=2, approval_token="approved:plan")
    assert result.status == "simulation-required"
