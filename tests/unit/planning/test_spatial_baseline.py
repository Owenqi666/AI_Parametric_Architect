from __future__ import annotations

import ast
import json
import math
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningContextError,
    SpatialConstraint,
)
from ai_parametric_architect.planning import (
    EQUAL_AREA_STABLE_ORDER_STRATEGY,
    FLOOR_PLAN_SCHEMA_VERSION,
    RULE_BASED_SPATIAL_STRATEGY,
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    RuleBasedFloorPlanPlanner,
    RuleBasedSpatialFloorPlanPlanner,
    RuleBasedSpatialPolicy,
)

SPATIAL_BASELINE_SOURCE = (
    Path(__file__).parents[3]
    / "src"
    / "ai_parametric_architect"
    / "planning"
    / "spatial_baseline.py"
)


def _intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=80,
        rooms=("living", "bedroom", "bedroom", "kitchen"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="bedroom",
                relation="near",
                target_room_type="kitchen",
            ),
        ),
    )


def test_legacy_rule_planner_remains_byte_stable_semantic_v1() -> None:
    intent = DesignIntent(building_type="house", area=60, rooms=("bedroom",))

    proposal = RuleBasedFloorPlanPlanner().plan(intent)
    encoded = json.dumps(
        proposal.to_dict(),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert encoded == (
        '{"intent":{"area":60,"building_type":"house","orientation":null,'
        '"rooms":["bedroom"]},"orientation":null,"rooms":[{"plan_id":'
        '"plan_room_001","room_type":"bedroom","target_area":60}],'
        '"schema_version":"1.0.0","spatial_constraints":[],"strategy":'
        '"equal-area-stable-order-v1"}'
    )
    assert proposal.schema_version == FLOOR_PLAN_SCHEMA_VERSION
    assert proposal.strategy == EQUAL_AREA_STABLE_ORDER_STRATEGY
    assert proposal.boundary is None
    assert all(not room.is_placed for room in proposal.rooms)


def test_spatial_baseline_is_deterministic_complete_and_detached() -> None:
    intent = _intent()
    before = deepcopy(intent.to_dict())
    planner = RuleBasedSpatialFloorPlanPlanner()

    first = planner.plan(intent)
    second = planner.plan(intent)

    assert first == second
    assert intent.to_dict() == before
    assert first.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
    assert first.strategy == RULE_BASED_SPATIAL_STRATEGY
    assert first.boundary is not None
    assert first.orientation == intent.orientation
    assert [room.plan_id for room in first.rooms] == [
        "plan_room_001",
        "plan_room_002",
        "plan_room_003",
        "plan_room_004",
    ]
    assert all(
        room.is_placed
        and room.y == 0.0
        and room.height == first.boundary.height
        and room.orientation == "south"
        for room in first.rooms
    )
    assert math.fsum(cast(float, room.actual_area) for room in first.rooms) <= intent.area
    assert set(first.to_dict()).isdisjoint(
        {"entities", "geometry", "model_id", "revision", "root_building_id"}
    )


def test_spatial_baseline_strip_is_non_overlapping_and_binds_first_occurrence() -> None:
    proposal = RuleBasedSpatialFloorPlanPlanner().plan(_intent())
    assert proposal.boundary is not None

    for index, room in enumerate(proposal.rooms):
        assert room.x is not None
        assert room.width is not None
        if index == 0:
            assert room.x == 0.0
        else:
            previous = proposal.rooms[index - 1]
            assert previous.x is not None
            assert previous.width is not None
            assert room.x == previous.x + previous.width
        assert room.x + room.width <= proposal.boundary.width

    for left_index, left in enumerate(proposal.rooms):
        assert left.x is not None
        assert left.width is not None
        for right in proposal.rooms[left_index + 1 :]:
            assert right.x is not None
            assert right.width is not None
            assert left.x + left.width <= right.x or right.x + right.width <= left.x

    assert [constraint.to_dict() for constraint in proposal.spatial_constraints] == [
        {
            "source_plan_id": "plan_room_002",
            "relation": "near",
            "target_plan_id": "plan_room_004",
            "required": True,
        }
    ]


@pytest.mark.parametrize(
    ("policy", "intent", "path", "reason"),
    [
        (
            RuleBasedSpatialPolicy(max_rooms=1),
            DesignIntent(building_type="house", area=20, rooms=("living", "kitchen")),
            "/intent/rooms",
            "ROOM_BUDGET_EXCEEDED",
        ),
        (
            RuleBasedSpatialPolicy(max_area=19),
            DesignIntent(building_type="house", area=20, rooms=("living",)),
            "/intent/area",
            "AREA_BUDGET_EXCEEDED",
        ),
        (
            RuleBasedSpatialPolicy(max_strip_length=1),
            DesignIntent(building_type="house", area=20, rooms=("living",)),
            "/policy/max_strip_length",
            "STRIP_LENGTH_BUDGET_EXCEEDED",
        ),
    ],
)
def test_spatial_baseline_fails_closed_on_resource_budgets(
    policy: RuleBasedSpatialPolicy,
    intent: DesignIntent,
    path: str,
    reason: str,
) -> None:
    with pytest.raises(PlanningContextError) as captured:
        RuleBasedSpatialFloorPlanPlanner(policy).plan(intent)

    assert captured.value.path == path
    assert captured.value.details["reason"] == reason


@pytest.mark.parametrize(
    ("kwargs", "path"),
    [
        ({"version": "2.0.0"}, "/policy/version"),
        ({"strip_depth": 0}, "/policy/strip_depth"),
        ({"max_rooms": True}, "/policy/max_rooms"),
        ({"max_area": math.inf}, "/policy/max_area"),
        ({"max_strip_length": 10_001}, "/policy/max_strip_length"),
    ],
)
def test_spatial_policy_rejects_invalid_or_unbounded_values(
    kwargs: dict[str, object],
    path: str,
) -> None:
    with pytest.raises(PlanningContextError) as captured:
        RuleBasedSpatialPolicy(**cast(Any, kwargs))

    assert captured.value.path == path


def test_spatial_policy_is_frozen() -> None:
    policy = RuleBasedSpatialPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.max_rooms = 2  # type: ignore[misc]


def test_spatial_baseline_has_no_solver_or_ortools_dependency() -> None:
    tree = ast.parse(
        SPATIAL_BASELINE_SOURCE.read_text(encoding="utf-8"),
        filename=str(SPATIAL_BASELINE_SOURCE),
    )
    imports = {imported for node in ast.walk(tree) for imported in _imported_modules(node)}

    assert "ortools" not in imports
    assert "ai_parametric_architect.planning.solver" not in imports


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()
