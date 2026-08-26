from security.redteam import acl_isolation_resisted, confused_deputy_resisted, run_content_corpus
from supply_chain.provenance import Component, verify_image_sbom


def test_default_redteam_corpus_passes():
    result = run_content_corpus()
    assert result.success
    assert result.failures == ()


def test_confused_deputy_cannot_expand_tool_permissions():
    assert confused_deputy_resisted(
        requested_tool="kubectl.exec",
        principal_tools=("rag.search", "github.comment"),
    )


def test_acl_isolation_denies_nonmember_principal():
    assert acl_isolation_resisted(
        principal_groups=("engineering",),
        document_groups=("security-admins",),
    )


def test_image_sbom_verification_fails_closed_when_a_direct_pin_is_missing():
    sbom = {
        "bomFormat": "CycloneDX",
        "metadata": {"component": {"type": "container", "name": "eip", "version": "ci"}},
        "components": [{"name": "fastapi", "version": "0.116.1"}],
    }

    allowed, failures = verify_image_sbom(
        sbom=sbom,
        required_components=(
            Component(name="fastapi", version="0.116.1"),
            Component(name="pydantic", version="2.11.7"),
        ),
        image_reference="eip:ci",
    )

    assert not allowed
    assert failures == ("direct dependency missing from image SBOM: pydantic==2.11.7",)


def test_image_sbom_verification_rejects_a_different_image_tag():
    sbom = {
        "bomFormat": "CycloneDX",
        "metadata": {"component": {"type": "container", "name": "eip", "version": "other"}},
        "components": [{"name": "fastapi", "version": "0.116.1"}],
    }

    allowed, failures = verify_image_sbom(
        sbom=sbom,
        required_components=(Component(name="fastapi", version="0.116.1"),),
        image_reference="eip:ci",
    )

    assert not allowed
    assert failures == ("SBOM container tag does not match the built image",)
