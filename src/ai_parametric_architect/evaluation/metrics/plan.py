"""Floor-plan semantic validity metric."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from ai_parametric_architect.evaluation.metrics.models import MetricResult, summarize_binary
from ai_parametric_architect.evaluation.scenarios import Scenario
from ai_parametric_architect.planning.models import FloorPlanProposal

PLAN_VALIDITY: Final = "plan_validity"


@dataclass(frozen=True, slots=True)
class PlanValidity:
    """Check that a typed plan realizes the scenario intent and spatial constraints."""

    def is_valid(self, plan: FloorPlanProposal, scenario: Scenario) -> bool:
        if plan.intent != scenario.expected_intent:
            return False
        room_types = {room.plan_id: room.room_type for room in plan.rooms}
        actual_constraints = tuple(
            (
                room_types[constraint.source_plan_id],
                constraint.relation,
                room_types[constraint.target_plan_id],
                constraint.required,
            )
            for constraint in plan.spatial_constraints
        )
        expected_constraints = tuple(
            (
                constraint.source_room_type,
                constraint.relation,
                constraint.target_room_type,
                constraint.required,
            )
            for constraint in scenario.expected_constraints
        )
        return actual_constraints == expected_constraints

    def summarize(self, observations: Iterable[bool]) -> MetricResult:
        return summarize_binary(PLAN_VALIDITY, observations)
