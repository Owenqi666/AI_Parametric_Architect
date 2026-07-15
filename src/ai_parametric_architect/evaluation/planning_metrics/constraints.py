"""Constraint-satisfaction score for detached rectangular proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ai_parametric_architect.domain import SpatialRelation
from ai_parametric_architect.evaluation.planning_metrics.geometry import (
    PlanRectangle,
    center_manhattan_distance,
    maximum_axis_clearance,
    overlap_area,
    rectangles,
    shared_edge_contact,
)
from ai_parametric_architect.evaluation.planning_metrics.models import PlanningMetricContext
from ai_parametric_architect.planning.models import FloorPlanProposal


@dataclass(frozen=True, slots=True)
class ConstraintScore:
    value: float
    satisfied: int
    total: int


@dataclass(frozen=True, slots=True)
class ConstraintSatisfactionScore:
    """Score structural, minimum-area, and declared spatial constraints."""

    context: PlanningMetricContext

    def score(self, plan: FloorPlanProposal) -> ConstraintScore:
        room_values = rectangles(plan)
        assert plan.boundary is not None
        tolerance = self.context.precision.linear_tolerance
        area_tolerance = self.context.precision.area_tolerance
        observations: list[bool] = []

        for room in room_values:
            observations.append(
                room.area + area_tolerance >= self.context.minimum_area_for(room.room_type)
            )
            observations.append(
                room.x >= -tolerance
                and room.y >= -tolerance
                and room.end_x <= plan.boundary.width + tolerance
                and room.end_y <= plan.boundary.height + tolerance
            )
        for left_index, left in enumerate(room_values):
            for right in room_values[left_index + 1 :]:
                observations.append(overlap_area(left, right) <= area_tolerance)

        rooms_by_id = {room.plan_id: room for room in room_values}
        for constraint in plan.spatial_constraints:
            observations.append(
                self._relation_satisfied(
                    rooms_by_id[constraint.source_plan_id],
                    constraint.relation,
                    rooms_by_id[constraint.target_plan_id],
                )
            )
        satisfied = sum(observations)
        return ConstraintScore(
            value=satisfied / len(observations),
            satisfied=satisfied,
            total=len(observations),
        )

    def _relation_satisfied(
        self,
        source: PlanRectangle,
        relation: SpatialRelation,
        target: PlanRectangle,
    ) -> bool:
        tolerance = self.context.precision.linear_tolerance
        if relation is SpatialRelation.ADJACENT_TO:
            return (
                shared_edge_contact(source, target, tolerance=tolerance) + tolerance
                >= self.context.minimum_adjacency_contact
            )
        if relation is SpatialRelation.SEPARATED_FROM:
            return maximum_axis_clearance(source, target) + tolerance >= self.context.separation_gap
        if relation is SpatialRelation.NEAR:
            return (
                center_manhattan_distance(source, target) <= self.context.near_distance + tolerance
            )
        if relation is SpatialRelation.NORTH_OF:
            return source.y + tolerance >= target.end_y
        if relation is SpatialRelation.SOUTH_OF:
            return source.end_y <= target.y + tolerance
        if relation is SpatialRelation.EAST_OF:
            return source.x + tolerance >= target.end_x
        return source.end_x <= target.x + tolerance


__all__ = ["ConstraintSatisfactionScore", "ConstraintScore"]
