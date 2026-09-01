import pytest
from azure.cosmos import exceptions

from app.entra_identity import EntraPrincipalStore, EntraSettings
from app.gateway import GatewayAuthError
from state.cosmos_store import CosmosStateStore, CosmosStoredStateError
from state.lifecycle import WorkflowLifecycleEvent
from state.models import ServiceRecord, WorkflowStatus
from state.store import VersionConflict


class Key:
    key = "public-key"


class KeyClient:
    def get_signing_key_from_jwt(self, token):
        assert token == "token"
        return Key()


def decode_ok(token, key, **kwargs):
    assert kwargs["audience"] == "api://eip"
    return {
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
        "sub": "subject",
        "oid": "object-id",
        "exp": 9999999999,
        "iat": 1,
        "groups": ["engineering", "platform"],
        "roles": ["EIP.AI.Advanced"],
    }


def test_entra_projects_only_verified_claims():
    store = EntraPrincipalStore(
        EntraSettings(
            "tenant",
            "api://eip",
            ("https://login.microsoftonline.com/tenant/v2.0",),
            "https://example.invalid/keys",
        ),
        key_client=KeyClient(),
        decode=decode_ok,
    )
    principal = store.authenticate("Bearer token")
    assert principal.subject == "object-id"
    assert principal.groups == ("engineering", "platform")
    assert principal.allowed_model_tiers == ("standard", "advanced")


def test_entra_group_overage_fails_closed():
    def decode_overage(*args, **kwargs):
        return {
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
            "sub": "subject",
            "exp": 9999999999,
            "iat": 1,
            "hasgroups": True,
        }

    store = EntraPrincipalStore(
        EntraSettings(
            "tenant",
            "api://eip",
            ("https://login.microsoftonline.com/tenant/v2.0",),
            "unused",
        ),
        key_client=KeyClient(),
        decode=decode_overage,
    )
    with pytest.raises(GatewayAuthError, match="group overage"):
        store.authenticate("Bearer token")


@pytest.mark.parametrize(
    "field,value", [("groups", "engineering"), ("roles", ["EIP.AI.Advanced", 1])]
)
def test_entra_malformed_group_and_role_claims_fail_closed(field, value):
    def decode_bad_claim(*args, **kwargs):
        return {
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
            "sub": "subject",
            "exp": 9999999999,
            "iat": 1,
            field: value,
        }

    store = EntraPrincipalStore(
        EntraSettings(
            "tenant",
            "api://eip",
            ("https://login.microsoftonline.com/tenant/v2.0",),
            "unused",
        ),
        key_client=KeyClient(),
        decode=decode_bad_claim,
    )
    with pytest.raises(GatewayAuthError, match=field):
        store.authenticate("Bearer token")


class FakeContainer:
    def __init__(self):
        self.items = {}
        self.etag = 0

    def read_item(self, item, partition_key):
        if item not in self.items:
            raise exceptions.CosmosResourceNotFoundError(
                status_code=404, message="missing"
            )
        return dict(self.items[item])

    def create_item(self, body):
        self.etag += 1
        stored = dict(body)
        stored["_etag"] = str(self.etag)
        self.items[body["id"]] = stored
        return stored

    def replace_item(self, item, body, *, etag, match_condition):
        assert self.items[item]["_etag"] == etag
        self.etag += 1
        stored = dict(body)
        stored["_etag"] = str(self.etag)
        self.items[item] = stored
        return stored

    def execute_item_batch(self, batch_operations, partition_key):
        staged = dict(self.items)
        next_etag = self.etag
        for operation in batch_operations:
            name, args, *options = operation
            options = options[0] if options else {}
            if name == "create":
                body = args[0]
                assert body["partition_key"] == partition_key
                if body["id"] in staged:
                    raise exceptions.CosmosResourceExistsError(
                        status_code=409, message="exists"
                    )
                next_etag += 1
                staged[body["id"]] = {**body, "_etag": str(next_etag)}
            elif name == "replace":
                item, body = args
                assert body["partition_key"] == partition_key
                if staged[item]["_etag"] != options["if_match_etag"]:
                    raise exceptions.CosmosAccessConditionFailedError(
                        status_code=412, message="stale"
                    )
                next_etag += 1
                staged[item] = {**body, "_etag": str(next_etag)}
            else:
                raise AssertionError(f"unexpected batch operation: {name}")
        self.items = staged
        self.etag = next_etag
        return []


def test_cosmos_state_store_preserves_optimistic_version_contract():
    store = CosmosStateStore(FakeContainer())
    created = store.put_service(
        ServiceRecord(service_id="payments", owner="team-payments")
    )
    assert created.version == 1
    updated = store.put_service(created, expected_version=1)
    assert updated.version == 2
    assert store.get_service("payments").version == 2
    with pytest.raises(VersionConflict):
        store.put_service(updated, expected_version=1)


def test_cosmos_state_store_rejects_corrupt_payloads_without_coercion():
    container = FakeContainer()
    container.items["service:payments"] = {
        "id": "service:payments",
        "partition_key": "service:payments",
        "kind": "service",
        "version": 1,
        "payload": {
            "service_id": "payments",
            "owner": "team-payments",
            "tier": True,
            "repositories": [],
            "dependencies": [],
            "slo_target": None,
            "autonomy_level": 0,
            "metadata": {},
            "version": 1,
        },
        "_etag": "1",
    }

    with pytest.raises(CosmosStoredStateError, match="tier"):
        CosmosStateStore(container).get_service("payments")


def test_cosmos_state_store_atomically_persists_transition_receipt():
    store = CosmosStateStore(FakeContainer())
    event = WorkflowLifecycleEvent(
        event_id="evt-received",
        idempotency_key="idem-received",
        workflow_id="incident:42",
        tenant_id="contoso",
        service_id="payments",
        environment="prod",
        kind="incident-investigation",
        correlation_id="corr-42",
        actor="agent:incident-investigator",
        action="record-lifecycle",
        from_status=None,
        to_status=WorkflowStatus.RECEIVED,
        expected_version=None,
        occurred_at="2026-08-26T12:00:00+00:00",
    )

    first = store.apply_workflow_event(event)
    replay = store.apply_workflow_event(event)

    assert first.record.version == replay.record.version == 1
    assert not first.replayed
    assert replay.replayed
