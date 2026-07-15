"""Deterministic allocation rules for the Task 3 floor-plan IR."""

from __future__ import annotations

import math
from typing import Final

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import PlanningContextError
from ai_parametric_architect.planning.models import (
    FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanConstraint,
    FloorPlanProposal,
    FloorPlanRoom,
)

EQUAL_AREA_STABLE_ORDER_STRATEGY: Final = "equal-area-stable-order-v1"
_PLAN_ROOM_ID_PREFIX: Final = "plan_room_"
_MAX_PREFIX_ADJUSTMENTS: Final = 256
_MAX_RESIDUAL_ADJUSTMENTS: Final = 256


class RuleBasedFloorPlanPlanner:
    """Allocate intent rooms without reading or mutating the JSON world model."""

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Floor-plan rules require a validated DesignIntent.",
                path="/intent",
                details={"reason": "INVALID_INTENT_TYPE"},
            )

        target_areas = allocate_equal_target_areas(intent.area, len(intent.rooms))
        rooms = tuple(
            FloorPlanRoom(
                plan_id=f"{_PLAN_ROOM_ID_PREFIX}{index:03d}",
                room_type=room_type,
                target_area=target_area,
            )
            for index, (room_type, target_area) in enumerate(
                zip(intent.rooms, target_areas, strict=True),
                start=1,
            )
        )
        first_room_by_type: dict[str, str] = {}
        for room in rooms:
            first_room_by_type.setdefault(room.room_type, room.plan_id)

        constraints = tuple(
            FloorPlanConstraint(
                source_plan_id=first_room_by_type[constraint.source_room_type],
                relation=constraint.relation,
                target_plan_id=first_room_by_type[constraint.target_room_type],
                required=constraint.required,
            )
            for constraint in intent.spatial_constraints
        )
        return FloorPlanProposal(
            intent=intent,
            rooms=rooms,
            spatial_constraints=constraints,
            orientation=intent.orientation,
            strategy=EQUAL_AREA_STABLE_ORDER_STRATEGY,
            schema_version=FLOOR_PLAN_SCHEMA_VERSION,
        )


def allocate_equal_target_areas(area: float, count: int) -> tuple[float, ...]:
    """Allocate exact positive targets while preserving the input float total."""

    share = area / count
    if not math.isfinite(share) or share <= 0.0:
        raise _area_allocation_error(area, count, "NON_POSITIVE_EQUAL_SHARE")
    if count == 1:
        return (area,)

    prefix_share = share
    prefix: tuple[float, ...] = ()
    residual = 0.0
    for _ in range(_MAX_PREFIX_ADJUSTMENTS + 1):
        prefix = (prefix_share,) * (count - 1)
        residual = area - math.fsum(prefix)
        if math.isfinite(residual) and residual > 0.0:
            break
        candidate = math.nextafter(prefix_share, 0.0)
        if candidate <= 0.0 or candidate == prefix_share:
            break
        prefix_share = candidate
    if not math.isfinite(residual) or residual <= 0.0:
        raise _area_allocation_error(area, count, "NON_POSITIVE_RESIDUAL")

    adjustments = 0
    total = _sum_areas(prefix, residual)
    while total != area and adjustments < _MAX_RESIDUAL_ADJUSTMENTS:
        direction = math.inf if total < area else -math.inf
        candidate = math.nextafter(residual, direction)
        if not math.isfinite(candidate) or candidate <= 0.0 or candidate == residual:
            break
        residual = candidate
        total = math.fsum((*prefix, residual))
        adjustments += 1

    if not math.isfinite(residual) or residual <= 0.0 or total != area:
        raise _area_allocation_error(area, count, "EXACT_TOTAL_UNREPRESENTABLE")
    return (*prefix, residual)


def _sum_areas(prefix: tuple[float, ...], residual: float) -> float:
    try:
        return math.fsum((*prefix, residual))
    except OverflowError:
        return math.inf


def _area_allocation_error(area: float, count: int, reason: str) -> PlanningContextError:
    return PlanningContextError(
        "Design area cannot be allocated into positive finite room targets.",
        path="/intent/area",
        details={
            "reason": reason,
            "area": area,
            "room_count": count,
        },
    )
