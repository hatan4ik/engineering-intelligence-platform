from __future__ import annotations


from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.policy import ActionRequest, ServiceAutonomy


class _MockK8sAdapter:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.verified: list[str] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.executed.append(runbook_id)
        return f"exec-{runbook_id}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        self.verified.append(signal)
        return True

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        return f"rollback-{rollback_id}"


def test_onprem_disaster_recovery_runbooks_registered_in_default_catalog() -> None:
    catalog = default_catalog()

    # etcd defragmentation and alarm clearance
    etcd_rb = catalog.get("k8s.etcd.defrag_and_alarm_clear")
    assert etcd_rb.required_level == AutonomyLevel.APPROVE_AND_EXECUTE
    assert etcd_rb.reversible is True
    assert etcd_rb.verify_signal == "etcd.alarm_absent"
    assert "etcd.member_healthy" in etcd_rb.preconditions

    # Admission webhook bypass
    webhook_rb = catalog.get("k8s.webhook.bypass_deadlock")
    assert webhook_rb.required_level == AutonomyLevel.APPROVE_AND_EXECUTE
    assert webhook_rb.reversible is True
    assert webhook_rb.verify_signal == "apiserver.admission_healthy"
    assert "webhook.failing_closed" in webhook_rb.preconditions

    # CoreDNS query storm autopath
    dns_rb = catalog.get("k8s.coredns.autopath_scale")
    assert dns_rb.required_level == AutonomyLevel.APPROVE_AND_EXECUTE
    assert dns_rb.reversible is True
    assert dns_rb.verify_signal == "dns.query_latency_normal"

    # Safe node drain under PDBs
    drain_rb = catalog.get("k8s.node.drain_with_pdb_eviction")
    assert drain_rb.required_level == AutonomyLevel.APPROVE_AND_EXECUTE
    assert drain_rb.reversible is True
    assert drain_rb.verify_signal == "node.unschedulable_and_empty"


def test_execute_control_loop_executes_etcd_disaster_recovery() -> None:
    catalog = default_catalog()
    policy = ServiceAutonomy("control-plane", "prod", AutonomyLevel.APPROVE_AND_EXECUTE, ("k8s.etcd.defrag_and_alarm_clear",), 1)
    request = ActionRequest("control-plane", "prod", "k8s.etcd.defrag_and_alarm_clear", blast_radius=1)
    adapter = _MockK8sAdapter()

    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=adapter,
        approval_verified=True,
    )

    assert result.status == "succeeded"
    assert result.verified is True
    assert "k8s.etcd.defrag_and_alarm_clear" in adapter.executed
    assert "etcd.alarm_absent" in adapter.verified


def test_execute_control_loop_executes_webhook_deadlock_bypass() -> None:
    catalog = default_catalog()
    policy = ServiceAutonomy("apiserver", "prod", AutonomyLevel.APPROVE_AND_EXECUTE, ("k8s.webhook.bypass_deadlock",), 5)
    request = ActionRequest("apiserver", "prod", "k8s.webhook.bypass_deadlock", blast_radius=1)
    adapter = _MockK8sAdapter()

    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=adapter,
        approval_verified=True,
    )

    assert result.status == "succeeded"
    assert result.verified is True
    assert "k8s.webhook.bypass_deadlock" in adapter.executed
    assert "apiserver.admission_healthy" in adapter.verified
