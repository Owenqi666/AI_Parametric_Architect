from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from ai_parametric_architect.application import EditingService, PatchedModelValidationError
from ai_parametric_architect.composition import create_editing_service, create_planning_service
from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    AuditActorType,
    PatchOperation,
    PatchProposal,
    PlanningCapacityError,
    PlanningRecord,
    RevisionConflictError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.validation import ModelValidator

AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="planning-pipeline-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:planning-pipeline-test",
)
PLANNING_IDENTITY = TrustedAuditIdentity(
    actor_id="architecture-planning-service",
    actor_type=AuditActorType.AGENT,
    agent_version="rule-based-v1",
    trace_id="trace:planning-agent-test",
)


def _with_three_room_slots(model: dict[str, Any]) -> dict[str, Any]:
    source = model["entities"]["rooms"]["rom_living"]
    definitions = (
        ("rom_c", [[5.3, 0.1], [7.9, 0.1], [7.9, 5.9], [5.3, 5.9], [5.3, 0.1]]),
        ("rom_a", [[0.1, 0.1], [2.6, 0.1], [2.6, 5.9], [0.1, 5.9], [0.1, 0.1]]),
        ("rom_b", [[2.7, 0.1], [5.2, 0.1], [5.2, 5.9], [2.7, 5.9], [2.7, 0.1]]),
    )
    rooms: dict[str, Any] = {}
    for room_id, exterior in definitions:
        room = copy.deepcopy(source)
        room["id"] = room_id
        room["name"] = f"Unassigned {room_id}"
        room.pop("usage", None)
        room["geometry"]["exterior"] = exterior
        rooms[room_id] = room
    model["entities"]["rooms"] = rooms
    return model


def _initialize(model: dict[str, Any]) -> EditingService:
    editing = create_editing_service()
    editing.initialize(
        model,
        provenance="fixture:planning-house",
        rationale="Initialize a validated room-slot model.",
        audit_identity=AUDIT_IDENTITY,
    )
    return editing


def test_natural_language_proposal_is_validated_and_committed_without_geometry_changes(
    valid_simple_house: dict[str, Any],
) -> None:
    model = _with_three_room_slots(valid_simple_house)
    editing = _initialize(model)
    planning = create_planning_service(editing, audit_identity=PLANNING_IDENTITY)
    before = editing.current("mdl_simple_house").document
    before_room_geometry = {
        room_id: copy.deepcopy(room["geometry"])
        for room_id, room in before["entities"]["rooms"].items()
    }
    before_other_entities = {
        registry: copy.deepcopy(values)
        for registry, values in before["entities"].items()
        if registry != "rooms"
    }

    proposed = planning.propose("mdl_simple_house", "设计一个120平方米三室住宅")

    assert proposed.intent.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom", "bedroom", "bedroom"],
        "orientation": None,
    }
    assert proposed.proposal is not None
    assert all("geometry" not in operation.path for operation in proposed.proposal.operations)
    assert editing.current("mdl_simple_house").document == before

    committed = planning.plan_and_commit("mdl_simple_house", "设计一个120平方米三室住宅")

    assert committed.changed
    assert committed.base_revision.revision_number == 0
    assert committed.revision.revision_number == 1
    assert committed.proposal is not None
    assert committed.proposal.to_dict() == proposed.proposal.to_dict()
    document = committed.revision.document
    rooms = document["entities"]["rooms"]
    assert [
        (room_id, rooms[room_id]["usage"], rooms[room_id]["name"]) for room_id in sorted(rooms)
    ] == [
        ("rom_a", "bedroom", "Bedroom 1"),
        ("rom_b", "bedroom", "Bedroom 2"),
        ("rom_c", "bedroom", "Bedroom 3"),
    ]
    assert {room_id: room["geometry"] for room_id, room in rooms.items()} == before_room_geometry
    assert {
        registry: values for registry, values in document["entities"].items() if registry != "rooms"
    } == before_other_entities

    record = PlanningRecord.from_dict(document["extensions"][PLANNING_EXTENSION_KEY])
    assert record.intent == committed.intent
    assert record.unverified_constraints == ("area", "building_type")
    assert ModelValidator(ShapelyGeometryEngine()).validate(document).valid
    json.dumps(document, allow_nan=False)
    assert [entry.action.value for entry in editing.audit_log("mdl_simple_house")] == [
        "initialize",
        "patch",
    ]
    assert editing.audit_log("mdl_simple_house")[-1].provenance == "planner:rule-based-v1"

    repeated = planning.plan_and_commit("mdl_simple_house", "设计一个120平方米三室住宅")

    assert repeated.no_change
    assert repeated.revision.revision_number == 1
    assert len(editing.audit_log("mdl_simple_house")) == 2


def test_insufficient_room_slots_reject_the_whole_plan_without_history_changes(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialize(valid_simple_house)
    planning = create_planning_service(editing, audit_identity=PLANNING_IDENTITY)
    before = editing.current("mdl_simple_house").document

    with pytest.raises(PlanningCapacityError):
        planning.plan_and_commit("mdl_simple_house", "设计一个120平方米三室住宅")

    assert editing.current("mdl_simple_house").document == before
    assert len(editing.audit_log("mdl_simple_house")) == 1


def test_general_patch_cannot_desynchronize_a_committed_planning_record(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialize(valid_simple_house)
    planning = create_planning_service(editing, audit_identity=PLANNING_IDENTITY)
    committed = planning.plan_and_commit(
        "mdl_simple_house",
        "设计一个120平方米一室住宅",
    )

    with pytest.raises(PatchedModelValidationError) as error:
        editing.apply_patch(
            "mdl_simple_house",
            PatchProposal(
                base_model_id="mdl_simple_house",
                base_revision=committed.revision.revision_number,
                operations=(
                    PatchOperation(
                        "replace",
                        "/entities/rooms/rom_living/usage",
                        "living",
                    ),
                ),
                provenance="source:manual-test",
                rationale="Attempt to create a stale planning trace.",
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert {issue.code for issue in error.value.report.issues} == {"PLANNING_ASSIGNMENT_MISMATCH"}
    assert editing.current("mdl_simple_house").revision_number == 1


def test_stale_planning_proposal_keeps_existing_revision_conflict_semantics(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialize(valid_simple_house)
    planning = create_planning_service(editing, audit_identity=PLANNING_IDENTITY)
    planned = planning.propose("mdl_simple_house", "设计一个120平方米一室住宅")
    assert planned.proposal is not None
    editing.apply_patch(
        "mdl_simple_house",
        PatchProposal(
            base_model_id="mdl_simple_house",
            base_revision=0,
            operations=(PatchOperation("replace", "/metadata/description", "Concurrent edit."),),
            provenance="source:manual-test",
            rationale="Advance the model before applying the plan.",
        ),
        audit_identity=AUDIT_IDENTITY,
    )

    with pytest.raises(RevisionConflictError):
        editing.apply_patch(
            "mdl_simple_house",
            planned.proposal,
            audit_identity=AUDIT_IDENTITY,
        )

    assert editing.current("mdl_simple_house").revision_number == 1
