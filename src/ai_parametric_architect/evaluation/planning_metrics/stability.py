"""Order-independent repeated-run spatial stability score."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ai_parametric_architect.evaluation.planning_metrics.geometry import (
    has_solved_layout,
    rectangles,
)
from ai_parametric_architect.evaluation.planning_metrics.models import (
    PlanningMetricError,
    normalized_value,
)
from ai_parametric_architect.planning.models import FloorPlanProposal


@dataclass(frozen=True, slots=True)
class StabilityMeasurement:
    value: float
    exact_match_pairs: int
    comparison_pairs: int


@dataclass(frozen=True, slots=True)
class PlanStabilityScore:
    """Compare every pair so the result does not depend on a selected baseline run."""

    def score(self, plans: tuple[FloorPlanProposal, ...]) -> StabilityMeasurement:
        if not isinstance(plans, tuple) or len(plans) < 2:
            raise PlanningMetricError(
                "Plan stability requires at least two proposals.",
                path="/plans",
                details={"reason": "REPEATED_PLANS_REQUIRED"},
            )
        for index, plan in enumerate(plans):
            if not has_solved_layout(plan):
                raise PlanningMetricError(
                    "Plan stability requires solved FloorPlanProposal v2 values.",
                    path=f"/plans/{index}",
                    details={"reason": "SOLVED_LAYOUT_REQUIRED"},
                )
            if plan.intent != plans[0].intent:
                raise PlanningMetricError(
                    "Plan stability runs must retain the same DesignIntent.",
                    path=f"/plans/{index}/intent",
                )
        similarities: list[float] = []
        exact_matches = 0
        for left_index, left in enumerate(plans):
            for right in plans[left_index + 1 :]:
                similarities.append(_pair_similarity(left, right))
                if left == right:
                    exact_matches += 1
        return StabilityMeasurement(
            value=math.fsum(similarities) / len(similarities),
            exact_match_pairs=exact_matches,
            comparison_pairs=len(similarities),
        )


def _pair_similarity(left: FloorPlanProposal, right: FloorPlanProposal) -> float:
    assert left.boundary is not None
    assert right.boundary is not None
    left_rooms = rectangles(left)
    right_rooms = rectangles(right)
    differences: list[float] = [
        _relative_difference(left.boundary.width, right.boundary.width),
        _relative_difference(left.boundary.height, right.boundary.height),
    ]
    for left_room, right_room in zip(left_rooms, right_rooms, strict=True):
        differences.extend(
            (
                abs(left_room.x / left.boundary.width - right_room.x / right.boundary.width),
                abs(left_room.y / left.boundary.height - right_room.y / right.boundary.height),
                abs(
                    left_room.width / left.boundary.width - right_room.width / right.boundary.width
                ),
                abs(
                    left_room.height / left.boundary.height
                    - right_room.height / right.boundary.height
                ),
                0.0 if left_room.orientation == right_room.orientation else 1.0,
                0.0 if left_room.plan_id == right_room.plan_id else 1.0,
            )
        )
    left_constraints = _constraint_occurrence_bindings(left)
    right_constraints = _constraint_occurrence_bindings(right)
    differences.extend(
        0.0 if left_value == right_value else 1.0
        for left_value, right_value in zip(left_constraints, right_constraints, strict=True)
    )
    return normalized_value(
        1.0 - math.fsum(differences) / len(differences),
        "plan_stability_score",
    )


def _constraint_occurrence_bindings(
    plan: FloorPlanProposal,
) -> tuple[tuple[tuple[str, int], str, tuple[str, int], bool], ...]:
    room_keys = {room.plan_id: room.occurrence_key for room in rectangles(plan)}
    return tuple(
        (
            room_keys[constraint.source_plan_id],
            constraint.relation.value,
            room_keys[constraint.target_plan_id],
            constraint.required,
        )
        for constraint in plan.spatial_constraints
    )


def _relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(left, right)


__all__ = ["PlanStabilityScore", "StabilityMeasurement"]
