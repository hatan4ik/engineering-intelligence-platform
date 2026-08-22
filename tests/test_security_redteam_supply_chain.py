from security.redteam import acl_isolation_resisted, confused_deputy_resisted, run_content_corpus
from supply_chain.provenance import build_sbom, issue_provenance, verify_admission


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


def test_provenance_admission_fails_closed_on_tampering():
    sbom = build_sbom(())
    provenance = issue_provenance(
        subject=b"image-bytes",
        sbom=sbom,
        builder="github-actions/eip",
        source_revision="abc123",
    )
    allowed, _ = verify_admission(
        subject=b"image-bytes",
        sbom=sbom,
        provenance=provenance,
        trusted_builders=("github-actions/eip",),
        expected_revision="abc123",
    )
    assert allowed

    allowed, reason = verify_admission(
        subject=b"tampered-image",
        sbom=sbom,
        provenance=provenance,
        trusted_builders=("github-actions/eip",),
        expected_revision="abc123",
    )
    assert not allowed
    assert reason == "subject digest mismatch"
