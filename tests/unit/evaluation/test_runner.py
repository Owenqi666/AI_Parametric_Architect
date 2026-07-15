from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    AffectedEntitiesMismatchError,
    DesignIntent,
    InvalidPatchError,
    ModelDocument,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlanningContextError,
    ProtectedPathError,
    RequirementParseError,
    RevisionConflictError,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.evaluation import (
    DetachedPatchValidator,
    EvaluationRunner,
    EvaluationStage,
    Scenario,
)
from ai_parametric_architect.evaluation.runner import (
    FloorPlanAgent,
    IntentAgent,
    PatchCandidateValidator,
    PatchGenerator,
)
from ai_parametric_architect.planning import FloorPlanProposal, RuleBasedFloorPlanPlanner


def _intent(*, area: int = 60) -> DesignIntent:
    return DesignIntent(building_type="house", area=area, rooms=("bedroom",))


def _scenario(*, area: int = 60) -> Scenario:
    intent = _intent(area=area)
    return Scenario("Create a 60 sqm one bedroom house", intent, ())


def _revision() -> ModelRevision:
    return ModelRevision(
        model_id="mdl_eval",
        revision_number=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_revision=None,
        document={"model_id": "mdl_eval", "revision": 0, "extensions": {}},
    )


def _proposal(
    *,
    model_id: str = "mdl_eval",
    revision: int = 0,
    operation: PatchOperation | None = None,
    affected_entity_ids: tuple[str, ...] = (),
) -> PatchProposal:
    return PatchProposal(
        base_model_id=model_id,
        base_revision=revision,
        operations=(
            PatchOperation("add", "/extensions/evaluation", {"status": "proposed"})
            if operation is None
            else operation,
        ),
        provenance="evaluation:test",
        rationale="Evaluate a detached proposal.",
        affected_entity_ids=affected_entity_ids,
    )


class StaticIntentAgent:
    def __init__(self, value: DesignIntent) -> None:
        self.value = value

    def run(self, value: str) -> DesignIntent:
        return self.value


class StaticFloorPlanAgent:
    def run(self, value: DesignIntent) -> FloorPlanProposal:
        return RuleBasedFloorPlanPlanner().plan(value)


class StaticPatchGenerator:
    def __init__(self, value: PatchProposal | None) -> None:
        self.value = value

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        return self.value


class StaticPatchValidator:
    def __init__(self, report: ValidationReport) -> None:
        self.report = report

    def validate(
        self,
        proposal: PatchProposal,
        current_revision: ModelRevision,
    ) -> ValidationReport:
        return self.report


class FailingIntentAgent:
    def run(self, value: str) -> DesignIntent:
        raise RequirementParseError(
            "Requirement is unsupported.",
            path="/input_requirement",
            details={"reason": "UNSUPPORTED"},
        )


class FailingPatchValidator:
    def validate(
        self,
        proposal: PatchProposal,
        current_revision: ModelRevision,
    ) -> ValidationReport:
        raise InvalidPatchError("Detached patch failed.", path="/operations/0")


class FailingFloorPlanAgent:
    def run(self, value: DesignIntent) -> FloorPlanProposal:
        raise PlanningContextError("Plan failed.", path="/intent")


class FailingPatchGenerator:
    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        raise InvalidPatchError("Patch generation failed.", path="/patch_proposal")


class WrongIntentAgent:
    def run(self, value: str) -> object:
        return object()


class WrongFloorPlanAgent:
    def run(self, value: DesignIntent) -> object:
        return object()


class WrongPatchGenerator:
    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> object:
        return object()


class WrongPatchValidator:
    def validate(
        self,
        proposal: PatchProposal,
        current_revision: ModelRevision,
    ) -> object:
        return object()


class UnexpectedFailureAgent:
    def run(self, value: str) -> DesignIntent:
        raise RuntimeError("dependency bug")


class SubDesignIntent(DesignIntent):
    """A structurally valid but contract-forbidden domain subclass."""


class SubFloorPlanProposal(FloorPlanProposal):
    """A structurally valid but contract-forbidden plan subclass."""


def _runner(
    *,
    intent_agent: IntentAgent | None = None,
    floor_plan_agent: FloorPlanAgent | None = None,
    proposal: PatchProposal | None = None,
    patch_validator: PatchCandidateValidator | None = None,
) -> EvaluationRunner:
    report = ValidationReport(model_id="mdl_eval", revision=1, issues=())
    return EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()) if intent_agent is None else intent_agent,
        floor_plan_agent=(StaticFloorPlanAgent() if floor_plan_agent is None else floor_plan_agent),
        patch_generator=StaticPatchGenerator(_proposal() if proposal is None else proposal),
        patch_validator=(
            StaticPatchValidator(report) if patch_validator is None else patch_validator
        ),
    )


def test_runner_produces_immutable_structured_metrics_deterministically() -> None:
    runner = _runner()

    first = runner.run((_scenario(),), _revision())
    second = runner.run((_scenario(),), _revision())

    assert first == second
    assert first.metrics.intent_extraction_accuracy.value == 1.0
    assert first.metrics.plan_validity.value == 1.0
    assert first.metrics.patch_validation_success_rate.value == 1.0
    assert first.scenarios[0].failures == ()
    assert first.to_dict()["scenario_count"] == 1
    assert first.to_dict() == second.to_dict()


def test_wrong_intent_is_scored_but_does_not_hide_later_stage_results() -> None:
    runner = _runner(intent_agent=StaticIntentAgent(_intent(area=61)))

    report = runner.run((_scenario(),), _revision())

    result = report.scenarios[0]
    assert not result.intent_matches
    assert not result.plan_valid
    assert result.patch_valid
    assert report.metrics.intent_extraction_accuracy.value == 0.0
    assert report.metrics.patch_validation_success_rate.value == 1.0


def test_known_intent_failure_is_structured_and_stops_dependent_stages() -> None:
    report = _runner(intent_agent=FailingIntentAgent()).run((_scenario(),), _revision())

    result = report.scenarios[0]
    assert result.extracted_intent is None
    assert not result.intent_matches
    assert not result.plan_valid
    assert not result.patch_valid
    assert result.failures[0].stage is EvaluationStage.INTENT
    assert result.failures[0].code == "REQUIREMENT_PARSE_FAILED"
    assert result.failures[0].path == "/input_requirement"
    assert result.failures[0].to_dict() == {
        "stage": "intent",
        "code": "REQUIREMENT_PARSE_FAILED",
        "path": "/input_requirement",
        "message": "Requirement is unsupported.",
    }


def test_known_plan_and_patch_generation_failures_are_structured() -> None:
    valid_report = ValidationReport(model_id="mdl_eval", revision=1, issues=())
    plan_failure = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=FailingFloorPlanAgent(),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())
    patch_failure = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=FailingPatchGenerator(),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())

    assert plan_failure.scenarios[0].failures[0].code == "PLANNING_CONTEXT_INVALID"
    assert plan_failure.scenarios[0].floor_plan is None
    assert patch_failure.scenarios[0].failures[0].code == "INVALID_PATCH"
    assert patch_failure.scenarios[0].floor_plan is not None


def test_dependency_contract_violations_are_structured_by_stage() -> None:
    valid_report = ValidationReport(model_id="mdl_eval", revision=1, issues=())
    wrong_intent = EvaluationRunner(
        intent_agent=cast(IntentAgent, WrongIntentAgent()),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())
    wrong_plan = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=cast(FloorPlanAgent, WrongFloorPlanAgent()),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())
    wrong_patch = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=cast(PatchGenerator, WrongPatchGenerator()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())
    wrong_validation = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=cast(PatchCandidateValidator, WrongPatchValidator()),
    ).run((_scenario(),), _revision())

    failures = tuple(
        report.scenarios[0].failures[0]
        for report in (wrong_intent, wrong_plan, wrong_patch, wrong_validation)
    )
    assert tuple(failure.stage for failure in failures) == (
        EvaluationStage.INTENT,
        EvaluationStage.PLAN,
        EvaluationStage.PATCH,
        EvaluationStage.PATCH,
    )
    assert all(failure.code == "EVALUATION_DEPENDENCY_CONTRACT_VIOLATION" for failure in failures)


def test_runner_rejects_subclasses_at_typed_agent_boundaries() -> None:
    sub_intent = SubDesignIntent(
        building_type="house",
        area=60,
        rooms=("bedroom",),
    )
    ordinary_plan = RuleBasedFloorPlanPlanner().plan(_intent())
    sub_plan = SubFloorPlanProposal(
        intent=ordinary_plan.intent,
        rooms=ordinary_plan.rooms,
        spatial_constraints=ordinary_plan.spatial_constraints,
        orientation=ordinary_plan.orientation,
        strategy=ordinary_plan.strategy,
    )
    valid_report = ValidationReport(model_id="mdl_eval", revision=1, issues=())
    intent_result = EvaluationRunner(
        intent_agent=StaticIntentAgent(sub_intent),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())

    class SubPlanAgent:
        def run(self, value: DesignIntent) -> FloorPlanProposal:
            return sub_plan

    plan_result = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=SubPlanAgent(),
        patch_generator=StaticPatchGenerator(_proposal()),
        patch_validator=StaticPatchValidator(valid_report),
    ).run((_scenario(),), _revision())

    assert intent_result.scenarios[0].failures[0].path == "/intent"
    assert plan_result.scenarios[0].failures[0].path == "/plan"


def test_unexpected_dependency_bug_is_not_hidden() -> None:
    runner = _runner(intent_agent=UnexpectedFailureAgent())

    with pytest.raises(RuntimeError, match="dependency bug"):
        runner.run((_scenario(),), _revision())


def test_no_patch_is_a_stable_metric_failure() -> None:
    runner = EvaluationRunner(
        intent_agent=StaticIntentAgent(_intent()),
        floor_plan_agent=StaticFloorPlanAgent(),
        patch_generator=StaticPatchGenerator(None),
        patch_validator=StaticPatchValidator(
            ValidationReport(model_id="mdl_eval", revision=1, issues=())
        ),
    )

    result = runner.run((_scenario(),), _revision()).scenarios[0]

    assert result.intent_matches
    assert result.plan_valid
    assert not result.patch_valid
    assert result.failures[0].code == "PATCH_NOT_PRODUCED"


def test_invalid_validation_report_records_ordered_issue_codes() -> None:
    issue = ValidationIssue(
        code="ROOM_OVERLAP",
        severity=Severity.ERROR,
        message="Rooms overlap.",
        path="/entities/rooms",
    )
    validator = StaticPatchValidator(
        ValidationReport(model_id="mdl_eval", revision=1, issues=(issue,))
    )

    result = _runner(patch_validator=validator).run((_scenario(),), _revision()).scenarios[0]

    assert not result.patch_valid
    assert result.validation_issue_codes == ("ROOM_OVERLAP",)
    assert result.failures[0].code == "PATCH_VALIDATION_FAILED"


def test_patch_validation_domain_error_is_structured() -> None:
    result = (
        _runner(patch_validator=FailingPatchValidator())
        .run((_scenario(),), _revision())
        .scenarios[0]
    )

    assert result.patch_proposal == _proposal()
    assert result.failures[0].stage is EvaluationStage.PATCH
    assert result.failures[0].code == "INVALID_PATCH"
    assert result.failures[0].path == "/operations/0"


@pytest.mark.parametrize("scenarios", [(), cast(Any, (object(),))])
def test_runner_rejects_invalid_scenario_collections(scenarios: object) -> None:
    expected = ValueError if scenarios == () else TypeError

    with pytest.raises(expected):
        _runner().run(cast(Any, scenarios), _revision())


def test_runner_rejects_non_revision_context() -> None:
    with pytest.raises(TypeError):
        _runner().run((_scenario(),), cast(Any, object()))


class CapturingValidator:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def validate(self, model: ModelDocument) -> ValidationReport:
        snapshot = deepcopy(dict(model))
        self.documents.append(snapshot)
        return ValidationReport.create(model, ())


def test_detached_patch_validator_applies_to_copy_and_advances_candidate_revision() -> None:
    revision = _revision()
    original = revision.document
    model_validator = CapturingValidator()
    validator = DetachedPatchValidator(JsonPatchEngine(), model_validator)

    report = validator.validate(_proposal(), revision)

    assert report.valid
    assert revision.document == original
    assert model_validator.documents == [
        {
            "model_id": "mdl_eval",
            "revision": 1,
            "extensions": {"evaluation": {"status": "proposed"}},
        }
    ]


class RejectingValidator:
    def validate(self, model: ModelDocument) -> ValidationReport:
        return ValidationReport.create(
            model,
            (
                ValidationIssue(
                    code="TEST_INVALID",
                    severity=Severity.ERROR,
                    message="Rejected candidate.",
                    path="/entities/rooms/rom_a",
                    entity_ids=("rom_a",),
                ),
            ),
        )


def test_invalid_candidate_report_is_returned_before_impact_metadata_check() -> None:
    validator = DetachedPatchValidator(JsonPatchEngine(), RejectingValidator())

    report = validator.validate(_proposal(affected_entity_ids=("rom_fake",)), _revision())

    assert not report.valid
    assert tuple(issue.code for issue in report.issues) == ("TEST_INVALID",)


@pytest.mark.parametrize(
    ("proposal", "error_type"),
    [
        (_proposal(model_id="mdl_other"), InvalidPatchError),
        (_proposal(revision=1), RevisionConflictError),
        (
            _proposal(operation=PatchOperation("replace", "/revision", 9)),
            ProtectedPathError,
        ),
        (
            _proposal(operation=PatchOperation("replace", "", {})),
            ProtectedPathError,
        ),
        (
            _proposal(operation=PatchOperation("add", "/extensions/~2", {})),
            InvalidPatchError,
        ),
    ],
)
def test_detached_patch_validator_rejects_wrong_context_or_protected_paths(
    proposal: PatchProposal,
    error_type: type[Exception],
) -> None:
    validator = DetachedPatchValidator(JsonPatchEngine(), CapturingValidator())

    with pytest.raises(error_type):
        validator.validate(proposal, _revision())


class NonObjectPatchEngine:
    def apply(self, document: object, operations: object) -> object:
        return []


def test_detached_patch_validator_requires_object_candidate() -> None:
    validator = DetachedPatchValidator(
        cast(Any, NonObjectPatchEngine()),
        CapturingValidator(),
    )

    with pytest.raises(InvalidPatchError):
        validator.validate(_proposal(), _revision())


def test_detached_patch_validator_rejects_false_affected_entity_claim() -> None:
    revision = ModelRevision(
        model_id="mdl_eval",
        revision_number=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_revision=None,
        document={
            "model_id": "mdl_eval",
            "revision": 0,
            "entities": {
                "rooms": {
                    "rom_a": {
                        "id": "rom_a",
                        "entity_type": "room",
                        "usage": "living",
                    }
                },
                "walls": {"wal_a": {"id": "wal_a", "entity_type": "wall"}},
            },
            "extensions": {},
        },
    )
    dishonest = PatchProposal(
        base_model_id="mdl_eval",
        base_revision=0,
        operations=(PatchOperation("replace", "/entities/rooms/rom_a/usage", "bedroom"),),
        provenance="evaluation:test",
        rationale="Claim the wrong affected entity.",
        affected_entity_ids=("wal_a",),
    )
    validator = DetachedPatchValidator(JsonPatchEngine(), CapturingValidator())

    with pytest.raises(AffectedEntitiesMismatchError) as captured:
        validator.validate(dishonest, revision)

    assert captured.value.code == "PATCH_AFFECTED_ENTITIES_MISMATCH"
    assert captured.value.path == "/affected_entity_ids"
    assert captured.value.details == {"actual": ["wal_a"], "expected": ["rom_a"]}
