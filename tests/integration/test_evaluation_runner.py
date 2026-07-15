from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from ai_parametric_architect.agents import (
    ArchitecturePlannerAgent,
    PatchGeneratorAgent,
    RequirementAgent,
)
from ai_parametric_architect.domain import DesignIntent, ModelRevision
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.evaluation import DetachedPatchValidator, EvaluationRunner, Scenario
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.planning import (
    RuleBasedFloorPlanPlanner,
    RuleBasedPlanner,
    RuleBasedRequirementParser,
)
from ai_parametric_architect.validation import ModelValidator


def test_evaluation_runner_exercises_existing_agents_and_full_validator_without_commit(
    valid_simple_house: dict[str, Any],
) -> None:
    original = deepcopy(valid_simple_house)
    revision = ModelRevision(
        model_id="mdl_simple_house",
        revision_number=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_revision=None,
        document=valid_simple_house,
    )
    expected_intent = DesignIntent(
        building_type="house",
        area=60,
        rooms=("bedroom",),
    )
    scenario = Scenario(
        input_requirement="Create a 60 sqm one bedroom house",
        expected_intent=expected_intent,
        expected_constraints=(),
    )
    runner = EvaluationRunner(
        intent_agent=RequirementAgent(RuleBasedRequirementParser()),
        floor_plan_agent=ArchitecturePlannerAgent(RuleBasedFloorPlanPlanner()),
        patch_generator=PatchGeneratorAgent(RuleBasedPlanner()),
        patch_validator=DetachedPatchValidator(
            JsonPatchEngine(),
            ModelValidator(ShapelyGeometryEngine()),
        ),
    )

    report = runner.run((scenario,), revision)

    assert report.metrics.intent_extraction_accuracy.value == 1.0
    assert report.metrics.plan_validity.value == 1.0
    assert report.metrics.patch_validation_success_rate.value == 1.0
    assert report.scenarios[0].validation_issue_codes == ()
    assert valid_simple_house == original
    assert revision.document == original
