from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningContextError,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.planning.rules import (
    EQUAL_AREA_STABLE_ORDER_STRATEGY,
    RuleBasedFloorPlanPlanner,
)


def _intent(
    *,
    area: float = 100.0,
    rooms: tuple[str, ...] = ("living", "bedroom", "bedroom"),
    orientation: str | None = "south",
    constraints: tuple[SpatialConstraint, ...] = (),
) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=area,
        rooms=rooms,
        orientation=orientation,
        spatial_constraints=constraints,
    )


def test_plan_allocates_stable_ids_types_orientation_and_strategy() -> None:
    intent = _intent()

    proposal = RuleBasedFloorPlanPlanner().plan(intent)

    assert proposal.intent is intent
    assert [room.plan_id for room in proposal.rooms] == [
        "plan_room_001",
        "plan_room_002",
        "plan_room_003",
    ]
    assert [room.room_type for room in proposal.rooms] == [
        "living",
        "bedroom",
        "bedroom",
    ]
    assert proposal.orientation == "south"
    assert proposal.strategy == EQUAL_AREA_STABLE_ORDER_STRATEGY
    assert proposal.spatial_constraints == ()


@pytest.mark.parametrize(
    ("area", "room_count"),
    [
        (1.0, 3),
        (100.0, 3),
        (0.1, 7),
        (123.456789, 64),
        (float.fromhex("0x1.0p-1020"), 4),
        (float.fromhex("0x1.fffffffffffffp+1023"), 13),
        (float.fromhex("0x1.fffffffffffffp+1023"), 31),
        (float.fromhex("0x1.fffffffffffffp+1023"), 64),
    ],
)
def test_equal_area_allocation_preserves_first_shares_and_exact_total(
    area: float,
    room_count: int,
) -> None:
    intent = _intent(area=area, rooms=("room",) * room_count)

    target_areas = tuple(
        room.target_area for room in RuleBasedFloorPlanPlanner().plan(intent).rooms
    )

    assert target_areas[:-1] == (area / room_count,) * (room_count - 1)
    assert all(math.isfinite(value) and value > 0.0 for value in target_areas)
    assert math.fsum(target_areas) == intent.area


def test_single_room_keeps_the_exact_intent_area_and_null_orientation() -> None:
    intent = _intent(area=17.25, rooms=("studio",), orientation=None)

    proposal = RuleBasedFloorPlanPlanner().plan(intent)

    assert proposal.rooms[0].target_area == intent.area
    assert proposal.orientation is None


def test_constraints_bind_to_first_room_of_each_type_in_canonical_order() -> None:
    constraints = (
        SpatialConstraint(
            source_room_type="living",
            relation=SpatialRelation.NEAR,
            target_room_type="bedroom",
            required=False,
        ),
        SpatialConstraint(
            source_room_type="bedroom",
            relation=SpatialRelation.ADJACENT_TO,
            target_room_type="kitchen",
        ),
    )
    intent = _intent(
        rooms=("living", "bedroom", "bedroom", "kitchen"),
        constraints=constraints,
    )

    proposal = RuleBasedFloorPlanPlanner().plan(intent)

    assert [constraint.source_plan_id for constraint in proposal.spatial_constraints] == [
        "plan_room_002",
        "plan_room_001",
    ]
    assert [constraint.target_plan_id for constraint in proposal.spatial_constraints] == [
        "plan_room_004",
        "plan_room_002",
    ]
    assert [constraint.relation for constraint in proposal.spatial_constraints] == [
        value.relation for value in intent.spatial_constraints
    ]
    assert [constraint.required for constraint in proposal.spatial_constraints] == [
        value.required for value in intent.spatial_constraints
    ]


def test_repeated_planning_is_value_deterministic_and_does_not_mutate_intent() -> None:
    intent = _intent()
    before = intent.to_dict()
    planner = RuleBasedFloorPlanPlanner()

    first = planner.plan(intent)
    second = planner.plan(intent)

    assert isinstance(first, FloorPlanProposal)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert intent.to_dict() == before


def test_underflowing_equal_share_is_rejected_with_structured_context() -> None:
    smallest_positive_float = float.fromhex("0x0.0000000000001p-1022")
    intent = _intent(
        area=smallest_positive_float,
        rooms=("bedroom", "bedroom"),
    )

    with pytest.raises(PlanningContextError) as captured:
        RuleBasedFloorPlanPlanner().plan(intent)

    assert captured.value.path == "/intent/area"
    assert captured.value.details == {
        "reason": "NON_POSITIVE_EQUAL_SHARE",
        "area": smallest_positive_float,
        "room_count": 2,
    }


def test_representable_subnormal_area_uses_a_positive_exact_allocation() -> None:
    unit = math.ulp(0.0)
    intent = _intent(area=6 * unit, rooms=("bedroom",) * 4)

    target_areas = tuple(
        room.target_area for room in RuleBasedFloorPlanPlanner().plan(intent).rooms
    )

    assert target_areas == (unit, unit, unit, 3 * unit)
    assert math.fsum(target_areas) == intent.area


def test_planner_rejects_non_intent_input_at_its_public_boundary() -> None:
    with pytest.raises(PlanningContextError) as captured:
        RuleBasedFloorPlanPlanner().plan(cast(Any, {"area": 100}))

    assert captured.value.to_dict() == {
        "code": "PLANNING_CONTEXT_INVALID",
        "path": "/intent",
        "message": "Floor-plan rules require a validated DesignIntent.",
        "details": {"reason": "INVALID_INTENT_TYPE"},
    }
