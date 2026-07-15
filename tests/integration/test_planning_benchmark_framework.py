from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from ai_parametric_architect.agents import ArchitecturePlannerAgent, RequirementAgent
from ai_parametric_architect.benchmark.data import (
    BenchmarkAnnotationSet,
    BenchmarkCase,
    BenchmarkDataset,
    ReferenceAnnotation,
)
from ai_parametric_architect.benchmark.models import (
    BenchmarkExecutionMode,
    BenchmarkSystemDescriptor,
)
from ai_parametric_architect.benchmark.runner import BenchmarkRunner, BenchmarkSystem
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    GeometryPrecisionPolicy,
    ModelRevision,
    TrustedAuditIdentity,
)
from ai_parametric_architect.evaluation.planning_metrics import PlanningMetricContext
from ai_parametric_architect.infrastructure.llm import (
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
)
from ai_parametric_architect.llm import PROMPT_VERSION, LLMRequirementParser
from ai_parametric_architect.planning import (
    RULE_BASED_SPATIAL_STRATEGY,
    RuleBasedRequirementParser,
    RuleBasedSpatialFloorPlanPlanner,
    RuleBasedSpatialPolicy,
)
from ai_parametric_architect.planning.solver import (
    CP_SAT_STRATEGY,
    ConstraintFloorPlanPlanner,
    PlanningRules,
)
from ai_parametric_architect.repositories import InMemoryRevisionRepository

RAW_REQUIREMENT_MARKER = "RAW_REQUIREMENT_MARKER"
RAW_PROVIDER_OUTPUT_MARKER = r"\u0068\u006f\u0075\u0073\u0065"
TRIALS = 2


def _completed_response(text: str) -> object:
    block = SimpleNamespace(type="output_text", text=text)
    message = SimpleNamespace(
        type="message",
        role="assistant",
        status="completed",
        content=[block],
    )
    return SimpleNamespace(status="completed", error=None, output=[message])


class _FakeResponses:
    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(dict(kwargs))
        return self._response


class _FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.responses = _FakeResponses(response)


class _StepMonotonicClock:
    def __init__(self, step_ns: int = 10) -> None:
        self._value = 0
        self._step_ns = step_ns

    def monotonic_ns(self) -> int:
        self._value += self._step_ns
        return self._value


def _intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=60,
        rooms=("living", "bedroom"),
        orientation="south",
    )


def _benchmark_data() -> tuple[BenchmarkDataset, BenchmarkAnnotationSet]:
    expected = _intent()
    dataset = BenchmarkDataset(
        dataset_id="integration_planning_core",
        dataset_version="1.0.0",
        cases=(
            BenchmarkCase(
                case_id="residential_basic",
                tags=("english", "orientation", "residential"),
                input_requirement=(
                    "Design a south-facing 60 sqm house with one living room and one bedroom. "
                    f"{RAW_REQUIREMENT_MARKER}"
                ),
            ),
        ),
    )
    annotations = BenchmarkAnnotationSet(
        annotation_set_id="integration_planning_reference",
        annotation_set_version="1.0.0",
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        annotations=(
            ReferenceAnnotation(
                case_id="residential_basic",
                expected_intent=expected,
                expected_constraints=expected.spatial_constraints,
            ),
        ),
    )
    return dataset, annotations


def _repository() -> InMemoryRevisionRepository:
    repository = InMemoryRevisionRepository()
    repository.initialize(
        ModelRevision(
            model_id="mdl_benchmark_guard",
            revision_number=0,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            parent_revision=None,
            document={"model_id": "mdl_benchmark_guard", "revision": 0},
        ),
        provenance="fixture:benchmark-integration",
        rationale="Create an authority snapshot outside the benchmark runner.",
        audit_identity=TrustedAuditIdentity(
            actor_id="benchmark-integration-fixture",
            actor_type=AuditActorType.SYSTEM,
            trace_id="trace:benchmark-integration-fixture",
        ),
    )
    return repository


def _repository_snapshot(repository: InMemoryRevisionRepository) -> tuple[object, ...]:
    return (
        repository.head("mdl_benchmark_guard").to_dict(),
        tuple(entry.to_dict() for entry in repository.audit_log("mdl_benchmark_guard")),
    )


def test_three_planning_systems_remain_detached_and_report_only_allowlisted_evidence() -> None:
    dataset, annotations = _benchmark_data()
    rules = PlanningRules()
    context = PlanningMetricContext.from_threshold_source(
        context_id="integration_benchmark_rules_v1",
        source=rules,
        precision=GeometryPrecisionPolicy(linear_tolerance=1e-9, decimal_places=9),
        max_runs=TRIALS,
    )
    rule_requirement_agent = RequirementAgent(RuleBasedRequirementParser())
    rule_spatial_agent = ArchitecturePlannerAgent(RuleBasedSpatialFloorPlanPlanner())
    cp_sat_agent = ArchitecturePlannerAgent(ConstraintFloorPlanPlanner(rules=rules))

    provider_payload = {
        "building_type": "house",
        "area": 60,
        "rooms": ["living", "bedroom"],
        "orientation": "south",
        "spatial_constraints": [],
    }
    raw_provider_output = json.dumps(provider_payload, ensure_ascii=False).replace(
        '"house"',
        f'"{RAW_PROVIDER_OUTPUT_MARKER}"',
    )
    assert RAW_PROVIDER_OUTPUT_MARKER in raw_provider_output
    fake_client = _FakeOpenAIClient(_completed_response(raw_provider_output))
    provider_config = OpenAIProviderConfig(model="gpt-test", max_retries=0)
    provider = OpenAIResponsesProvider(provider_config, client=fake_client)
    openai_requirement_agent = RequirementAgent(LLMRequirementParser(provider))

    systems = (
        BenchmarkSystem(
            descriptor=BenchmarkSystemDescriptor(
                system_id="rule_spatial_v1",
                system_version="1.0.0",
                intent_agent_name=rule_requirement_agent.name,
                intent_agent_version=rule_requirement_agent.version,
                floor_plan_agent_name=rule_spatial_agent.name,
                floor_plan_agent_version=rule_spatial_agent.version,
                planner_strategy=RULE_BASED_SPATIAL_STRATEGY,
                rules_version=RuleBasedSpatialPolicy().version,
                random_seed=0,
                execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
            ),
            intent_agent=rule_requirement_agent,
            floor_plan_agent=rule_spatial_agent,
        ),
        BenchmarkSystem(
            descriptor=BenchmarkSystemDescriptor(
                system_id="cp_sat_v1",
                system_version="1.0.0",
                intent_agent_name=rule_requirement_agent.name,
                intent_agent_version=rule_requirement_agent.version,
                floor_plan_agent_name=cp_sat_agent.name,
                floor_plan_agent_version=cp_sat_agent.version,
                planner_strategy=CP_SAT_STRATEGY,
                rules_version=rules.version,
                random_seed=rules.random_seed,
                execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
            ),
            intent_agent=rule_requirement_agent,
            floor_plan_agent=cp_sat_agent,
        ),
        BenchmarkSystem(
            descriptor=BenchmarkSystemDescriptor(
                system_id="openai_cp_sat_v1",
                system_version="1.0.0",
                intent_agent_name=openai_requirement_agent.name,
                intent_agent_version=openai_requirement_agent.version,
                floor_plan_agent_name=cp_sat_agent.name,
                floor_plan_agent_version=cp_sat_agent.version,
                planner_strategy=CP_SAT_STRATEGY,
                rules_version=rules.version,
                random_seed=None,
                execution_mode=BenchmarkExecutionMode.REAL_NONDETERMINISTIC,
                provider=provider.name,
                model=provider_config.model,
                prompt_version=PROMPT_VERSION,
            ),
            intent_agent=openai_requirement_agent,
            floor_plan_agent=cp_sat_agent,
        ),
    )
    repository = _repository()
    repository_before = _repository_snapshot(repository)

    report = BenchmarkRunner(metric_context=context, clock=_StepMonotonicClock()).run(
        dataset,
        annotations,
        systems,
        trials=TRIALS,
    )

    assert _repository_snapshot(repository) == repository_before
    assert len(report.systems) == 3
    assert len(report.observations) == len(systems) * TRIALS
    for system_report in report.systems:
        assert system_report.attempt_count == TRIALS
        assert system_report.intent_extraction_accuracy.attempt_count == TRIALS
        assert system_report.intent_extraction_accuracy.value == 1.0
        for track in (system_report.end_to_end, system_report.oracle_intent):
            assert track.planning_success.attempt_count == TRIALS
            assert track.planning_success.value == 1.0
            assert track.plan_validity.attempt_count == TRIALS
            assert track.plan_validity.value == 1.0
            assert track.constraint_satisfaction.attempt_count == TRIALS
            assert track.constraint_satisfaction.covered_attempt_count == TRIALS
            assert track.stability.attempt_count == TRIALS
            assert track.stability.sample_count == 1
            assert track.stability.value == 1.0
            assert track.plan_runtime.attempt_count == TRIALS
            assert track.total_runtime.attempt_count == TRIALS
        assert system_report.end_to_end.parse_runtime.sample_count == TRIALS
        assert system_report.oracle_intent.parse_runtime.attempt_count == TRIALS
        assert system_report.oracle_intent.parse_runtime.sample_count == 0

    openai_report = next(
        value for value in report.systems if value.descriptor.system_id == "openai_cp_sat_v1"
    )
    assert not openai_report.descriptor.deterministic
    assert openai_report.descriptor.random_seed is None
    assert len(fake_client.responses.calls) == TRIALS
    for request in fake_client.responses.calls:
        assert request["store"] is False
        assert request["tools"] == []
        assert request["truncation"] == "disabled"
        assert cast(dict[str, Any], request["text"])["format"]["strict"] is True
        messages = cast(list[dict[str, str]], request["input"])
        assert [message["role"] for message in messages] == ["developer", "user"]
        assert RAW_REQUIREMENT_MARKER in messages[1]["content"]

    payload = report.to_dict()
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert json.loads(encoded) == payload
    assert RAW_REQUIREMENT_MARKER not in encoded
    assert RAW_PROVIDER_OUTPUT_MARKER not in encoded
    assert "expected_intent" not in encoded
    assert "expected_constraints" not in encoded
    forbidden_keys = {
        "commit",
        "document",
        "geometry",
        "input_requirement",
        "model_id",
        "operations",
        "output",
        "patch",
        "patch_proposal",
        "prompt",
        "provider_output",
        "revision",
        "revision_number",
        "system_prompt",
        "user_prompt",
        "world_model",
    }
    for key in forbidden_keys:
        assert f'"{key}"' not in encoded
