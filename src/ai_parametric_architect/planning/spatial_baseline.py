"""Deterministic spatial baseline for planner benchmarking.

This module deliberately remains independent of OR-Tools.  It turns the same
equal-area targets as the legacy semantic planner into one simple horizontal
strip, producing a detached ``FloorPlanProposal`` v2 for spatial comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from ai_parametric_architect.domain import DesignIntent, PlanningContextError
from ai_parametric_architect.planning.models import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanBoundary,
    FloorPlanConstraint,
    FloorPlanProposal,
    FloorPlanRoom,
)
from ai_parametric_architect.planning.rules import allocate_equal_target_areas

RULE_BASED_SPATIAL_STRATEGY: Final = "rule-based-single-row-v1"

_POLICY_VERSION: Final = "1.0.0"
_PLAN_ROOM_ID_PREFIX: Final = "plan_room_"
_MAX_IMPLEMENTATION_AREA: Final = 1_000_000.0
_MAX_IMPLEMENTATION_LENGTH: Final = 10_000.0
_MAX_WIDTH_ADJUSTMENTS: Final = 8


@dataclass(frozen=True, slots=True)
class RuleBasedSpatialPolicy:
    """Explicit resource limits and strip depth for the spatial baseline."""

    version: str = _POLICY_VERSION
    strip_depth: float = 4.0
    max_rooms: int = 16
    max_area: float = 2_500.0
    max_strip_length: float = 625.0

    def __post_init__(self) -> None:
        if self.version != _POLICY_VERSION:
            raise PlanningContextError(
                "Unsupported rule-based spatial policy version.",
                path="/policy/version",
            )
        _require_positive_finite_length(self.strip_depth, "/policy/strip_depth")
        if (
            not isinstance(self.max_rooms, int)
            or isinstance(self.max_rooms, bool)
            or not 1 <= self.max_rooms <= 64
        ):
            raise PlanningContextError(
                "Rule-based spatial max_rooms must be an integer from 1 to 64.",
                path="/policy/max_rooms",
            )
        _require_positive_finite_area(self.max_area, "/policy/max_area")
        _require_positive_finite_length(
            self.max_strip_length,
            "/policy/max_strip_length",
        )


@dataclass(frozen=True, slots=True)
class RuleBasedSpatialFloorPlanPlanner:
    """Lay rooms in stable intent order along one non-overlapping strip."""

    policy: RuleBasedSpatialPolicy = field(default_factory=RuleBasedSpatialPolicy)

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Rule-based spatial planning requires a validated DesignIntent.",
                path="/intent",
                details={"reason": "INVALID_INTENT_TYPE"},
            )
        if len(intent.rooms) > self.policy.max_rooms:
            raise PlanningContextError(
                "Design intent exceeds the rule-based spatial room budget.",
                path="/intent/rooms",
                details={
                    "reason": "ROOM_BUDGET_EXCEEDED",
                    "maximum": self.policy.max_rooms,
                    "actual": len(intent.rooms),
                },
            )
        if intent.area > self.policy.max_area:
            raise PlanningContextError(
                "Design intent exceeds the rule-based spatial area budget.",
                path="/intent/area",
                details={
                    "reason": "AREA_BUDGET_EXCEEDED",
                    "maximum": self.policy.max_area,
                    "actual": intent.area,
                },
            )

        target_areas = allocate_equal_target_areas(intent.area, len(intent.rooms))
        rooms: list[FloorPlanRoom] = []
        next_x = 0.0
        for index, (room_type, target_area) in enumerate(
            zip(intent.rooms, target_areas, strict=True),
            start=1,
        ):
            width = _conservative_width(target_area, self.policy.strip_depth)
            end_x = next_x + width
            if not math.isfinite(end_x) or end_x > self.policy.max_strip_length:
                raise PlanningContextError(
                    "Rule-based spatial strip exceeds its coordinate budget.",
                    path="/policy/max_strip_length",
                    details={
                        "reason": "STRIP_LENGTH_BUDGET_EXCEEDED",
                        "maximum": self.policy.max_strip_length,
                        "actual": end_x,
                        "room_index": index - 1,
                    },
                )
            rooms.append(
                FloorPlanRoom(
                    plan_id=f"{_PLAN_ROOM_ID_PREFIX}{index:03d}",
                    room_type=room_type,
                    target_area=target_area,
                    x=next_x,
                    y=0.0,
                    width=width,
                    height=self.policy.strip_depth,
                    orientation="south",
                )
            )
            next_x = end_x

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
            rooms=tuple(rooms),
            spatial_constraints=constraints,
            orientation=intent.orientation,
            strategy=RULE_BASED_SPATIAL_STRATEGY,
            schema_version=SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
            boundary=FloorPlanBoundary(
                width=next_x,
                height=self.policy.strip_depth,
            ),
        )


def _conservative_width(target_area: float, strip_depth: float) -> float:
    width = target_area / strip_depth
    if not math.isfinite(width) or width <= 0.0:
        raise PlanningContextError(
            "Room target area cannot be represented by the spatial strip.",
            path="/intent/area",
            details={"reason": "STRIP_WIDTH_UNREPRESENTABLE"},
        )
    for _ in range(_MAX_WIDTH_ADJUSTMENTS):
        if width * strip_depth <= target_area:
            return width
        adjusted = math.nextafter(width, 0.0)
        if adjusted <= 0.0 or adjusted == width:
            break
        width = adjusted
    raise PlanningContextError(
        "Room target area cannot be represented by the spatial strip.",
        path="/intent/area",
        details={"reason": "STRIP_WIDTH_UNREPRESENTABLE"},
    )


def _require_positive_finite_area(value: object, path: str) -> None:
    converted = _positive_finite(value, path)
    if converted > _MAX_IMPLEMENTATION_AREA:
        raise PlanningContextError(
            "Rule-based spatial area policy exceeds the implementation limit.",
            path=path,
            details={"maximum": _MAX_IMPLEMENTATION_AREA},
        )


def _require_positive_finite_length(value: object, path: str) -> None:
    converted = _positive_finite(value, path)
    if converted > _MAX_IMPLEMENTATION_LENGTH:
        raise PlanningContextError(
            "Rule-based spatial length policy exceeds the implementation limit.",
            path=path,
            details={"maximum": _MAX_IMPLEMENTATION_LENGTH},
        )


def _positive_finite(value: object, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PlanningContextError(
            "Rule-based spatial policy values must be positive finite numbers.",
            path=path,
        )
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        converted = math.nan
    if not math.isfinite(converted) or converted <= 0.0:
        raise PlanningContextError(
            "Rule-based spatial policy values must be positive finite numbers.",
            path=path,
        )
    return converted


__all__ = [
    "RULE_BASED_SPATIAL_STRATEGY",
    "RuleBasedSpatialFloorPlanPlanner",
    "RuleBasedSpatialPolicy",
]
