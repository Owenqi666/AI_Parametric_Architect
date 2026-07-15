from __future__ import annotations

import json
from copy import deepcopy

from ai_parametric_architect.domain import (
    DesignIntent,
    GeometryPrecisionPolicy,
    SpatialConstraint,
    StrictJsonTreeGuard,
)
from ai_parametric_architect.evaluation import PlanValidity, Scenario
from ai_parametric_architect.evaluation.planning_metrics import (
    PlanningMetricContext,
    PlanningMetricsEvaluator,
)
from ai_parametric_architect.planning.solver import (
    ConstraintFloorPlanPlanner,
    CpSatFloorPlanSolver,
    PlanningRules,
)


def test_repeated_constraint_plans_are_valid_stable_and_json_only() -> None:
    intent = DesignIntent(
        building_type="house",
        area=60,
        rooms=("living", "kitchen", "bedroom", "bathroom"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation="adjacent_to",
                target_room_type="living",
            ),
        ),
    )
    scenario = Scenario(
        input_requirement="Create a south-facing house with an adjacent kitchen and living room",
        expected_intent=intent,
        expected_constraints=intent.spatial_constraints,
    )
    rules = PlanningRules()
    planner = ConstraintFloorPlanPlanner(
        rules=rules,
        solver=CpSatFloorPlanSolver(),
    )
    proposals = tuple(planner.plan(intent) for _ in range(3))
    proposal_snapshots = deepcopy([proposal.to_dict() for proposal in proposals])
    context = PlanningMetricContext.from_threshold_source(
        context_id="integration-planning-rules-v1",
        source=rules,
        precision=GeometryPrecisionPolicy(linear_tolerance=1e-9, decimal_places=9),
        max_runs=3,
    )

    report = PlanningMetricsEvaluator(context).evaluate(proposals)

    assert all(PlanValidity().is_valid(proposal, scenario) for proposal in proposals)
    assert report.constraint_satisfaction_score.value == 1.0
    assert report.plan_stability_score.value == 1.0
    assert report.exact_match_pairs == 3
    assert report.comparison_pairs == 3
    assert report.spatial_efficiency_score.value is not None
    assert 0.0 < report.spatial_efficiency_score.value <= 1.0
    assert report.circulation_score.value is not None
    assert 0.0 <= report.circulation_score.value <= 1.0
    assert [proposal.to_dict() for proposal in proposals] == proposal_snapshots

    payload = report.to_dict()
    StrictJsonTreeGuard().require(payload)
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert json.loads(encoded) == payload
