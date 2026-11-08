from evidence_ai.mat_registry import (
    CAPABILITIES,
    EVIDENCE_FIELDS,
    VERSION,
    selected_capabilities,
    selected_evidence_fields,
)


def test_public_registry_selects_all_evidence_and_capabilities_separately() -> None:
    assert VERSION == "mat-public-v1"
    assert selected_evidence_fields(["all"]) == EVIDENCE_FIELDS
    assert selected_capabilities(["all"]) == CAPABILITIES
    assert {field.id for field in EVIDENCE_FIELDS}.isdisjoint(
        capability.id for capability in CAPABILITIES
    )


def test_public_registry_selects_requested_field_ids() -> None:
    assert [field.id for field in selected_evidence_fields(["ev_src_repo_link"])] == [
        "ev_src_repo_link"
    ]
    assert [capability.id for capability in selected_capabilities(["src_public_repo"])] == [
        "src_public_repo"
    ]
