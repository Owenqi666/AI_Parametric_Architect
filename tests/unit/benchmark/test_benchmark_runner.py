from __future__ import annotations

import json
from typing import cast

import pytest

from ai_parametric_architect.agents import ArchitecturePlannerAgent
from ai_parametric_architect.benchmark.data import (
    BenchmarkAnnotationSet,
    BenchmarkCase,
    BenchmarkDataset,
    ReferenceAnnotation,
)
from ai_parametric_architect.benchmark.models import (
    BenchmarkBudget,
    BenchmarkExecutionMode,
    BenchmarkSystemDescriptor,
)
from ai_parametric_architect.benchmark.runner import (
    EXACT_REFERENCE_INTENT_REQUIRED,
    BenchmarkRunner,
    BenchmarkSystem,
)
from ai_parametric_architect.domain import (
    DesignIntent,
    GeometryPrecisionPolicy,
    RequirementParseError,
)
from ai_parametric_architect.evaluation.planning_metrics import PlanningMetricContext
from ai_parametric_architect.planning import (
    RULE_BASED_SPATIAL_STRATEGY,
    RuleBasedSpatialFloorPlanPlanner,
)
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.planning.solver import PlanningRules


class StepClock:
    def __init__(self, *, step: int = 10) -> None:
        self.value = 0
        self.step = step
        self.calls = 0

    def monotonic_ns(self) -> int:
        self.calls += 1
        self.value += self.step
        return self.value


class StaticIntentAgent:
    def __init__(self, intent: DesignIntent) -> None:
        self.intent = intent
        self.calls = 0

    def run(self, value: str) -> DesignIntent:
        self.calls += 1
        return self.intent


class FailingIntentAgent:
    def run(self, value: str) -> DesignIntent:
        raise RequirementParseError(
            "secret provider response",
            path="/input_requirement",
            details={"provider_payload": "must-not-leak"},
        )


class UnexpectedIntentAgent:
    def run(self, value: str) -> DesignIntent:
        raise RuntimeError("dependency bug")


class CountingFloorPlanAgent:
    def __init__(self) -> None:
        self._agent = ArchitecturePlannerAgent(RuleBasedSpatialFloorPlanPlanner())
        self.calls = 0

    def run(self, value: DesignIntent) -> FloorPlanProposal:
        self.calls += 1
        return self._agent.run(value)


def _intent(*, area: int = 60) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=area,
        rooms=("living", "bedroom"),
        orientation="south",
    )


def _dataset_and_annotations() -> tuple[BenchmarkDataset, BenchmarkAnnotationSet]:
    intent = _intent()
    dataset = BenchmarkDataset(
        dataset_id="planning-core",
        dataset_version="1.0.0",
        cases=(
            BenchmarkCase(
                case_id="basic-house",
                tags=("basic",),
                input_requirement="PRIVATE requirement text that must not enter the report",
            ),
        ),
    )
    annotations = BenchmarkAnnotationSet(
        annotation_set_id="planning-reference",
        annotation_set_version="1.0.0",
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        annotations=(
            ReferenceAnnotation(
                case_id="basic-house",
                expected_intent=intent,
                expected_constraints=intent.spatial_constraints,
            ),
        ),
    )
    return dataset, annotations


def _context(*, max_runs: int = 4) -> PlanningMetricContext:
    return PlanningMetricContext.from_threshold_source(
        context_id="benchmark-rules-v1",
        source=PlanningRules(),
        precision=GeometryPrecisionPolicy(linear_tolerance=1e-9, decimal_places=9),
        max_runs=max_runs,
    )


def _system(
    intent_agent: StaticIntentAgent | FailingIntentAgent | UnexpectedIntentAgent,
    floor_plan_agent: CountingFloorPlanAgent,
    *,
    planner_strategy: str = RULE_BASED_SPATIAL_STRATEGY,
) -> BenchmarkSystem:
    return BenchmarkSystem(
        descriptor=BenchmarkSystemDescriptor(
            system_id="rule-v2",
            system_version="1.0.0",
            intent_agent_name="test-intent-agent",
            intent_agent_version="1.0.0",
            floor_plan_agent_name="architecture-planner-agent",
            floor_plan_agent_version="2.0.0",
            planner_strategy=planner_strategy,
            rules_version="1.0.0",
            random_seed=0,
            execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
        ),
        intent_agent=intent_agent,
        floor_plan_agent=floor_plan_agent,
    )


def test_runner_executes_both_tracks_and_gates_end_to_end_spatial_metrics() -> None:
    dataset, annotations = _dataset_and_annotations()
    clock = StepClock()
    plan_agent = CountingFloorPlanAgent()
    runner = BenchmarkRunner(metric_context=_context(), clock=clock)

    report = runner.run(
        dataset,
        annotations,
        (_system(StaticIntentAgent(_intent(area=61)), plan_agent),),
        trials=2,
    )

    system = report.systems[0]
    assert system.attempt_count == 2
    assert system.intent_extraction_accuracy.value == 0.0
    assert system.intent_extraction_accuracy.sample_count == 2
    assert system.end_to_end.planning_success.value == 1.0
    assert system.end_to_end.plan_validity.value == 0.0
    assert system.end_to_end.constraint_satisfaction.value is None
    assert system.end_to_end.constraint_satisfaction.reason == EXACT_REFERENCE_INTENT_REQUIRED
    assert system.end_to_end.constraint_satisfaction.attempt_count == 2
    assert system.end_to_end.constraint_satisfaction.sample_count == 0
    assert system.oracle_intent.planning_success.value == 1.0
    assert system.oracle_intent.plan_validity.value == 1.0
    assert system.oracle_intent.constraint_satisfaction.sample_count == 2
    assert system.oracle_intent.stability.value == 1.0
    assert system.oracle_intent.stability.sample_count == 1
    assert plan_agent.calls == 4

    assert system.end_to_end.parse_runtime.minimum_ns == 10
    assert system.end_to_end.plan_runtime.median_ns == 10
    assert system.end_to_end.total_runtime.p95_ns == 20
    assert system.oracle_intent.parse_runtime.sample_count == 0
    assert system.oracle_intent.plan_runtime.coverage == 1.0

    payload = report.to_dict()
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert "PRIVATE requirement" not in encoded
    assert "expected_intent" not in encoded
    assert '"rooms"' not in encoded
    configuration = cast(dict[str, object], payload["configuration"])
    observations = cast(list[object], payload["observations"])
    assert configuration["metric_context"] == _context().to_dict()
    assert len(observations) == 2


def test_exact_intent_enables_end_to_end_spatial_metrics_and_stability() -> None:
    dataset, annotations = _dataset_and_annotations()
    report = BenchmarkRunner(metric_context=_context(), clock=StepClock()).run(
        dataset,
        annotations,
        (_system(StaticIntentAgent(_intent()), CountingFloorPlanAgent()),),
        trials=2,
    )

    system = report.systems[0]
    assert system.intent_extraction_accuracy.value == 1.0
    assert system.end_to_end.constraint_satisfaction.sample_count == 2
    assert system.end_to_end.spatial_efficiency.sample_count == 2
    assert system.end_to_end.circulation.sample_count == 2
    assert system.end_to_end.stability.value == 1.0
    assert system.end_to_end.stability.sample_count == 1
    assert system.end_to_end.stability.coverage == 1.0


def test_known_planning_error_is_redacted_and_oracle_track_still_runs() -> None:
    dataset, annotations = _dataset_and_annotations()
    plan_agent = CountingFloorPlanAgent()
    report = BenchmarkRunner(metric_context=_context(), clock=StepClock()).run(
        dataset,
        annotations,
        (_system(FailingIntentAgent(), plan_agent),),
    )

    observation = report.observations[0]
    assert observation.end_to_end.failure is not None
    assert observation.end_to_end.failure.to_dict() == {
        "stage": "intent",
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "/input_requirement",
    }
    assert not observation.end_to_end.planning_succeeded
    assert observation.oracle_intent.planning_succeeded
    assert plan_agent.calls == 1
    encoded = json.dumps(report.to_dict(), sort_keys=True)
    assert "secret provider response" not in encoded
    assert "provider_payload" not in encoded


def test_unexpected_agent_failure_propagates() -> None:
    dataset, annotations = _dataset_and_annotations()
    runner = BenchmarkRunner(metric_context=_context(), clock=StepClock())

    with pytest.raises(RuntimeError, match="dependency bug"):
        runner.run(
            dataset,
            annotations,
            (_system(UnexpectedIntentAgent(), CountingFloorPlanAgent()),),
        )


def test_mislabeled_planner_strategy_propagates_as_contract_failure() -> None:
    dataset, annotations = _dataset_and_annotations()
    runner = BenchmarkRunner(metric_context=_context(), clock=StepClock())

    with pytest.raises(TypeError, match="strategy does not match"):
        runner.run(
            dataset,
            annotations,
            (
                _system(
                    StaticIntentAgent(_intent()),
                    CountingFloorPlanAgent(),
                    planner_strategy="misleading-strategy",
                ),
            ),
        )


def test_budget_is_checked_before_clock_or_agent_calls() -> None:
    dataset, annotations = _dataset_and_annotations()
    clock = StepClock()
    intent_agent = StaticIntentAgent(_intent())
    plan_agent = CountingFloorPlanAgent()
    runner = BenchmarkRunner(
        metric_context=_context(),
        clock=clock,
        budget=BenchmarkBudget(max_cases=1, max_systems=1, max_trials=1, max_attempts=1),
    )

    with pytest.raises(ValueError, match="trial count"):
        runner.run(
            dataset,
            annotations,
            (_system(intent_agent, plan_agent),),
            trials=2,
        )

    assert clock.calls == 0
    assert intent_agent.calls == 0
    assert plan_agent.calls == 0
