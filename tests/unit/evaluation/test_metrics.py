from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import DesignIntent, SpatialConstraint
from ai_parametric_architect.evaluation.metrics import (
    IntentExtractionAccuracy,
    MetricResult,
    PatchValidationSuccessRate,
    PlanValidity,
)
from ai_parametric_architect.evaluation.metrics.models import summarize_binary
from ai_parametric_architect.evaluation.scenarios import Scenario
from ai_parametric_architect.planning import RuleBasedFloorPlanPlanner


def _scenario() -> Scenario:
    intent = DesignIntent(
        building_type="house",
        area=100,
        rooms=("living", "bedroom"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="living",
                relation="adjacent_to",
                target_room_type="bedroom",
            ),
        ),
    )
    return Scenario("requirement", intent, intent.spatial_constraints)


def test_metric_result_exposes_exact_counts_and_rate() -> None:
    metric = summarize_binary("test_metric", (True, False, True))

    assert metric == MetricResult(name="test_metric", successes=2, total=3)
    assert metric.value == pytest.approx(2 / 3)
    assert metric.to_dict() == {
        "name": "test_metric",
        "value": pytest.approx(2 / 3),
        "successes": 2,
        "total": 3,
    }
    assert summarize_binary("empty", ()).value == 0.0


@pytest.mark.parametrize(
    "metric",
    [
        MetricResult(name="valid", successes=0, total=0),
        MetricResult(name="valid", successes=1, total=1),
    ],
)
def test_valid_metric_count_boundaries(metric: MetricResult) -> None:
    assert 0.0 <= metric.value <= 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "successes": 0, "total": 0},
        {"name": "x", "successes": -1, "total": 1},
        {"name": "x", "successes": 2, "total": 1},
        {"name": "x", "successes": 0, "total": -1},
        {"name": "x", "successes": True, "total": 1},
        {"name": "x", "successes": 0, "total": False},
    ],
)
def test_metric_result_rejects_invalid_counts(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MetricResult(**cast(Any, kwargs))


def test_binary_summary_rejects_non_boolean_observations() -> None:
    with pytest.raises(TypeError):
        summarize_binary("bad", cast(Any, (True, 1)))


def test_intent_accuracy_is_exact_and_plan_validity_checks_constraint_realization() -> None:
    scenario = _scenario()
    intent_metric = IntentExtractionAccuracy()
    plan_metric = PlanValidity()
    plan = RuleBasedFloorPlanPlanner().plan(scenario.expected_intent)
    different_intent = DesignIntent(
        building_type="house",
        area=100,
        rooms=("bedroom",),
    )

    assert intent_metric.matches(scenario.expected_intent, scenario)
    assert not intent_metric.matches(different_intent, scenario)
    assert plan_metric.is_valid(plan, scenario)
    assert not plan_metric.is_valid(
        RuleBasedFloorPlanPlanner().plan(different_intent),
        scenario,
    )
    assert intent_metric.summarize((True, False)).value == 0.5
    assert plan_metric.summarize((True, True)).value == 1.0
    assert PatchValidationSuccessRate().summarize((False, True)).value == 0.5
