"""Pure rectangular geometry projections for planning metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TypeGuard

from ai_parametric_architect.evaluation.planning_metrics.models import PlanningMetricError
from ai_parametric_architect.planning.models import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanProposal,
)


@dataclass(frozen=True, slots=True)
class PlanRectangle:
    plan_id: str
    room_type: str
    occurrence: int
    x: float
    y: float
    width: float
    height: float
    orientation: str

    @property
    def end_x(self) -> float:
        return self.x + self.width

    @property
    def end_y(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def occurrence_key(self) -> tuple[str, int]:
        return self.room_type, self.occurrence


def has_solved_layout(plan: object) -> TypeGuard[FloorPlanProposal]:
    return (
        type(plan) is FloorPlanProposal
        and plan.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
        and plan.boundary is not None
        and all(room.is_placed for room in plan.rooms)
    )


def rectangles(plan: FloorPlanProposal) -> tuple[PlanRectangle, ...]:
    if not has_solved_layout(plan):
        raise PlanningMetricError(
            "Planning metric requires a solved FloorPlanProposal v2.",
            path="/plan",
            details={"reason": "SOLVED_LAYOUT_REQUIRED"},
        )
    occurrences: defaultdict[str, int] = defaultdict(int)
    result: list[PlanRectangle] = []
    for room in plan.rooms:
        occurrences[room.room_type] += 1
        assert room.x is not None
        assert room.y is not None
        assert room.width is not None
        assert room.height is not None
        assert room.orientation is not None
        result.append(
            PlanRectangle(
                plan_id=room.plan_id,
                room_type=room.room_type,
                occurrence=occurrences[room.room_type],
                x=room.x,
                y=room.y,
                width=room.width,
                height=room.height,
                orientation=room.orientation,
            )
        )
    return tuple(result)


def overlap_area(left: PlanRectangle, right: PlanRectangle) -> float:
    width = max(0.0, min(left.end_x, right.end_x) - max(left.x, right.x))
    height = max(0.0, min(left.end_y, right.end_y) - max(left.y, right.y))
    return width * height


def shared_edge_contact(left: PlanRectangle, right: PlanRectangle, *, tolerance: float) -> float:
    vertical_touch = (
        abs(left.end_x - right.x) <= tolerance or abs(right.end_x - left.x) <= tolerance
    )
    if vertical_touch:
        return max(0.0, min(left.end_y, right.end_y) - max(left.y, right.y))
    horizontal_touch = (
        abs(left.end_y - right.y) <= tolerance or abs(right.end_y - left.y) <= tolerance
    )
    if horizontal_touch:
        return max(0.0, min(left.end_x, right.end_x) - max(left.x, right.x))
    return 0.0


def maximum_axis_clearance(left: PlanRectangle, right: PlanRectangle) -> float:
    return max(
        right.x - left.end_x,
        left.x - right.end_x,
        right.y - left.end_y,
        left.y - right.end_y,
        0.0,
    )


def center_manhattan_distance(left: PlanRectangle, right: PlanRectangle) -> float:
    return abs(left.center_x - right.center_x) + abs(left.center_y - right.center_y)


__all__ = [
    "PlanRectangle",
    "center_manhattan_distance",
    "has_solved_layout",
    "maximum_axis_clearance",
    "overlap_area",
    "rectangles",
    "shared_edge_contact",
]
