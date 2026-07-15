from __future__ import annotations

from typing import cast

import pytest

import ai_parametric_architect.composition as composition
from ai_parametric_architect.agents import RequirementAgent
from ai_parametric_architect.benchmark import (
    BenchmarkBudget,
    BenchmarkExecutionMode,
)
from ai_parametric_architect.infrastructure import OpenAIProviderConfig
from ai_parametric_architect.planning import (
    CP_SAT_STRATEGY,
    RULE_BASED_SPATIAL_STRATEGY,
    PlanningRules,
    RuleBasedRequirementParser,
)


def test_offline_benchmark_composition_does_not_construct_an_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_provider(*args: object, **kwargs: object) -> object:
        raise AssertionError("offline benchmark composition reached the network provider")

    monkeypatch.setattr(composition, "OpenAIResponsesProvider", unexpected_provider)
    rules = PlanningRules()
    runner = composition.create_planning_benchmark_runner(
        rules=rules,
        budget=BenchmarkBudget(
            max_cases=8,
            max_systems=3,
            max_trials=2,
            max_attempts=48,
        ),
    )
    rule_system = composition.create_rule_spatial_benchmark_system()
    cp_sat_system = composition.create_cp_sat_benchmark_system(rules=rules)

    assert runner.metric_context.context_id == composition.PLANNING_BENCHMARK_CONTEXT_ID
    assert runner.metric_context.max_runs == 2
    assert rule_system.descriptor.planner_strategy == RULE_BASED_SPATIAL_STRATEGY
    assert rule_system.descriptor.execution_mode is BenchmarkExecutionMode.DETERMINISTIC
    assert cp_sat_system.descriptor.planner_strategy == CP_SAT_STRATEGY
    assert cp_sat_system.descriptor.random_seed == rules.random_seed
    assert cp_sat_system.descriptor.provider is None


def test_openai_benchmark_composition_is_explicit_and_records_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[OpenAIProviderConfig] = []

    def fake_openai_agent(config: OpenAIProviderConfig) -> RequirementAgent:
        received.append(config)
        return RequirementAgent(RuleBasedRequirementParser())

    monkeypatch.setattr(composition, "create_openai_requirement_agent", fake_openai_agent)
    config = OpenAIProviderConfig(model="gpt-test")
    rules = PlanningRules(random_seed=7)

    system = composition.create_openai_cp_sat_benchmark_system(config, rules=rules)

    assert received == [config]
    assert system.descriptor.execution_mode is BenchmarkExecutionMode.REAL_NONDETERMINISTIC
    assert system.descriptor.provider == "openai-responses"
    assert system.descriptor.model == "gpt-test"
    assert system.descriptor.random_seed == 7
    assert "api_key" not in system.descriptor.to_dict()


def test_benchmark_composition_rejects_metric_trial_budget_above_implementation_limit() -> None:
    budget = BenchmarkBudget(
        max_cases=1,
        max_systems=1,
        max_trials=65,
        max_attempts=65,
    )

    with pytest.raises(ValueError, match="metric implementation budget"):
        composition.create_planning_benchmark_runner(budget=budget)


def test_composed_benchmark_components_have_no_world_write_capabilities() -> None:
    components = (
        composition.create_rule_spatial_benchmark_system(),
        composition.create_cp_sat_benchmark_system(),
        composition.create_planning_benchmark_runner(),
    )
    forbidden = {
        "apply_patch",
        "authorize",
        "commit",
        "commit_patch",
        "initialize",
        "repository",
    }

    for component in components:
        assert all(not hasattr(cast(object, component), name) for name in forbidden)
