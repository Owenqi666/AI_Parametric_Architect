from __future__ import annotations

import json
from typing import Any

import pytest

from ai_parametric_architect.application import EditingService, PatchedModelValidationError
from ai_parametric_architect.composition import create_editing_service
from ai_parametric_architect.domain import (
    AffectedEntitiesMismatchError,
    AuditActorType,
    InvalidPatchError,
    NonJsonValueError,
    PatchModelMismatchError,
    PatchOperation,
    PatchProposal,
    RevisionConflictError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.repositories import InMemoryRevisionRepository

AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="editing-pipeline-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:editing-pipeline-test",
)


def proposal(
    *operations: PatchOperation,
    base_model_id: str = "mdl_simple_house",
    base_revision: int = 0,
    rationale: str = "Apply tested design edit.",
    affected_entity_ids: tuple[str, ...] = (),
) -> PatchProposal:
    return PatchProposal(
        base_model_id=base_model_id,
        base_revision=base_revision,
        operations=operations,
        provenance="integration-test",
        rationale=rationale,
        affected_entity_ids=affected_entity_ids,
    )


def initialized_service(model: dict[str, Any]) -> EditingService:
    service = create_editing_service()
    service.initialize(
        model,
        provenance="fixture:valid_simple_house",
        rationale="Create the initial revision.",
        audit_identity=AUDIT_IDENTITY,
    )
    return service


def test_successful_patch_creates_valid_new_revision_and_audit(
    valid_simple_house: dict[str, Any],
) -> None:
    source_revision = valid_simple_house["revision"]
    service = initialized_service(valid_simple_house)

    created = service.apply_patch(
        "mdl_simple_house",
        proposal(
            PatchOperation(
                "replace",
                "/metadata/description",
                "Updated through deterministic JSON Patch.",
            )
        ),
        audit_identity=AUDIT_IDENTITY,
    )

    assert valid_simple_house["revision"] == source_revision
    assert created.revision_number == 1
    assert created.parent_revision == 0
    assert created.document["revision"] == 1
    assert created.document["metadata"]["description"].startswith("Updated")
    assert service.current("mdl_simple_house").revision_number == 1
    assert [entry.action.value for entry in service.audit_log("mdl_simple_house")] == [
        "initialize",
        "patch",
    ]
    json.dumps(created.to_dict(), allow_nan=False)


def test_invalid_patch_is_rejected_without_revision(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    with pytest.raises(InvalidPatchError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(PatchOperation("remove", "/metadata/missing")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details["reason"] == "TARGET_NOT_FOUND"
    assert service.current("mdl_simple_house").revision_number == 0
    assert len(service.audit_log("mdl_simple_house")) == 1


def test_shared_python_container_cannot_create_multi_path_patch_side_effect(
    valid_simple_house: dict[str, Any],
) -> None:
    shared = {"tag": "old"}
    valid_simple_house["metadata"]["shared"] = shared
    valid_simple_house["entities"]["rooms"]["rom_living"]["metadata"] = shared
    service = create_editing_service()

    with pytest.raises(NonJsonValueError) as error:
        service.initialize(
            valid_simple_house,
            provenance="python-api-test",
            rationale="Reject graph aliases before they enter JSON history.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details["reason"] == "SHARED_REFERENCE"


def test_revision_conflict_rejects_stale_proposal(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)
    service.apply_patch(
        "mdl_simple_house",
        proposal(PatchOperation("replace", "/metadata/description", "First edit.")),
        audit_identity=AUDIT_IDENTITY,
    )

    with pytest.raises(RevisionConflictError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(PatchOperation("replace", "/metadata/description", "Stale edit.")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details == {
        "model_id": "mdl_simple_house",
        "expected": 0,
        "actual": 1,
    }
    assert service.current("mdl_simple_house").document["metadata"]["description"] == "First edit."
    assert len(service.audit_log("mdl_simple_house")) == 2


def test_patch_proposal_cannot_be_replayed_against_another_model_at_same_revision(
    valid_simple_house: dict[str, Any],
) -> None:
    repository = InMemoryRevisionRepository()
    service = create_editing_service(repository)
    service.initialize(
        valid_simple_house,
        provenance="fixture:model-a",
        rationale="Initialize model A.",
        audit_identity=AUDIT_IDENTITY,
    )
    other = json.loads(json.dumps(valid_simple_house))
    other["model_id"] = "mdl_other_house"
    service.initialize(
        other,
        provenance="fixture:model-b",
        rationale="Initialize model B.",
        audit_identity=AUDIT_IDENTITY,
    )

    with pytest.raises(PatchModelMismatchError):
        service.apply_patch(
            "mdl_other_house",
            proposal(PatchOperation("replace", "/metadata/description", "Wrong model.")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert service.current("mdl_simple_house").revision_number == 0
    assert service.current("mdl_other_house").revision_number == 0
    assert len(service.audit_log("mdl_other_house")) == 1


def test_declared_affected_entities_must_equal_the_validated_entity_delta(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    with pytest.raises(AffectedEntitiesMismatchError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(
                PatchOperation("replace", "/entities/rooms/rom_living/name", "Lounge"),
                affected_entity_ids=("wal_south",),
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.code == "PATCH_AFFECTED_ENTITIES_MISMATCH"
    assert error.value.details == {
        "actual": ["wal_south"],
        "expected": ["rom_living"],
    }
    assert service.current("mdl_simple_house").revision_number == 0
    assert len(service.audit_log("mdl_simple_house")) == 1


def test_verified_affected_entities_are_recorded_in_canonical_order(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    created = service.apply_patch(
        "mdl_simple_house",
        proposal(
            PatchOperation("replace", "/entities/rooms/rom_living/name", "Lounge"),
            affected_entity_ids=("rom_living",),
        ),
        audit_identity=AUDIT_IDENTITY,
    )

    assert created.document["entities"]["rooms"]["rom_living"]["name"] == "Lounge"
    assert service.audit_log("mdl_simple_house")[-1].details["affected_entity_ids"] == [
        "rom_living"
    ]


def test_schema_broken_patch_is_rejected_without_commit(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    with pytest.raises(PatchedModelValidationError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(PatchOperation("remove", "/units")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert {issue.code for issue in error.value.report.issues} == {"SCHEMA_REQUIRED"}
    assert service.current("mdl_simple_house").revision_number == 0
    assert len(service.audit_log("mdl_simple_house")) == 1


def test_patch_cannot_relax_geometry_precision_policy(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    with pytest.raises(InvalidPatchError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(
                PatchOperation(
                    "replace",
                    "/geometry_settings/linear_tolerance",
                    0.01,
                ),
                PatchOperation(
                    "replace",
                    "/entities/doors/dor_entry/center_offset",
                    8.009,
                ),
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.code == "PATCH_PATH_PROTECTED"
    assert error.value.details["protected_member"] == "geometry_settings"
    assert service.current("mdl_simple_house").revision_number == 0


def test_geometry_broken_patch_is_rejected_without_commit(
    valid_simple_house: dict[str, Any],
) -> None:
    service = initialized_service(valid_simple_house)

    with pytest.raises(PatchedModelValidationError) as error:
        service.apply_patch(
            "mdl_simple_house",
            proposal(
                PatchOperation(
                    "replace",
                    "/entities/walls/wal_south/axis/end",
                    [0.0, 0.0],
                )
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert "WALL_ZERO_LENGTH" in {issue.code for issue in error.value.report.issues}
    assert service.current("mdl_simple_house").document["entities"]["walls"]["wal_south"]["axis"][
        "end"
    ] == [8.0, 0.0]
    assert len(service.audit_log("mdl_simple_house")) == 1


def test_real_pipeline_undo_redo_preserves_json_truth_and_monotonic_history(
    valid_simple_house: dict[str, Any],
) -> None:
    repository = InMemoryRevisionRepository()
    service = create_editing_service(repository)
    service.initialize(
        valid_simple_house,
        provenance="fixture",
        rationale="Initialize.",
        audit_identity=AUDIT_IDENTITY,
    )
    service.apply_patch(
        "mdl_simple_house",
        proposal(PatchOperation("replace", "/metadata/description", "Edited.")),
        audit_identity=AUDIT_IDENTITY,
    )

    undone = service.undo(
        "mdl_simple_house",
        expected_revision=1,
        provenance="integration-test",
        rationale="Undo the metadata edit.",
        audit_identity=AUDIT_IDENTITY,
    )
    redone = service.redo(
        "mdl_simple_house",
        expected_revision=2,
        provenance="integration-test",
        rationale="Redo the metadata edit.",
        audit_identity=AUDIT_IDENTITY,
    )

    assert undone.revision_number == 2
    assert undone.document["metadata"]["description"].startswith("One-room")
    assert redone.revision_number == 3
    assert redone.document["metadata"]["description"] == "Edited."
    assert [
        service.revision("mdl_simple_house", number).revision_number for number in range(4)
    ] == [
        0,
        1,
        2,
        3,
    ]
