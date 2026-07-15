from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from ai_parametric_architect.benchmark.models import (
    BenchmarkBudget,
    BenchmarkExecutionMode,
    BenchmarkFailure,
    BenchmarkMetricSummary,
    BenchmarkRuntimeSummary,
    BenchmarkStage,
    BenchmarkSystemDescriptor,
    BenchmarkTrack,
    BenchmarkTrackObservation,
)


def _descriptor(
    *,
    mode: BenchmarkExecutionMode = BenchmarkExecutionMode.DETERMINISTIC,
    provider: str | None = None,
    model: str | None = None,
    random_seed: int | None = 0,
) -> BenchmarkSystemDescriptor:
    return BenchmarkSystemDescriptor(
        system_id="rule-v2",
        system_version="1.0.0",
        intent_agent_name="rule-parser",
        intent_agent_version="1.0.0",
        floor_plan_agent_name="architecture-planner",
        floor_plan_agent_version="2.0.0",
        planner_strategy="rule-based-single-row-v1",
        rules_version="1.0.0",
        random_seed=random_seed,
        execution_mode=mode,
        provider=provider,
        model=model,
    )


def test_system_descriptor_serializes_explicit_reproducibility_metadata() -> None:
    descriptor = _descriptor()

    assert descriptor.deterministic
    assert descriptor.to_dict() == {
        "system_id": "rule-v2",
        "system_version": "1.0.0",
        "intent_agent": {"name": "rule-parser", "version": "1.0.0"},
        "floor_plan_agent": {"name": "architecture-planner", "version": "2.0.0"},
        "planner_configuration": {
            "strategy": "rule-based-single-row-v1",
            "rules_version": "1.0.0",
            "random_seed": 0,
        },
        "execution_mode": "deterministic",
        "deterministic": True,
        "provider": None,
        "model": None,
        "prompt_version": None,
    }
    with pytest.raises(FrozenInstanceError):
        cast(Any, descriptor).system_id = "changed"


def test_real_nondeterministic_descriptor_requires_provider_and_model() -> None:
    with pytest.raises(ValueError, match="provider and model"):
        _descriptor(
            mode=BenchmarkExecutionMode.REAL_NONDETERMINISTIC,
            random_seed=None,
        )

    descriptor = _descriptor(
        mode=BenchmarkExecutionMode.REAL_NONDETERMINISTIC,
        provider="openai",
        model="gpt-test",
        random_seed=0,
    )

    assert not descriptor.deterministic
    assert descriptor.to_dict()["execution_mode"] == "real_nondeterministic"


def test_deterministic_descriptor_requires_explicit_seed() -> None:
    with pytest.raises(ValueError, match="random seed"):
        _descriptor(random_seed=None)


def test_budget_preflights_individual_and_product_limits() -> None:
    budget = BenchmarkBudget(max_cases=2, max_systems=2, max_trials=3, max_attempts=8)

    assert budget.require(case_count=2, system_count=2, trials=2) == 8
    with pytest.raises(ValueError, match="attempt count"):
        budget.require(case_count=2, system_count=2, trials=3)
    with pytest.raises(ValueError, match="positive integer"):
        budget.require(case_count=True, system_count=1, trials=1)


def test_failure_and_observation_are_redacted_allowlist_values() -> None:
    failure = BenchmarkFailure(
        stage=BenchmarkStage.INTENT,
        code="REQUIREMENT_PARSE_FAILED",
        path="/input_requirement",
    )
    observation = BenchmarkTrackObservation(
        track=BenchmarkTrack.END_TO_END,
        planning_succeeded=False,
        plan_valid=False,
        proposal_digest=None,
        parse_runtime_ns=7,
        plan_runtime_ns=None,
        total_runtime_ns=7,
        failure=failure,
    )

    assert failure.to_dict() == {
        "stage": "intent",
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "/input_requirement",
    }
    assert set(observation.to_dict()) == {
        "track",
        "planning_succeeded",
        "plan_valid",
        "proposal_digest",
        "runtime_ns",
        "failure",
    }
    failure_payload = cast(dict[str, object], observation.to_dict()["failure"])
    assert "message" not in failure_payload
    assert "details" not in failure_payload


def test_metric_summary_keeps_attempt_denominator_and_sample_coverage_separate() -> None:
    metric = BenchmarkMetricSummary(
        name="constraint_satisfaction_score",
        value=0.75,
        attempt_count=4,
        covered_attempt_count=2,
        sample_count=2,
    )

    assert metric.coverage == 0.5
    assert metric.to_dict()["attempt_count"] == 4
    assert metric.to_dict()["sample_count"] == 2

    with pytest.raises(ValueError, match="cannot contain samples"):
        BenchmarkMetricSummary(
            name="constraint_satisfaction_score",
            value=None,
            attempt_count=4,
            covered_attempt_count=1,
            sample_count=1,
            reason="NO_SAMPLE",
        )


@pytest.mark.parametrize(
    ("override", "error_type", "message"),
    [
        ({"system_id": "Not_Canonical"}, ValueError, "system_id"),
        ({"system_version": ""}, ValueError, "system_version"),
        ({"execution_mode": "deterministic"}, TypeError, "execution_mode"),
        ({"provider": ""}, ValueError, "provider"),
        ({"random_seed": -1}, ValueError, "random_seed"),
    ],
)
def test_system_descriptor_rejects_invalid_metadata(
    override: dict[str, object],
    error_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "system_id": "rule-v2",
        "system_version": "1.0.0",
        "intent_agent_name": "rule-parser",
        "intent_agent_version": "1.0.0",
        "floor_plan_agent_name": "architecture-planner",
        "floor_plan_agent_version": "2.0.0",
        "planner_strategy": "rule-based-single-row-v1",
        "rules_version": "1.0.0",
        "random_seed": 0,
        "execution_mode": BenchmarkExecutionMode.DETERMINISTIC,
    }
    values.update(override)

    with pytest.raises(error_type, match=message):
        BenchmarkSystemDescriptor(**cast(Any, values))


def test_budget_rejects_each_individual_limit() -> None:
    budget = BenchmarkBudget(max_cases=1, max_systems=1, max_trials=1, max_attempts=1)

    with pytest.raises(ValueError, match="case count"):
        budget.require(case_count=2, system_count=1, trials=1)
    with pytest.raises(ValueError, match="system count"):
        budget.require(case_count=1, system_count=2, trials=1)
    with pytest.raises(ValueError, match="trial count"):
        budget.require(case_count=1, system_count=1, trials=2)
    with pytest.raises(ValueError, match="positive integer"):
        BenchmarkBudget(max_cases=0)


@pytest.mark.parametrize(
    ("kwargs", "error_type", "message"),
    [
        ({"stage": "intent"}, TypeError, "stage"),
        ({"code": "not-canonical"}, ValueError, "code"),
        ({"path": "not-a-pointer"}, ValueError, "path"),
    ],
)
def test_failure_rejects_noncanonical_fields(
    kwargs: dict[str, object],
    error_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "stage": BenchmarkStage.INTENT,
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "",
    }
    values.update(kwargs)

    with pytest.raises(error_type, match=message):
        BenchmarkFailure(**cast(Any, values))


@pytest.mark.parametrize(
    ("override", "error_type", "message"),
    [
        ({"track": "end_to_end"}, TypeError, "track"),
        ({"planning_succeeded": 1}, TypeError, "boolean"),
        ({"planning_succeeded": False, "plan_valid": True}, ValueError, "valid plan"),
        ({"proposal_digest": "bad"}, ValueError, "proposal_digest"),
        ({"total_runtime_ns": 6}, ValueError, "total runtime"),
        (
            {"track": BenchmarkTrack.ORACLE_INTENT, "parse_runtime_ns": 2},
            ValueError,
            "Oracle-intent",
        ),
        ({"plan_runtime_ns": None, "total_runtime_ns": 2}, ValueError, "measured plan"),
    ],
)
def test_track_observation_rejects_inconsistent_values(
    override: dict[str, object],
    error_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "track": BenchmarkTrack.END_TO_END,
        "planning_succeeded": True,
        "plan_valid": True,
        "proposal_digest": "a" * 64,
        "parse_runtime_ns": 2,
        "plan_runtime_ns": 3,
        "total_runtime_ns": 5,
    }
    values.update(override)

    with pytest.raises(error_type, match=message):
        BenchmarkTrackObservation(**cast(Any, values))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"covered_attempt_count": 3}, "coverage"),
        ({"minimum_ns": 1}, "without samples"),
        ({"reason": None}, "requires a reason"),
    ],
)
def test_empty_runtime_summary_rejects_inconsistent_values(
    override: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "name": "plan_runtime_ns",
        "attempt_count": 2,
        "covered_attempt_count": 0,
        "sample_count": 0,
        "minimum_ns": None,
        "median_ns": None,
        "p95_ns": None,
        "maximum_ns": None,
        "total_ns": None,
        "reason": "NO_RUNTIME_SAMPLES",
    }
    values.update(override)

    with pytest.raises(ValueError, match=message):
        BenchmarkRuntimeSummary(**cast(Any, values))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"covered_attempt_count": 0}, "requires coverage"),
        ({"reason": "unexpected"}, "requires coverage"),
        ({"minimum_ns": -1}, "non-negative"),
        ({"median_ns": 4}, "quantiles"),
        ({"total_ns": 2}, "total"),
    ],
)
def test_sampled_runtime_summary_rejects_inconsistent_values(
    override: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "name": "plan_runtime_ns",
        "attempt_count": 2,
        "covered_attempt_count": 2,
        "sample_count": 2,
        "minimum_ns": 1,
        "median_ns": 2,
        "p95_ns": 3,
        "maximum_ns": 3,
        "total_ns": 4,
        "reason": None,
    }
    values.update(override)

    with pytest.raises(ValueError, match=message):
        BenchmarkRuntimeSummary(**cast(Any, values))
