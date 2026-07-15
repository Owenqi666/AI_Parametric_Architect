from __future__ import annotations

import json

from ai_parametric_architect.domain import (
    DesignIntent,
    GeometryPrecisionPolicy,
    RequirementParseError,
)
from ai_parametric_architect.evaluation.planning_metrics import (
    PlanningMetricContext,
    PlanningMetricsEvaluator,
)
from ai_parametric_architect.planning import PlanningRules
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.showcase import (
    ShowcaseCase,
    ShowcaseExecution,
    ShowcaseScenarioEvidence,
    ShowcaseSystemEvidence,
    build_planning_showcase,
    canonical_proposal_digest,
)
from ai_parametric_architect.showcase_generation import build_preview_artifact

SECRET = "sk-showcase-must-never-leak"


class _FailingIntentAgent:
    def run(self, value: str) -> DesignIntent:
        raise RequirementParseError(
            f"provider failure containing {SECRET}",
            path="/input_requirement",
            details={"api_key": SECRET, "provider_output": SECRET},
        )


class _UnusedPlanAgent:
    def run(self, value: DesignIntent) -> FloorPlanProposal:
        raise AssertionError("planner must not run after intent rejection")


def _evidence(
    case: ShowcaseCase,
    intent: DesignIntent,
    proposal: FloorPlanProposal,
) -> ShowcaseScenarioEvidence:
    rules = PlanningRules()
    context = PlanningMetricContext.from_threshold_source(
        context_id="showcase-security-v1",
        source=rules,
        precision=GeometryPrecisionPolicy(linear_tolerance=1e-9, decimal_places=9),
        max_runs=1,
    )
    return ShowcaseScenarioEvidence(
        metric_context=context,
        systems=(
            ShowcaseSystemEvidence(
                system_id="unused-system",
                strategy=proposal.strategy,
                proposal_digest=canonical_proposal_digest(proposal),
                report=PlanningMetricsEvaluator(context).evaluate((proposal,)),
            ),
        ),
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(member) for member in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(member) for member in value))
    return set()


def test_known_failures_exclude_exception_text_details_and_secrets() -> None:
    artifact = build_planning_showcase(
        cases=(ShowcaseCase("secure-case", "Secure case", "untrusted requirement"),),
        execution=ShowcaseExecution(
            intent_agent_name="failing-agent",
            intent_agent_version="1.0.0",
            floor_plan_agent_name="unused-agent",
            floor_plan_agent_version="1.0.0",
            planner_strategy="unused-strategy",
            rules_version="1.0.0",
            random_seed=0,
        ),
        intent_agent=_FailingIntentAgent(),
        floor_plan_agent=_UnusedPlanAgent(),
        evidence_factory=_evidence,
    )
    encoded = json.dumps(artifact.to_dict(), ensure_ascii=False, sort_keys=True)

    assert SECRET not in encoded
    assert "provider failure" not in encoded
    assert "api_key" not in encoded
    assert "provider_output" not in encoded
    assert artifact.scenarios[0].failure is not None
    assert artifact.scenarios[0].failure.to_dict() == {
        "stage": "intent",
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "/input_requirement",
    }


def test_preview_artifact_contains_no_world_model_or_write_contract_fields() -> None:
    payload = build_preview_artifact().to_dict()
    forbidden = {
        "affected_entity_ids",
        "base_model_id",
        "base_revision",
        "commit",
        "model_id",
        "operations",
        "patch",
        "revision",
        "root_building_id",
        "source_model",
    }

    assert _all_keys(payload).isdisjoint(forbidden)


def test_preview_generation_is_deterministic() -> None:
    first = build_preview_artifact().to_dict()
    second = build_preview_artifact().to_dict()

    assert first == second
