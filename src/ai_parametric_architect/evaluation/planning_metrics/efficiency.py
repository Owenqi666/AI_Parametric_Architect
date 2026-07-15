"""Net-to-gross spatial efficiency score."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ai_parametric_architect.evaluation.planning_metrics.geometry import rectangles
from ai_parametric_architect.evaluation.planning_metrics.models import normalized_value
from ai_parametric_architect.planning.models import FloorPlanProposal


@dataclass(frozen=True, slots=True)
class SpatialEfficiencyScore:
    def score(self, plan: FloorPlanProposal) -> float:
        room_values = rectangles(plan)
        assert plan.boundary is not None
        room_area = math.fsum(room.area for room in room_values)
        boundary_area = plan.boundary.width * plan.boundary.height
        value = room_area / boundary_area
        return normalized_value(value, "spatial_efficiency_score")


__all__ = ["SpatialEfficiencyScore"]
