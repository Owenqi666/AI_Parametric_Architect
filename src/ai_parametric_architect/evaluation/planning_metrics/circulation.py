"""Normalized room-center distance proxy for circulation efficiency."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ai_parametric_architect.evaluation.planning_metrics.geometry import (
    center_manhattan_distance,
    rectangles,
)
from ai_parametric_architect.evaluation.planning_metrics.models import normalized_value
from ai_parametric_architect.planning.models import FloorPlanProposal


@dataclass(frozen=True, slots=True)
class CirculationScore:
    """Score a distance proxy; this is not a path, accessibility, or egress analysis."""

    def score(self, plan: FloorPlanProposal) -> float:
        room_values = rectangles(plan)
        assert plan.boundary is not None
        if len(room_values) == 1:
            return 1.0
        distances = tuple(
            center_manhattan_distance(left, right)
            for left_index, left in enumerate(room_values)
            for right in room_values[left_index + 1 :]
        )
        average_distance = math.fsum(distances) / len(distances)
        maximum_distance = plan.boundary.width + plan.boundary.height
        return normalized_value(1.0 - average_distance / maximum_distance, "circulation_score")


__all__ = ["CirculationScore"]
