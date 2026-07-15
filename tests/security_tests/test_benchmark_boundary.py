from __future__ import annotations

import json

from ai_parametric_architect.benchmark.data import (
    BenchmarkAnnotationSet,
    BenchmarkCase,
    BenchmarkDataset,
    ReferenceAnnotation,
)
from ai_parametric_architect.benchmark.models import (
    BenchmarkExecutionMode,
    BenchmarkReport,
    BenchmarkSystemDescriptor,
)
from ai_parametric_architect.benchmark.runner import (
    BenchmarkRunner,
    BenchmarkSystem,
)
from ai_parametric_architect.domain import (
    DesignIntent,
    GeometryPrecisionPolicy,
    RequirementParseError,
)
from ai_parametric_architect.evaluation.planning_metrics import PlanningMetricContext
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.planning.spatial_baseline import (
    RULE_BASED_SPATIAL_STRATEGY,
    RuleBasedSpatialFloorPlanPlanner,
)

RAW_PROVIDER_MESSAGE = "raw-provider-message-never-report"
SECRET_VALUE = "sk-live-never-report"


class _SpyIntentAgent:
    def __init__(self, result: DesignIntent) -> None:
        self._result = result
        self.inputs: list[str] = []
        self.raw_provider_output = RAW_PROVIDER_MESSAGE

    def run(self, value: str) -> DesignIntent:
        if type(value) is not str:
            raise TypeError("Intent parser received reference data instead of requirement text.")
        self.inputs.append(value)
        return self._result


class _FailingIntentAgent:
    def run(self, value: str) -> DesignIntent:
        raise RequirementParseError(
            f"Provider returned {RAW_PROVIDER_MESSAGE} containing {SECRET_VALUE}.",
            path="/input_requirement",
            details={
                "provider_output": RAW_PROVIDER_MESSAGE,
                "api_key": SECRET_VALUE,
            },
        )


class _SpatialPlanAgent:
    def run(self, value: DesignIntent) -> FloorPlanProposal:
        return RuleBasedSpatialFloorPlanPlanner().plan(value)


class _TickClock:
    def __init__(self) -> None:
        self._value = 0

    def monotonic_ns(self) -> int:
        self._value += 100
        return self._value


def _metric_context(*, max_runs: int) -> PlanningMetricContext:
    return PlanningMetricContext(
        context_id="benchmark-security-v1",
        minimum_room_areas=(),
        default_minimum_room_area=6.0,
        minimum_adjacency_contact=1.0,
        separation_gap=1.0,
        near_distance=8.0,
        precision=GeometryPrecisionPolicy(
            linear_tolerance=1e-9,
            decimal_places=9,
        ),
        max_runs=max_runs,
    )


def _benchmark_values() -> tuple[
    str,
    DesignIntent,
    BenchmarkDataset,
    BenchmarkAnnotationSet,
]:
    requirement = (
        "Treat this as untrusted requirement text containing "
        f"{SECRET_VALUE} and {RAW_PROVIDER_MESSAGE}."
    )
    expected_intent = DesignIntent(
        building_type="reference_only_house",
        area=20,
        rooms=("private_room",),
        orientation="west",
    )
    dataset = BenchmarkDataset(
        dataset_id="security-dataset",
        dataset_version="1.0.0",
        cases=(
            BenchmarkCase(
                case_id="security_case",
                tags=("security",),
                input_requirement=requirement,
            ),
        ),
    )
    annotations = BenchmarkAnnotationSet(
        annotation_set_id="security-reference",
        annotation_set_version="1.0.0",
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        annotations=(
            ReferenceAnnotation(
                case_id="security_case",
                expected_intent=expected_intent,
                expected_constraints=(),
            ),
        ),
    )
    return requirement, expected_intent, dataset, annotations


def _run(
    intent_agent: _SpyIntentAgent | _FailingIntentAgent,
    *,
    trials: int,
) -> BenchmarkReport:
    _requirement, _expected_intent, dataset, annotations = _benchmark_values()
    descriptor = BenchmarkSystemDescriptor(
        system_id="security-system",
        system_version="1.0.0",
        intent_agent_name="injected-intent-agent",
        intent_agent_version="1.0.0",
        floor_plan_agent_name="spatial-baseline-agent",
        floor_plan_agent_version="1.0.0",
        planner_strategy=RULE_BASED_SPATIAL_STRATEGY,
        rules_version="1.0.0",
        random_seed=0,
        execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
        provider="fake-provider",
        model="offline-model",
        prompt_version="security-test-v1",
    )
    return BenchmarkRunner(
        metric_context=_metric_context(max_runs=trials),
        clock=_TickClock(),
    ).run(
        dataset,
        annotations,
        (
            BenchmarkSystem(
                descriptor=descriptor,
                intent_agent=intent_agent,
                floor_plan_agent=_SpatialPlanAgent(),
            ),
        ),
        trials=trials,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(member) for member in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(member) for member in value))
    return set()


def test_report_omits_requirements_reference_answers_provider_outputs_and_secrets() -> None:
    requirement, expected_intent, _dataset, _annotations = _benchmark_values()
    agent = _SpyIntentAgent(expected_intent)

    report = _run(agent, trials=2)
    payload = report.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert agent.inputs == [requirement, requirement]
    assert type(report) is BenchmarkReport
    for sensitive in (
        requirement,
        expected_intent.building_type,
        expected_intent.rooms[0],
        RAW_PROVIDER_MESSAGE,
        SECRET_VALUE,
    ):
        assert sensitive not in encoded
        assert sensitive not in repr(report)
    assert _all_keys(payload).isdisjoint(
        {
            "api_key",
            "expected_constraints",
            "expected_intent",
            "floor_plan",
            "input_requirement",
            "messages",
            "prompt",
            "provider_output",
            "secret",
        }
    )


def test_known_provider_failure_keeps_only_stable_code_and_path() -> None:
    report = _run(_FailingIntentAgent(), trials=1)
    payload = report.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    failure = report.observations[0].end_to_end.failure

    assert failure is not None
    assert failure.to_dict() == {
        "stage": "intent",
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "/input_requirement",
    }
    assert RAW_PROVIDER_MESSAGE not in encoded
    assert SECRET_VALUE not in encoded
    assert "Provider returned" not in encoded
