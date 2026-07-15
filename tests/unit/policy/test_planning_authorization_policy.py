from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlannerContractError,
    PlanningRecord,
    RoomAssignment,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy


def _intent(*, area: int = 60) -> DesignIntent:
    return DesignIntent(building_type="house", area=area, rooms=("bedroom",))


def _record(intent: DesignIntent) -> PlanningRecord:
    return PlanningRecord(
        intent=intent,
        assignments=(RoomAssignment("rom_a", "bedroom", "Bedroom 1"),),
        unverified_constraints=("area", "building_type"),
    )


def _revision(*, realized: bool = False) -> ModelRevision:
    intent = _intent()
    room: dict[str, object] = {
        "id": "rom_a",
        "entity_type": "room",
        "name": "Bedroom 1" if realized else "Room A",
    }
    document: dict[str, object] = {
        "schema_version": "1.0.0",
        "model_id": "mdl_house",
        "revision": 4,
        "entities": {"rooms": {"rom_a": room}},
        "extensions": {},
    }
    if realized:
        room["usage"] = "bedroom"
        document["extensions"] = {PLANNING_EXTENSION_KEY: _record(intent).to_dict()}
    return ModelRevision(
        model_id="mdl_house",
        revision_number=4,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        parent_revision=3,
        document=document,
    )


def _proposal(
    *,
    intent: DesignIntent | None = None,
    operations: tuple[PatchOperation, ...] | None = None,
    affected_entity_ids: tuple[str, ...] = ("rom_a",),
) -> PatchProposal:
    record = _record(_intent() if intent is None else intent)
    canonical_operations = (
        PatchOperation("add", "/entities/rooms/rom_a/usage", "bedroom"),
        PatchOperation("replace", "/entities/rooms/rom_a/name", "Bedroom 1"),
        PatchOperation(
            "add",
            f"/extensions/{PLANNING_EXTENSION_KEY}",
            record.to_dict(),
        ),
    )
    return PatchProposal(
        base_model_id="mdl_house",
        base_revision=4,
        operations=canonical_operations if operations is None else operations,
        provenance="planner:test-v1",
        rationale="Realize the authorized room semantics.",
        affected_entity_ids=affected_entity_ids,
    )


def test_exact_planning_proposal_is_authorized_without_mutation() -> None:
    policy = ArchitecturePlanningAuthorizationPolicy()
    revision = _revision()
    proposal = _proposal()
    before = revision.document

    authorized = policy.authorize(_intent(), revision, proposal)

    assert authorized is proposal
    assert revision.document == before


def test_intent_mismatch_is_not_authorized() -> None:
    policy = ArchitecturePlanningAuthorizationPolicy()

    with pytest.raises(PlannerContractError) as error:
        policy.authorize(_intent(), _revision(), _proposal(intent=_intent(area=90)))

    assert error.value.path == "/planning_record/intent"


def test_unowned_geometry_operation_is_not_authorized() -> None:
    policy = ArchitecturePlanningAuthorizationPolicy()
    malicious = _proposal(
        operations=(
            PatchOperation(
                "replace",
                "/entities/rooms/rom_a/geometry",
                {"exterior": []},
            ),
            PatchOperation(
                "add",
                f"/extensions/{PLANNING_EXTENSION_KEY}",
                _record(_intent()).to_dict(),
            ),
        )
    )

    with pytest.raises(PlannerContractError):
        policy.authorize(_intent(), _revision(), malicious)


def test_affected_entities_must_equal_the_owned_assignments() -> None:
    policy = ArchitecturePlanningAuthorizationPolicy()

    with pytest.raises(PlannerContractError) as error:
        policy.authorize(
            _intent(),
            _revision(),
            _proposal(affected_entity_ids=("rom_other",)),
        )

    assert error.value.path == "/affected_entity_ids"


def test_verified_no_change_requires_an_exact_existing_realization() -> None:
    ArchitecturePlanningAuthorizationPolicy().require_no_change(
        _intent(),
        _revision(realized=True),
    )


def test_false_no_change_is_not_authorized() -> None:
    with pytest.raises(PlannerContractError) as error:
        ArchitecturePlanningAuthorizationPolicy().require_no_change(
            _intent(),
            _revision(),
        )

    assert error.value.details == {"reason": "MISSING_PLANNING_RECORD"}
