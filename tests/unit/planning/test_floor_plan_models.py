from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningContextError,
    SpatialConstraint,
    ensure_json_value,
)
from ai_parametric_architect.planning.models import (
    FLOOR_PLAN_SCHEMA_VERSION,
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanBoundary,
    FloorPlanConstraint,
    FloorPlanProposal,
    FloorPlanRoom,
)


def intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "kitchen"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation="adjacent_to",
                target_room_type="living",
                required=True,
            ),
        ),
    )


def room(plan_id: str, room_type: str, target_area: float = 60) -> FloorPlanRoom:
    return FloorPlanRoom(
        plan_id=plan_id,
        room_type=room_type,
        target_area=target_area,
    )


def plan_constraint(
    *,
    source: str = "plan_room_002",
    relation: str = "adjacent_to",
    target: str = "plan_room_001",
    required: bool = True,
) -> FloorPlanConstraint:
    return FloorPlanConstraint(
        source_plan_id=source,
        relation=relation,
        target_plan_id=target,
        required=required,
    )


def proposal(**overrides: object) -> FloorPlanProposal:
    arguments: dict[str, object] = {
        "intent": intent(),
        "rooms": (
            room("plan_room_001", "living"),
            room("plan_room_002", "kitchen"),
        ),
        "spatial_constraints": (plan_constraint(),),
        "orientation": "south",
        "strategy": "equal-area-stable-order-v1",
    }
    arguments.update(overrides)
    return FloorPlanProposal(**cast(Any, arguments))


def placed_room(
    plan_id: str,
    room_type: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    orientation: str,
    target_area: float = 60,
) -> FloorPlanRoom:
    return FloorPlanRoom(
        plan_id=plan_id,
        room_type=room_type,
        target_area=target_area,
        x=x,
        y=y,
        width=width,
        height=height,
        orientation=orientation,
    )


def solved_proposal(**overrides: object) -> FloorPlanProposal:
    arguments: dict[str, object] = {
        "schema_version": SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
        "intent": intent(),
        "rooms": (
            placed_room(
                "plan_room_001",
                "living",
                x=0,
                y=0,
                width=6,
                height=10,
                orientation="west",
            ),
            placed_room(
                "plan_room_002",
                "kitchen",
                x=6,
                y=0,
                width=6,
                height=10,
                orientation="east",
            ),
        ),
        "spatial_constraints": (plan_constraint(),),
        "orientation": "south",
        "strategy": "cp-sat-v1",
        "boundary": FloorPlanBoundary(width=12, height=10),
    }
    arguments.update(overrides)
    return FloorPlanProposal(**cast(Any, arguments))


def test_floor_plan_proposal_has_stable_json_round_trip() -> None:
    value = proposal()

    assert FLOOR_PLAN_SCHEMA_VERSION == "1.0.0"
    assert value.to_dict() == {
        "schema_version": "1.0.0",
        "strategy": "equal-area-stable-order-v1",
        "intent": intent().to_dict(),
        "orientation": "south",
        "rooms": [
            {"plan_id": "plan_room_001", "room_type": "living", "target_area": 60},
            {"plan_id": "plan_room_002", "room_type": "kitchen", "target_area": 60},
        ],
        "spatial_constraints": [
            {
                "source_plan_id": "plan_room_002",
                "relation": "adjacent_to",
                "target_plan_id": "plan_room_001",
                "required": True,
            }
        ],
    }
    assert FloorPlanProposal.from_dict(value.to_dict()) == value
    ensure_json_value(value.to_dict())


def test_solved_floor_plan_proposal_has_stable_json_round_trip() -> None:
    value = solved_proposal()

    assert SOLVED_FLOOR_PLAN_SCHEMA_VERSION == "2.0.0"
    assert value.to_dict() == {
        "schema_version": "2.0.0",
        "strategy": "cp-sat-v1",
        "intent": intent().to_dict(),
        "orientation": "south",
        "rooms": [
            {
                "plan_id": "plan_room_001",
                "room_type": "living",
                "target_area": 60,
                "x": 0,
                "y": 0,
                "width": 6,
                "height": 10,
                "orientation": "west",
            },
            {
                "plan_id": "plan_room_002",
                "room_type": "kitchen",
                "target_area": 60,
                "x": 6,
                "y": 0,
                "width": 6,
                "height": 10,
                "orientation": "east",
            },
        ],
        "spatial_constraints": [
            {
                "source_plan_id": "plan_room_002",
                "relation": "adjacent_to",
                "target_plan_id": "plan_room_001",
                "required": True,
            }
        ],
        "boundary": {"width": 12, "height": 10},
    }
    assert FloorPlanProposal.from_dict(value.to_dict()) == value
    ensure_json_value(value.to_dict())


def test_serialized_plan_is_a_defensive_json_value() -> None:
    value = proposal()
    document = value.to_dict()
    cast(list[dict[str, object]], document["rooms"])[0]["room_type"] = "changed"
    cast(dict[str, object], document["intent"])["area"] = 1

    assert value.rooms[0].room_type == "living"
    assert value.intent.area == 120


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        ({"width": 0, "height": 10}, "/width"),
        ({"width": 10, "height": float("inf")}, "/height"),
        ({"width": float("nan"), "height": 10}, "/width"),
        ({"width": True, "height": 10}, "/width"),
        ({"width": 1e308, "height": 1e308}, "/width"),
    ],
)
def test_floor_plan_boundary_rejects_invalid_values(
    arguments: dict[str, object], path: str
) -> None:
    with pytest.raises(PlanningContextError) as error:
        FloorPlanBoundary(**cast(Any, arguments))

    assert error.value.path == path


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"x": 0}, "/x"),
        (
            {
                "x": float("nan"),
                "y": 0,
                "width": 5,
                "height": 5,
                "orientation": "west",
            },
            "/x",
        ),
        (
            {
                "x": 0,
                "y": 0,
                "width": float("inf"),
                "height": 5,
                "orientation": "west",
            },
            "/width",
        ),
        (
            {
                "x": 0,
                "y": 0,
                "width": 1e308,
                "height": 1e308,
                "orientation": "west",
            },
            "/width",
        ),
        (
            {
                "x": 0,
                "y": 0,
                "width": 5,
                "height": 5,
                "orientation": "up",
            },
            "/orientation",
        ),
    ],
)
def test_floor_plan_room_rejects_partial_or_invalid_placement(
    overrides: dict[str, object], path: str
) -> None:
    arguments: dict[str, object] = {
        "plan_id": "plan_1",
        "room_type": "living",
        "target_area": 25,
    }
    arguments.update(overrides)

    with pytest.raises(PlanningContextError) as error:
        FloorPlanRoom(**cast(Any, arguments))

    assert error.value.path == path


def test_v1_contract_rejects_v2_spatial_fields() -> None:
    with pytest.raises(PlanningContextError) as error:
        proposal(
            rooms=solved_proposal().rooms,
            boundary=FloorPlanBoundary(width=12, height=10),
        )

    assert error.value.path == "/rooms"


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"boundary": None}, "/boundary"),
        (
            {
                "rooms": (
                    room("plan_room_001", "living"),
                    room("plan_room_002", "kitchen"),
                )
            },
            "/rooms",
        ),
        (
            {
                "rooms": (
                    placed_room(
                        "plan_room_001",
                        "living",
                        x=0,
                        y=0,
                        width=6,
                        height=10,
                        orientation="west",
                    ),
                    placed_room(
                        "plan_room_002",
                        "kitchen",
                        x=7,
                        y=0,
                        width=6,
                        height=10,
                        orientation="east",
                    ),
                )
            },
            "/rooms/1",
        ),
        (
            {
                "rooms": (
                    placed_room(
                        "plan_room_001",
                        "living",
                        x=0,
                        y=0,
                        width=7,
                        height=8,
                        orientation="west",
                    ),
                    placed_room(
                        "plan_room_002",
                        "kitchen",
                        x=6,
                        y=0,
                        width=6,
                        height=8,
                        orientation="east",
                    ),
                )
            },
            "/rooms/1",
        ),
        (
            {
                "rooms": (
                    placed_room(
                        "plan_room_001",
                        "living",
                        x=0,
                        y=0,
                        width=6,
                        height=10,
                        orientation="interior",
                    ),
                    solved_proposal().rooms[1],
                )
            },
            "/rooms/0/orientation",
        ),
    ],
)
def test_v2_contract_rejects_missing_or_invalid_geometry(
    overrides: dict[str, object], path: str
) -> None:
    with pytest.raises(PlanningContextError) as error:
        solved_proposal(**overrides)

    assert error.value.path == path


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        ({"plan_id": "Plan 1", "room_type": "living", "target_area": 10}, "/plan_id"),
        ({"plan_id": "plan_1", "room_type": "Living", "target_area": 10}, "/room_type"),
        ({"plan_id": "plan_1", "room_type": "living", "target_area": 0}, "/target_area"),
        (
            {"plan_id": "plan_1", "room_type": "living", "target_area": float("inf")},
            "/target_area",
        ),
        ({"plan_id": "plan_1", "room_type": "living", "target_area": True}, "/target_area"),
        ({"plan_id": "plan_1", "room_type": "living", "target_area": 10**400}, "/target_area"),
    ],
)
def test_floor_plan_room_rejects_invalid_values(arguments: dict[str, object], path: str) -> None:
    with pytest.raises(PlanningContextError) as error:
        FloorPlanRoom(**cast(Any, arguments))

    assert error.value.path == path


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        (
            {
                "source_plan_id": "Plan",
                "relation": "near",
                "target_plan_id": "other",
                "required": True,
            },
            "/source_plan_id",
        ),
        (
            {
                "source_plan_id": "plan_a",
                "relation": "overlaps",
                "target_plan_id": "plan_b",
                "required": True,
            },
            "/relation",
        ),
        (
            {
                "source_plan_id": "plan_a",
                "relation": "near",
                "target_plan_id": "plan_a",
                "required": True,
            },
            "/target_plan_id",
        ),
        (
            {
                "source_plan_id": "plan_a",
                "relation": "near",
                "target_plan_id": "plan_b",
                "required": 1,
            },
            "/required",
        ),
    ],
)
def test_floor_plan_constraint_rejects_invalid_values(
    arguments: dict[str, object], path: str
) -> None:
    with pytest.raises(PlanningContextError) as error:
        FloorPlanConstraint(**cast(Any, arguments))

    assert error.value.path == path


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"schema_version": "3.0.0"}, "/schema_version"),
        ({"intent": {}}, "/intent"),
        ({"strategy": "Equal Area"}, "/strategy"),
        ({"rooms": []}, "/rooms"),
        (
            {
                "rooms": (
                    room("plan_room_001", "living"),
                    room("plan_room_001", "kitchen"),
                )
            },
            "/rooms",
        ),
        (
            {
                "rooms": (
                    room("plan_room_001", "kitchen"),
                    room("plan_room_002", "living"),
                )
            },
            "/rooms",
        ),
        (
            {
                "rooms": (
                    room("plan_room_001", "living", 50),
                    room("plan_room_002", "kitchen", 50),
                )
            },
            "/rooms",
        ),
        ({"orientation": "north"}, "/orientation"),
        ({"spatial_constraints": []}, "/spatial_constraints"),
        (
            {"spatial_constraints": (plan_constraint(), plan_constraint())},
            "/spatial_constraints",
        ),
        (
            {"spatial_constraints": (plan_constraint(source="plan_missing"),)},
            "/spatial_constraints/0",
        ),
        (
            {
                "spatial_constraints": (
                    plan_constraint(source="plan_room_001", target="plan_room_002"),
                )
            },
            "/spatial_constraints/0",
        ),
        (
            {"spatial_constraints": (plan_constraint(relation="near"),)},
            "/spatial_constraints/0",
        ),
    ],
)
def test_floor_plan_proposal_enforces_intent_realization(
    overrides: dict[str, object], path: str
) -> None:
    with pytest.raises(PlanningContextError) as error:
        proposal(**overrides)

    assert error.value.path == path


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            **proposal().to_dict(),
            "extra": True,
        },
        {
            **proposal().to_dict(),
            "intent": [],
        },
        {
            **proposal().to_dict(),
            "rooms": "invalid",
        },
        {
            **proposal().to_dict(),
            "rooms": ["invalid"],
        },
        {
            **proposal().to_dict(),
            "spatial_constraints": "invalid",
        },
        {
            **proposal().to_dict(),
            "spatial_constraints": ["invalid"],
        },
        {
            **proposal().to_dict(),
            "orientation": 1,
        },
        {
            **proposal().to_dict(),
            "strategy": 1,
        },
        {
            **proposal().to_dict(),
            "schema_version": 1,
        },
    ],
)
def test_from_dict_rejects_malformed_plan_documents(payload: dict[str, Any]) -> None:
    with pytest.raises(PlanningContextError):
        FloorPlanProposal.from_dict(payload)


def test_from_dict_rejects_unsupported_schema_version() -> None:
    payload = proposal().to_dict()
    payload["schema_version"] = "3.0.0"

    with pytest.raises(PlanningContextError) as error:
        FloorPlanProposal.from_dict(payload)

    assert error.value.path == "/schema_version"


def test_v1_from_dict_rejects_boundary_and_room_placement_fields() -> None:
    boundary_payload = proposal().to_dict()
    boundary_payload["boundary"] = {"width": 12, "height": 10}
    room_payload = proposal().to_dict()
    cast(list[dict[str, object]], room_payload["rooms"])[0].update(
        {
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 10,
            "orientation": "west",
        }
    )

    with pytest.raises(PlanningContextError):
        FloorPlanProposal.from_dict(boundary_payload)
    with pytest.raises(PlanningContextError) as room_error:
        FloorPlanProposal.from_dict(room_payload)

    assert room_error.value.path == "/rooms/0"


def test_v2_from_dict_requires_exact_boundary_and_room_fields() -> None:
    missing_boundary = solved_proposal().to_dict()
    missing_boundary.pop("boundary")
    malformed_boundary = solved_proposal().to_dict()
    malformed_boundary["boundary"] = []
    partial_room = solved_proposal().to_dict()
    cast(list[dict[str, object]], partial_room["rooms"])[0].pop("orientation")

    with pytest.raises(PlanningContextError):
        FloorPlanProposal.from_dict(missing_boundary)
    with pytest.raises(PlanningContextError) as boundary_error:
        FloorPlanProposal.from_dict(malformed_boundary)
    with pytest.raises(PlanningContextError) as room_error:
        FloorPlanProposal.from_dict(partial_room)

    assert boundary_error.value.path == "/boundary"
    assert room_error.value.path == "/rooms/0"


@pytest.mark.parametrize(
    ("container", "field", "value", "path"),
    [
        ("boundary", "width", float("inf"), "/boundary/width"),
        ("boundary", "height", float("nan"), "/boundary/height"),
        ("room", "x", float("nan"), "/rooms/0/x"),
        ("room", "width", float("inf"), "/rooms/0/width"),
    ],
)
def test_v2_from_dict_rejects_nonfinite_geometry(
    container: str, field: str, value: float, path: str
) -> None:
    payload = solved_proposal().to_dict()
    if container == "boundary":
        cast(dict[str, object], payload["boundary"])[field] = value
    else:
        cast(list[dict[str, object]], payload["rooms"])[0][field] = value

    with pytest.raises(PlanningContextError) as error:
        FloorPlanProposal.from_dict(payload)

    assert error.value.path == path


def test_nested_from_dict_errors_have_full_paths() -> None:
    invalid_room = proposal().to_dict()
    cast(list[dict[str, object]], invalid_room["rooms"])[0]["target_area"] = 0
    invalid_constraint = proposal().to_dict()
    cast(list[dict[str, object]], invalid_constraint["spatial_constraints"])[0]["relation"] = (
        "invalid"
    )
    invalid_intent = proposal().to_dict()
    cast(dict[str, object], invalid_intent["intent"])["building_type"] = "House"

    with pytest.raises(PlanningContextError) as room_error:
        FloorPlanProposal.from_dict(invalid_room)
    with pytest.raises(PlanningContextError) as constraint_error:
        FloorPlanProposal.from_dict(invalid_constraint)
    with pytest.raises(PlanningContextError) as intent_error:
        FloorPlanProposal.from_dict(invalid_intent)

    assert room_error.value.path == "/rooms/0/target_area"
    assert constraint_error.value.path == "/spatial_constraints/0/relation"
    assert intent_error.value.path == "/intent/building_type"


def test_leaf_from_dict_methods_are_strict() -> None:
    with pytest.raises(PlanningContextError):
        FloorPlanRoom.from_dict({})
    with pytest.raises(PlanningContextError):
        FloorPlanRoom.from_dict({"plan_id": 1, "room_type": "living", "target_area": 10})
    with pytest.raises(PlanningContextError):
        FloorPlanRoom.from_dict({"plan_id": "plan_1", "room_type": 1, "target_area": 10})
    with pytest.raises(PlanningContextError):
        FloorPlanRoom.from_dict({"plan_id": "plan_1", "room_type": "living", "target_area": "10"})
    with pytest.raises(PlanningContextError):
        FloorPlanConstraint.from_dict({})
    for field in ("source_plan_id", "relation", "target_plan_id", "required"):
        value = plan_constraint().to_dict()
        value[field] = 1
        with pytest.raises(PlanningContextError):
            FloorPlanConstraint.from_dict(value)
