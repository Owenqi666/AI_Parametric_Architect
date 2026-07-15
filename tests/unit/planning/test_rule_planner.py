from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, cast

import pytest

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    ModelRevision,
    PlanningCapacityError,
    PlanningContextError,
    PlanningRecord,
    RoomAssignment,
    SpatialConstraint,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.planning import (
    ConstraintFloorPlanPlanner,
    FloorPlanProposal,
    RuleBasedFloorPlanPlanner,
)
from ai_parametric_architect.planning.rule_planner import (
    RULE_BASED_PLANNER_PROVENANCE,
    RULE_BASED_PLANNER_RATIONALE,
    RuleBasedPlanner,
)

_MISSING: Final = object()


class RecordingFloorPlanPlanner:
    def __init__(self) -> None:
        self.intents: list[DesignIntent] = []
        self.proposals: list[FloorPlanProposal] = []

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        self.intents.append(intent)
        proposal = RuleBasedFloorPlanPlanner().plan(intent)
        self.proposals.append(proposal)
        return proposal


class MalformedFloorPlanPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        return cast(FloorPlanProposal, {"intent": intent.to_dict()})


def _room(
    room_id: str,
    *,
    name: str = "Unassigned",
    usage: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": room_id,
        "entity_type": "room",
        "name": name,
        "geometry": {
            "boundary": [[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]],
        },
    }
    if usage is not None:
        value["usage"] = usage
    return value


def _revision(
    rooms: Mapping[str, object],
    *,
    extensions: object = _MISSING,
    revision_number: int = 7,
) -> ModelRevision:
    document: dict[str, Any] = {
        "model_id": "mdl_planning",
        "revision": revision_number,
        "entities": {"rooms": dict(rooms)},
    }
    if extensions is not _MISSING:
        document["extensions"] = extensions
    return ModelRevision(
        model_id="mdl_planning",
        revision_number=revision_number,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_revision=revision_number - 1 if revision_number else None,
        document=document,
    )


def _intent(
    *rooms: str,
    orientation: str | None = None,
) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=120,
        rooms=rooms,
        orientation=orientation,
    )


def _planning_record(
    intent: DesignIntent,
    assignments: tuple[RoomAssignment, ...],
) -> PlanningRecord:
    constraints: tuple[str, ...] = ("area", "building_type")
    if intent.orientation is not None:
        constraints = (*constraints, "orientation")
    return PlanningRecord(
        intent=intent,
        assignments=assignments,
        unverified_constraints=constraints,
    )


def test_plan_produces_exact_deterministic_semantic_patch_and_trace() -> None:
    revision = _revision(
        {
            "rom_c": _room("rom_c"),
            "rom_a": _room("rom_a"),
            "rom_b": _room("rom_b"),
        },
        revision_number=11,
    )
    intent = _intent("bedroom", "bedroom", orientation="south")
    before = revision.document

    proposal = RuleBasedPlanner().plan(intent, revision)

    assert proposal is not None
    record = _planning_record(
        intent,
        (
            RoomAssignment("rom_a", "bedroom", "Bedroom 1"),
            RoomAssignment("rom_b", "bedroom", "Bedroom 2"),
        ),
    )
    assert proposal.to_dict() == {
        "base_model_id": "mdl_planning",
        "base_revision": 11,
        "operations": [
            {"op": "add", "path": "/entities/rooms/rom_a/usage", "value": "bedroom"},
            {
                "op": "replace",
                "path": "/entities/rooms/rom_a/name",
                "value": "Bedroom 1",
            },
            {"op": "add", "path": "/entities/rooms/rom_b/usage", "value": "bedroom"},
            {
                "op": "replace",
                "path": "/entities/rooms/rom_b/name",
                "value": "Bedroom 2",
            },
            {
                "op": "add",
                "path": "/extensions",
                "value": {PLANNING_EXTENSION_KEY: record.to_dict()},
            },
        ],
        "provenance": RULE_BASED_PLANNER_PROVENANCE,
        "rationale": RULE_BASED_PLANNER_RATIONALE,
        "affected_entity_ids": ["rom_a", "rom_b"],
    }
    assert proposal.provenance == "planner:rule-based-v1"
    assert proposal.rationale == (
        "Assign requested room semantics and record unverified design constraints."
    )
    assert all("geometry" not in operation.path for operation in proposal.operations)
    assert revision.document == before

    applied = cast(dict[str, Any], JsonPatchEngine().apply(before, proposal.operations))
    before_rooms = cast(dict[str, Any], cast(dict[str, Any], before["entities"])["rooms"])
    after_rooms = cast(dict[str, Any], cast(dict[str, Any], applied["entities"])["rooms"])
    for room_id in before_rooms:
        assert after_rooms[room_id]["geometry"] == before_rooms[room_id]["geometry"]


def test_solved_spatial_proposal_generates_semantic_only_patch() -> None:
    revision = _revision(
        {"rom_a": _room("rom_a"), "rom_b": _room("rom_b")},
        revision_number=3,
    )
    intent = _intent("living", "bedroom", orientation="south")
    solved_plan = ConstraintFloorPlanPlanner().plan(intent)
    before = revision.document

    proposal = RuleBasedPlanner().plan_from_floor_plan(solved_plan, revision)

    assert proposal is not None
    allowed_paths = {
        "/entities/rooms/rom_a/usage",
        "/entities/rooms/rom_a/name",
        "/entities/rooms/rom_b/usage",
        "/entities/rooms/rom_b/name",
        "/extensions",
    }
    assert {operation.path for operation in proposal.operations} <= allowed_paths
    assert all("geometry" not in operation.path for operation in proposal.operations)
    applied = cast(dict[str, Any], JsonPatchEngine().apply(before, proposal.operations))
    assert (
        applied["entities"]["rooms"]["rom_a"]["geometry"]
        == before["entities"]["rooms"]["rom_a"]["geometry"]
    )
    assert (
        applied["entities"]["rooms"]["rom_b"]["geometry"]
        == before["entities"]["rooms"]["rom_b"]["geometry"]
    )
    record = PlanningRecord.from_dict(applied["extensions"][PLANNING_EXTENSION_KEY])
    assert record.unverified_constraints == ("area", "building_type", "orientation")
    assert revision.document == before


def test_plan_is_independent_of_room_registry_insertion_order() -> None:
    ascending = {
        "rom_a": _room("rom_a"),
        "rom_b": _room("rom_b"),
        "rom_c": _room("rom_c"),
    }
    descending = dict(reversed(tuple(ascending.items())))
    planner = RuleBasedPlanner()
    intent = _intent("living", "kitchen")

    first = planner.plan(intent, _revision(ascending))
    second = planner.plan(intent, _revision(descending))

    assert first is not None
    assert second is not None
    assert first.to_dict() == second.to_dict()


def test_plan_routes_through_injected_floor_plan_ir_before_patch_generation() -> None:
    intent = _intent("living", "kitchen", orientation="south")
    revision = _revision({"rom_a": _room("rom_a"), "rom_b": _room("rom_b")})
    floor_plan_planner = RecordingFloorPlanPlanner()
    planner = RuleBasedPlanner(floor_plan_planner=floor_plan_planner)

    proposal = planner.plan(intent, revision)

    assert proposal is not None
    assert floor_plan_planner.intents == [intent]
    assert floor_plan_planner.intents[0] is intent
    assert len(floor_plan_planner.proposals) == 1
    floor_plan = floor_plan_planner.proposals[0]
    assert [room.room_type for room in floor_plan.rooms] == ["living", "kitchen"]
    assert planner.plan_from_floor_plan(floor_plan, revision) == proposal


def test_malformed_injected_floor_plan_is_rejected_before_model_patch_planning() -> None:
    revision = _revision({"rom_a": _room("rom_a")})
    before = revision.document

    with pytest.raises(PlanningContextError) as captured:
        RuleBasedPlanner(MalformedFloorPlanPlanner()).plan(_intent("living"), revision)

    assert captured.value.path == "/floor_plan"
    assert captured.value.details == {"reason": "INVALID_FLOOR_PLAN_OUTPUT"}
    assert revision.document == before


def test_existing_extensions_are_preserved_and_only_changed_room_fields_are_patched() -> None:
    sibling_extension = {"vendor.example": {"keep": [1, 2, 3]}}
    revision = _revision(
        {"rom_a": _room("rom_a", name="Living Room", usage="storage")},
        extensions=sibling_extension,
    )
    intent = _intent("living")

    proposal = RuleBasedPlanner().plan(intent, revision)

    assert proposal is not None
    assert [operation.to_dict() for operation in proposal.operations] == [
        {
            "op": "replace",
            "path": "/entities/rooms/rom_a/usage",
            "value": "living",
        },
        {
            "op": "add",
            "path": f"/extensions/{PLANNING_EXTENSION_KEY}",
            "value": _planning_record(
                intent,
                (RoomAssignment("rom_a", "living", "Living Room"),),
            ).to_dict(),
        },
    ]
    applied = cast(
        dict[str, Any],
        JsonPatchEngine().apply(revision.document, proposal.operations),
    )
    extensions = cast(dict[str, Any], applied["extensions"])
    assert extensions["vendor.example"] == {"keep": [1, 2, 3]}
    assert PLANNING_EXTENSION_KEY in extensions


def test_existing_planning_record_is_replaced_without_overwriting_siblings() -> None:
    old_intent = _intent("study")
    old_record = _planning_record(
        old_intent,
        (RoomAssignment("rom_a", "study", "Study"),),
    )
    revision = _revision(
        {"rom_a": _room("rom_a", name="Study", usage="study")},
        extensions={
            PLANNING_EXTENSION_KEY: old_record.to_dict(),
            "vendor.example": {"keep": True},
        },
    )
    intent = _intent("kitchen")

    proposal = RuleBasedPlanner().plan(intent, revision)

    assert proposal is not None
    assert proposal.operations[-1].to_dict() == {
        "op": "replace",
        "path": f"/extensions/{PLANNING_EXTENSION_KEY}",
        "value": _planning_record(
            intent,
            (RoomAssignment("rom_a", "kitchen", "Kitchen"),),
        ).to_dict(),
    }
    applied = cast(
        dict[str, Any],
        JsonPatchEngine().apply(revision.document, proposal.operations),
    )
    assert cast(dict[str, Any], applied["extensions"])["vendor.example"] == {"keep": True}


@pytest.mark.parametrize(
    ("orientation", "expected_constraints"),
    [
        (None, ["area", "building_type"]),
        ("south", ["area", "building_type", "orientation"]),
    ],
)
def test_trace_only_records_requested_orientation_as_unverified(
    orientation: str | None,
    expected_constraints: list[str],
) -> None:
    proposal = RuleBasedPlanner().plan(
        _intent("study", orientation=orientation),
        _revision({"rom_a": _room("rom_a")}),
    )

    assert proposal is not None
    extension_value = cast(dict[str, Any], proposal.operations[-1].value)
    record = cast(dict[str, Any], extension_value[PLANNING_EXTENSION_KEY])
    realization = cast(dict[str, Any], record["realization"])
    assert realization["unverified_constraints"] == expected_constraints


def test_trace_explicitly_marks_spatial_constraints_as_unverified() -> None:
    intent = DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "kitchen"),
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation="adjacent_to",
                target_room_type="living",
            ),
        ),
    )

    proposal = RuleBasedPlanner().plan(
        intent,
        _revision({"rom_a": _room("rom_a"), "rom_b": _room("rom_b")}),
    )

    assert proposal is not None
    extension_value = cast(dict[str, Any], proposal.operations[-1].value)
    record = cast(dict[str, Any], extension_value[PLANNING_EXTENSION_KEY])
    realization = cast(dict[str, Any], record["realization"])
    assert realization["unverified_constraints"] == [
        "area",
        "building_type",
        "spatial_constraints",
    ]


def test_canonical_fallback_names_and_duplicate_ordinals_are_stable() -> None:
    proposal = RuleBasedPlanner().plan(
        _intent("guest_room", "guest_room"),
        _revision({"rom_b": _room("rom_b"), "rom_a": _room("rom_a")}),
    )

    assert proposal is not None
    assert [
        operation.value for operation in proposal.operations if operation.path.endswith("/name")
    ] == ["Guest Room 1", "Guest Room 2"]


def test_plan_returns_none_when_rooms_and_trace_already_match() -> None:
    intent = _intent("living", "bedroom")
    record = _planning_record(
        intent,
        (
            RoomAssignment("rom_a", "living", "Living Room"),
            RoomAssignment("rom_b", "bedroom", "Bedroom"),
        ),
    )
    revision = _revision(
        {
            "rom_b": _room("rom_b", name="Bedroom", usage="bedroom"),
            "rom_a": _room("rom_a", name="Living Room", usage="living"),
        },
        extensions={PLANNING_EXTENSION_KEY: record.to_dict()},
    )
    before = revision.document

    assert RuleBasedPlanner().plan(intent, revision) is None
    assert revision.document == before


def test_insufficient_capacity_is_rejected_without_mutating_revision() -> None:
    revision = _revision({"rom_a": _room("rom_a")})
    before = revision.document

    with pytest.raises(PlanningCapacityError) as raised:
        RuleBasedPlanner().plan(_intent("living", "kitchen"), revision)

    assert raised.value.path == "/entities/rooms"
    assert raised.value.details == {
        "reason": "INSUFFICIENT_ROOM_SLOTS",
        "requested": 2,
        "available": 1,
    }
    assert revision.document == before


@pytest.mark.parametrize(
    "fragment",
    [
        {},
        {"entities": []},
        {"entities": {}},
        {"entities": {"rooms": []}},
        {"entities": {"rooms": {"rom_a": 1}}},
        {"entities": {"rooms": {"rom_a": {"id": "rom_b", "entity_type": "room", "name": "Room"}}}},
        {"entities": {"rooms": {"rom_a": {"id": "rom_a", "entity_type": "wall", "name": "Room"}}}},
        {"entities": {"rooms": {"rom_a": {"id": "rom_a", "entity_type": "room", "name": " "}}}},
        {
            "entities": {
                "rooms": {
                    "rom_a": {
                        "id": "rom_a",
                        "entity_type": "room",
                        "name": "Room",
                        "usage": "",
                    }
                }
            }
        },
        {"entities": {"rooms": {"rom_a": _room("rom_a")}}, "extensions": []},
        {
            "entities": {"rooms": {"rom_a": _room("rom_a")}},
            "extensions": {PLANNING_EXTENSION_KEY: {"schema_version": "invalid"}},
        },
    ],
)
def test_malformed_context_is_rejected_atomically(fragment: dict[str, object]) -> None:
    document: dict[str, Any] = {
        "model_id": "mdl_planning",
        "revision": 7,
        **fragment,
    }
    revision = ModelRevision(
        model_id="mdl_planning",
        revision_number=7,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_revision=6,
        document=document,
    )
    before = revision.document

    with pytest.raises(PlanningContextError):
        RuleBasedPlanner().plan(_intent("living"), revision)

    assert revision.document == before


def test_invalid_runtime_inputs_are_reported_as_context_errors() -> None:
    planner = RuleBasedPlanner()
    revision = _revision({"rom_a": _room("rom_a")})

    with pytest.raises(PlanningContextError, match="DesignIntent"):
        planner.plan(cast(Any, {}), revision)
    with pytest.raises(PlanningContextError, match="ModelRevision"):
        planner.plan(_intent("living"), cast(Any, {}))
    with pytest.raises(PlanningContextError) as captured:
        planner.plan_from_floor_plan(cast(Any, {}), revision)
    assert captured.value.path == "/floor_plan"
    assert captured.value.details == {"reason": "INVALID_FLOOR_PLAN_TYPE"}
    floor_plan = RuleBasedFloorPlanPlanner().plan(_intent("living"))
    with pytest.raises(PlanningContextError, match="ModelRevision"):
        planner.plan_from_floor_plan(floor_plan, cast(Any, {}))
