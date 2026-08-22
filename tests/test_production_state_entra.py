import pytest
from azure.cosmos import exceptions

from app.entra_identity import EntraPrincipalStore, EntraSettings
from app.gateway import GatewayAuthError
from state.cosmos_store import CosmosStateStore
from state.models import ServiceRecord
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
            "tenant", "api://eip",
            ("https://login.microsoftonline.com/tenant/v2.0",),
            "https://example.invalid/keys",
        ),
        key_client=KeyClient(), decode=decode_ok,
    )
    principal = store.authenticate("Bearer token")
    assert principal.subject == "object-id"
    assert principal.groups == ("engineering", "platform")
    assert principal.allowed_model_tiers == ("standard", "advanced")


def test_entra_group_overage_fails_closed():
    def decode_overage(*args, **kwargs):
        return {
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
            "sub": "subject", "exp": 9999999999, "iat": 1,
            "hasgroups": True,
        }
    store = EntraPrincipalStore(
        EntraSettings("tenant", "api://eip", ("https://login.microsoftonline.com/tenant/v2.0",), "unused"),
        key_client=KeyClient(), decode=decode_overage,
    )
    with pytest.raises(GatewayAuthError, match="group overage"):
        store.authenticate("Bearer token")


class FakeContainer:
    def __init__(self):
        self.items = {}
        self.etag = 0

    def read_item(self, item, partition_key):
        if item not in self.items:
            raise exceptions.CosmosResourceNotFoundError(status_code=404, message="missing")
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


def test_cosmos_state_store_preserves_optimistic_version_contract():
    store = CosmosStateStore(FakeContainer())
    created = store.put_service(ServiceRecord(service_id="payments", owner="team-payments"))
    assert created.version == 1
    updated = store.put_service(created, expected_version=1)
    assert updated.version == 2
    assert store.get_service("payments").version == 2
    with pytest.raises(VersionConflict):
        store.put_service(updated, expected_version=1)
