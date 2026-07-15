from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import pytest

import ai_parametric_architect.composition as composition
from ai_parametric_architect.agents import ArchitecturePlannerAgent
from ai_parametric_architect.composition import (
    create_architecture_planner_agent,
    create_editing_service,
    create_planning_service,
    create_requirement_agent,
)
from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    AuditActorType,
    DesignIntent,
    PlanningRecord,
    SpatialConstraint,
    TrustedAuditIdentity,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.planning import (
    CP_SAT_STRATEGY,
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanProposal,
    RuleBasedFloorPlanPlanner,
    RuleBasedPlanner,
)
from ai_parametric_architect.validation import ModelValidator

_WORLD_OR_REVISION_FIELDS = frozenset(
    {
        "base_revision",
        "created_at",
        "entities",
        "geometry",
        "geometry_settings",
        "model_id",
        "parent_revision",
        "revision",
        "revision_number",
        "root_building_id",
    }
)
AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="architecture-pipeline-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:architecture-pipeline-test",
)
PLANNING_IDENTITY = TrustedAuditIdentity(
    actor_id="architecture-planner-agent",
    actor_type=AuditActorType.AGENT,
    agent_version="test-v1",
    trace_id="trace:architecture-planning-test",
)


class RecordingFloorPlanPlanner:
    def __init__(self) -> None:
        self.intents: list[DesignIntent] = []

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        self.intents.append(intent)
        return RuleBasedFloorPlanPlanner().plan(intent)


def test_requirement_and_architecture_agents_create_a_deterministic_detached_plan() -> None:
    requirement_agent = create_requirement_agent()
    planner_agent = create_architecture_planner_agent()
    requirement = "Create a 120 sqm three bedroom house"

    intent = requirement_agent.run(requirement)
    first = planner_agent.run(intent)
    second = planner_agent.run(requirement_agent.run(requirement))

    assert isinstance(planner_agent, ArchitecturePlannerAgent)
    assert isinstance(first, FloorPlanProposal)
    assert first == second
    assert first.strategy == CP_SAT_STRATEGY
    assert first.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
    assert first.boundary is not None
    assert [room.plan_id for room in first.rooms] == [
        "plan_room_001",
        "plan_room_002",
        "plan_room_003",
    ]
    assert [room.room_type for room in first.rooms] == ["bedroom"] * 3
    assert math.fsum(room.target_area for room in first.rooms) == intent.area
    assert all(
        room.is_placed
        and room.x is not None
        and room.y is not None
        and room.width is not None
        and room.height is not None
        and room.width > 0
        and room.height > 0
        for room in first.rooms
    )
    assert first.orientation is None
    assert first.spatial_constraints == ()
    assert json.dumps(first.to_dict(), sort_keys=True, allow_nan=False) == json.dumps(
        second.to_dict(), sort_keys=True, allow_nan=False
    )
    assert _all_mapping_keys(first.to_dict()).isdisjoint(_WORLD_OR_REVISION_FIELDS)


def test_composed_planning_service_routes_plan_ir_through_patch_validation_and_commit(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = create_editing_service()
    editing.initialize(
        valid_simple_house,
        provenance="fixture:task-3-integration",
        rationale="Initialize the validated deterministic model.",
        audit_identity=AUDIT_IDENTITY,
    )
    requirement = "设计一个60平方米一室住宅"
    intent = create_requirement_agent().run(requirement)
    floor_plan = create_architecture_planner_agent().run(intent)
    current = editing.current("mdl_simple_house")
    geometry_before = deepcopy(current.document["entities"]["rooms"]["rom_living"]["geometry"])
    expected_proposal = RuleBasedPlanner().plan_from_floor_plan(floor_plan, current)

    service = create_planning_service(editing, audit_identity=PLANNING_IDENTITY)
    proposed = service.propose("mdl_simple_house", requirement)

    assert proposed.intent == intent
    assert proposed.base_revision == current
    assert proposed.proposal is not None
    assert expected_proposal is not None
    assert proposed.proposal.to_dict() == expected_proposal.to_dict()
    assert all("geometry" not in operation.path for operation in proposed.proposal.operations)
    assert editing.current("mdl_simple_house") == current

    committed = service.plan_and_commit("mdl_simple_house", requirement)

    assert committed.changed
    assert committed.base_revision.revision_number == 0
    assert committed.revision.revision_number == 1
    assert committed.revision.parent_revision == 0
    assert ModelValidator(ShapelyGeometryEngine()).validate(committed.revision.document).valid
    assert (
        committed.revision.document["entities"]["rooms"]["rom_living"]["geometry"]
        == geometry_before
    )
    record = PlanningRecord.from_dict(
        committed.revision.document["extensions"][PLANNING_EXTENSION_KEY]
    )
    assert record.intent == intent
    assert [entry.action.value for entry in editing.audit_log("mdl_simple_house")] == [
        "initialize",
        "patch",
    ]


def test_composition_invokes_the_architecture_planner_agent(
    valid_simple_house: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editing = create_editing_service()
    editing.initialize(
        valid_simple_house,
        provenance="fixture:task-3-agent-spy",
        rationale="Initialize a valid model for composition verification.",
        audit_identity=AUDIT_IDENTITY,
    )
    recording_planner = RecordingFloorPlanPlanner()
    planner_agent = ArchitecturePlannerAgent(recording_planner)
    monkeypatch.setattr(
        composition,
        "create_architecture_planner_agent",
        lambda: planner_agent,
    )

    composition.create_planning_service(
        editing,
        audit_identity=PLANNING_IDENTITY,
    ).propose(
        "mdl_simple_house",
        "Create a 60 sqm one bedroom house",
    )

    assert len(recording_planner.intents) == 1
    assert recording_planner.intents[0].rooms == ("bedroom",)


def test_repeated_rooms_and_spatial_plan_survive_the_safe_commit_trace(
    valid_simple_house: dict[str, Any],
) -> None:
    _replace_with_four_room_slots(valid_simple_house)
    editing = create_editing_service()
    editing.initialize(
        valid_simple_house,
        provenance="fixture:task-3-spatial-plan",
        rationale="Initialize four deterministic room slots.",
        audit_identity=AUDIT_IDENTITY,
    )
    intent = DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "bedroom", "bedroom", "kitchen"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation="adjacent_to",
                target_room_type="living",
            ),
        ),
    )
    floor_plan = create_architecture_planner_agent().run(intent)
    current = editing.current("mdl_simple_house")
    proposal = RuleBasedPlanner().plan_from_floor_plan(floor_plan, current)

    assert proposal is not None
    committed = editing.apply_patch(
        "mdl_simple_house",
        proposal,
        audit_identity=AUDIT_IDENTITY,
    )
    record = PlanningRecord.from_dict(committed.document["extensions"][PLANNING_EXTENSION_KEY])

    assert record.intent == intent
    assert [assignment.usage for assignment in record.assignments] == [
        "living",
        "bedroom",
        "bedroom",
        "kitchen",
    ]
    assert record.unverified_constraints == (
        "area",
        "building_type",
        "orientation",
        "spatial_constraints",
    )
    assert ModelValidator(ShapelyGeometryEngine()).validate(committed.document).valid


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return set(value).union(
            *(_all_mapping_keys(member) for member in value.values()),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return set().union(*(_all_mapping_keys(member) for member in value))
    return set()


def _replace_with_four_room_slots(model: dict[str, Any]) -> None:
    rooms: dict[str, object] = {}
    for index, (start, end) in enumerate(
        ((0.1, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 7.9)),
        start=1,
    ):
        room_id = f"rom_slot_{index}"
        rooms[room_id] = {
            "id": room_id,
            "entity_type": "room",
            "name": f"Room Slot {index}",
            "floor_id": "flr_ground",
            "geometry": {
                "type": "Polygon2D",
                "exterior": [
                    [start, 0.1],
                    [end, 0.1],
                    [end, 5.9],
                    [start, 5.9],
                    [start, 0.1],
                ],
                "holes": [],
            },
        }
    model["entities"]["rooms"] = rooms
