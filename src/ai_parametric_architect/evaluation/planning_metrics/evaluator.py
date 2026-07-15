"""Pure evaluator for one or more already-produced floor-plan proposals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_parametric_architect.evaluation.planning_metrics.circulation import CirculationScore
from ai_parametric_architect.evaluation.planning_metrics.constraints import (
    ConstraintSatisfactionScore,
)
from ai_parametric_architect.evaluation.planning_metrics.efficiency import (
    SpatialEfficiencyScore,
)
from ai_parametric_architect.evaluation.planning_metrics.geometry import has_solved_layout
from ai_parametric_architect.evaluation.planning_metrics.models import (
    REPEATED_PLANS_REQUIRED,
    SOLVED_LAYOUT_REQUIRED,
    NormalizedMetricResult,
    PlanMetricObservation,
    PlanningMetricContext,
    PlanningMetricError,
    PlanningMetricsReport,
    aggregate,
    not_applicable,
)
from ai_parametric_architect.evaluation.planning_metrics.stability import PlanStabilityScore
from ai_parametric_architect.planning.models import FloorPlanProposal

CONSTRAINT_SATISFACTION_SCORE = "constraint_satisfaction_score"
SPATIAL_EFFICIENCY_SCORE = "spatial_efficiency_score"
CIRCULATION_SCORE = "circulation_score"
PLAN_STABILITY_SCORE = "plan_stability_score"


@dataclass(frozen=True, slots=True)
class PlanningMetricsEvaluator:
    """Evaluate detached outputs only; never run an Agent, patch, validate, or commit."""

    metric_context: PlanningMetricContext

    def evaluate(self, plans: Sequence[FloorPlanProposal]) -> PlanningMetricsReport:
        plan_values = tuple(plans)
        if not plan_values:
            raise PlanningMetricError(
                "Planning metrics require at least one proposal.", path="/plans"
            )
        if len(plan_values) > self.metric_context.max_runs:
            raise PlanningMetricError(
                "Planning metric run count exceeds the configured budget.",
                path="/plans",
                details={
                    "maximum": self.metric_context.max_runs,
                    "actual": len(plan_values),
                },
            )
        for index, plan in enumerate(plan_values):
            if type(plan) is not FloorPlanProposal:
                raise PlanningMetricError(
                    "Planning metrics require exact FloorPlanProposal values.",
                    path=f"/plans/{index}",
                    details={"actual_type": type(plan).__name__},
                )
            if plan.intent != plan_values[0].intent:
                raise PlanningMetricError(
                    "Planning metric runs must retain the same DesignIntent.",
                    path=f"/plans/{index}/intent",
                )

        if not all(has_solved_layout(plan) for plan in plan_values):
            observations = tuple(
                PlanMetricObservation(
                    run_index=index,
                    strategy=plan.strategy,
                    constraint_satisfaction=None,
                    spatial_efficiency=None,
                    circulation=None,
                    satisfied_constraints=0,
                    total_constraints=0,
                )
                for index, plan in enumerate(plan_values)
            )
            return PlanningMetricsReport(
                metric_context=self.metric_context,
                observations=observations,
                constraint_satisfaction_score=not_applicable(
                    CONSTRAINT_SATISFACTION_SCORE, SOLVED_LAYOUT_REQUIRED
                ),
                spatial_efficiency_score=not_applicable(
                    SPATIAL_EFFICIENCY_SCORE, SOLVED_LAYOUT_REQUIRED
                ),
                circulation_score=not_applicable(CIRCULATION_SCORE, SOLVED_LAYOUT_REQUIRED),
                plan_stability_score=not_applicable(PLAN_STABILITY_SCORE, SOLVED_LAYOUT_REQUIRED),
                exact_match_pairs=0,
                comparison_pairs=0,
            )

        constraint_metric = ConstraintSatisfactionScore(self.metric_context)
        efficiency_metric = SpatialEfficiencyScore()
        circulation_metric = CirculationScore()
        observations_list: list[PlanMetricObservation] = []
        constraint_values: list[float] = []
        efficiency_values: list[float] = []
        circulation_values: list[float] = []
        for index, plan in enumerate(plan_values):
            constraint = constraint_metric.score(plan)
            efficiency = efficiency_metric.score(plan)
            circulation = circulation_metric.score(plan)
            constraint_values.append(constraint.value)
            efficiency_values.append(efficiency)
            circulation_values.append(circulation)
            observations_list.append(
                PlanMetricObservation(
                    run_index=index,
                    strategy=plan.strategy,
                    constraint_satisfaction=constraint.value,
                    spatial_efficiency=efficiency,
                    circulation=circulation,
                    satisfied_constraints=constraint.satisfied,
                    total_constraints=constraint.total,
                )
            )

        stability_result: NormalizedMetricResult
        exact_match_pairs = 0
        comparison_pairs = 0
        if len(plan_values) < 2:
            stability_result = not_applicable(PLAN_STABILITY_SCORE, REPEATED_PLANS_REQUIRED)
        else:
            stability = PlanStabilityScore().score(plan_values)
            exact_match_pairs = stability.exact_match_pairs
            comparison_pairs = stability.comparison_pairs
            stability_result = NormalizedMetricResult(
                name=PLAN_STABILITY_SCORE,
                value=stability.value,
                sample_count=stability.comparison_pairs,
            )
        return PlanningMetricsReport(
            metric_context=self.metric_context,
            observations=tuple(observations_list),
            constraint_satisfaction_score=aggregate(
                CONSTRAINT_SATISFACTION_SCORE, tuple(constraint_values)
            ),
            spatial_efficiency_score=aggregate(SPATIAL_EFFICIENCY_SCORE, tuple(efficiency_values)),
            circulation_score=aggregate(CIRCULATION_SCORE, tuple(circulation_values)),
            plan_stability_score=stability_result,
            exact_match_pairs=exact_match_pairs,
            comparison_pairs=comparison_pairs,
        )


__all__ = [
    "CIRCULATION_SCORE",
    "CONSTRAINT_SATISFACTION_SCORE",
    "PLAN_STABILITY_SCORE",
    "SPATIAL_EFFICIENCY_SCORE",
    "PlanningMetricsEvaluator",
]
