"""Pure, deterministic runner for typed agent evaluation scenarios."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.editing_errors import (
    AffectedEntitiesMismatchError,
    EditingError,
    InvalidPatchError,
    NonJsonValueError,
    PatchModelMismatchError,
    ProtectedPathError,
    RevisionConflictError,
)
from ai_parametric_architect.domain.guardrails import (
    ModelComplexityError,
    ModelComplexityPolicy,
    StrictJsonTreeGuard,
)
from ai_parametric_architect.domain.issues import ValidationReport
from ai_parametric_architect.domain.patch_impacts import derive_affected_entity_ids
from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.planning_errors import PlanningError
from ai_parametric_architect.domain.revisions import ModelRevision
from ai_parametric_architect.editing.pointers import decode_pointer
from ai_parametric_architect.evaluation.metrics import (
    EvaluationMetrics,
    IntentExtractionAccuracy,
    PatchValidationSuccessRate,
    PlanValidity,
)
from ai_parametric_architect.evaluation.scenarios import Scenario
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.ports.patching import PatchEngine
from ai_parametric_architect.ports.validation import Validator

_PROTECTED_ROOT_MEMBERS = frozenset({"geometry_settings", "model_id", "revision", "schema_version"})


class IntentAgent(Protocol):
    """Minimal injection boundary implemented by RequirementAgent."""

    def run(self, value: str) -> DesignIntent: ...


class FloorPlanAgent(Protocol):
    """Minimal injection boundary implemented by ArchitecturePlannerAgent."""

    def run(self, value: DesignIntent) -> FloorPlanProposal: ...


class PatchGenerator(Protocol):
    """Detached patch-generation boundary implemented by PatchGeneratorAgent."""

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None: ...


class PatchCandidateValidator(Protocol):
    """Validate one detached proposal against a supplied immutable revision."""

    def validate(
        self,
        proposal: PatchProposal,
        current_revision: ModelRevision,
    ) -> ValidationReport: ...


class EvaluationStage(StrEnum):
    INTENT = "intent"
    PLAN = "plan"
    PATCH = "patch"


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    """Observable stage failure; never contains hidden reasoning or chain-of-thought."""

    stage: EvaluationStage
    code: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    """Immutable outputs and observations for one scenario."""

    scenario_index: int
    scenario: Scenario
    extracted_intent: DesignIntent | None
    floor_plan: FloorPlanProposal | None
    patch_proposal: PatchProposal | None
    intent_matches: bool
    plan_valid: bool
    patch_valid: bool
    validation_issue_codes: tuple[str, ...]
    failures: tuple[EvaluationFailure, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_index": self.scenario_index,
            "scenario": self.scenario.to_dict(),
            "outputs": {
                "intent": (
                    None if self.extracted_intent is None else self.extracted_intent.to_dict()
                ),
                "floor_plan": None if self.floor_plan is None else self.floor_plan.to_dict(),
                "patch_proposal": (
                    None if self.patch_proposal is None else self.patch_proposal.to_dict()
                ),
            },
            "observations": {
                "intent_matches": self.intent_matches,
                "plan_valid": self.plan_valid,
                "patch_valid": self.patch_valid,
                "validation_issue_codes": list(self.validation_issue_codes),
            },
            "failures": [failure.to_dict() for failure in self.failures],
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Immutable evaluation outputs plus the required aggregate metric set."""

    scenarios: tuple[ScenarioEvaluation, ...]
    metrics: EvaluationMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_count": len(self.scenarios),
            "metrics": self.metrics.to_dict(),
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


@dataclass(frozen=True, slots=True)
class DetachedPatchValidator:
    """Apply to a copy and run core validation, without repository or commit access."""

    patch_engine: PatchEngine = field(repr=False)
    model_validator: Validator = field(repr=False)
    json_guard: StrictJsonTreeGuard = field(default_factory=StrictJsonTreeGuard, repr=False)
    complexity_policy: ModelComplexityPolicy = field(
        default_factory=ModelComplexityPolicy,
        repr=False,
    )

    def validate(
        self,
        proposal: PatchProposal,
        current_revision: ModelRevision,
    ) -> ValidationReport:
        if proposal.base_model_id != current_revision.model_id:
            raise PatchModelMismatchError(
                "Patch proposal is bound to a different model.",
                path="/base_model_id",
                details={
                    "base_model_id": proposal.base_model_id,
                    "target_model_id": current_revision.model_id,
                },
            )
        if proposal.base_revision != current_revision.revision_number:
            raise RevisionConflictError(
                current_revision.model_id,
                proposal.base_revision,
                current_revision.revision_number,
            )
        try:
            self.complexity_policy.require_patch_operations(len(proposal.operations))
        except ModelComplexityError as error:
            raise InvalidPatchError(
                str(error),
                path=error.path,
                details={**error.details, "reason": error.code},
            ) from error
        _ensure_mutable_paths(proposal)
        candidate_value = self.patch_engine.apply(
            current_revision.document,
            proposal.operations,
        )
        if not isinstance(candidate_value, dict):
            raise InvalidPatchError("A model patch must produce a JSON object document.")
        candidate = candidate_value
        try:
            self.json_guard.require(candidate)
        except NonJsonValueError as error:
            raise InvalidPatchError(
                f"Patch candidate is not JSON-compatible: {error}",
                path=error.path,
                details=error.details,
            ) from error
        candidate["revision"] = current_revision.revision_number + 1
        try:
            self.complexity_policy.require_model(candidate)
        except ModelComplexityError as error:
            raise InvalidPatchError(
                str(error),
                path=error.path,
                details={**error.details, "reason": error.code},
            ) from error
        report = self.model_validator.validate(candidate)
        if report.valid:
            affected_entity_ids = derive_affected_entity_ids(
                current_revision.document,
                candidate,
            )
            if frozenset(proposal.affected_entity_ids) != frozenset(affected_entity_ids):
                raise AffectedEntitiesMismatchError(
                    "Patch affected entities do not match the validated document delta.",
                    path="/affected_entity_ids",
                    details={
                        "actual": list(proposal.affected_entity_ids),
                        "expected": list(affected_entity_ids),
                    },
                )
        return report


@dataclass(frozen=True, slots=True)
class EvaluationRunner:
    """Evaluate agents as pure proposal producers against one supplied snapshot."""

    intent_agent: IntentAgent = field(repr=False)
    floor_plan_agent: FloorPlanAgent = field(repr=False)
    patch_generator: PatchGenerator = field(repr=False)
    patch_validator: PatchCandidateValidator = field(repr=False)
    intent_metric: IntentExtractionAccuracy = field(
        default_factory=IntentExtractionAccuracy,
        repr=False,
    )
    plan_metric: PlanValidity = field(default_factory=PlanValidity, repr=False)
    patch_metric: PatchValidationSuccessRate = field(
        default_factory=PatchValidationSuccessRate,
        repr=False,
    )

    def run(
        self,
        scenarios: Sequence[Scenario],
        current_revision: ModelRevision,
    ) -> EvaluationReport:
        scenario_values = tuple(scenarios)
        if not scenario_values:
            raise ValueError("Evaluation requires at least one scenario.")
        if not all(isinstance(scenario, Scenario) for scenario in scenario_values):
            raise TypeError("Evaluation scenarios must contain Scenario values.")
        if not isinstance(current_revision, ModelRevision):
            raise TypeError("Evaluation current_revision must be a ModelRevision.")

        results = tuple(
            self._evaluate(index, scenario, current_revision)
            for index, scenario in enumerate(scenario_values)
        )
        metrics = EvaluationMetrics(
            intent_extraction_accuracy=self.intent_metric.summarize(
                result.intent_matches for result in results
            ),
            plan_validity=self.plan_metric.summarize(result.plan_valid for result in results),
            patch_validation_success_rate=self.patch_metric.summarize(
                result.patch_valid for result in results
            ),
        )
        return EvaluationReport(scenarios=results, metrics=metrics)

    def _evaluate(
        self,
        index: int,
        scenario: Scenario,
        current_revision: ModelRevision,
    ) -> ScenarioEvaluation:
        try:
            intent = self.intent_agent.run(scenario.input_requirement)
        except PlanningError as error:
            return _stopped_result(index, scenario, _domain_failure(EvaluationStage.INTENT, error))
        if type(intent) is not DesignIntent:
            return _stopped_result(
                index,
                scenario,
                _contract_failure(EvaluationStage.INTENT, "DesignIntent", intent),
            )
        intent_matches = self.intent_metric.matches(intent, scenario)

        try:
            floor_plan = self.floor_plan_agent.run(intent)
        except PlanningError as error:
            return _stopped_result(
                index,
                scenario,
                _domain_failure(EvaluationStage.PLAN, error),
                extracted_intent=intent,
                intent_matches=intent_matches,
            )
        if type(floor_plan) is not FloorPlanProposal:
            return _stopped_result(
                index,
                scenario,
                _contract_failure(EvaluationStage.PLAN, "FloorPlanProposal", floor_plan),
                extracted_intent=intent,
                intent_matches=intent_matches,
            )
        plan_valid = self.plan_metric.is_valid(floor_plan, scenario)

        try:
            proposal = self.patch_generator.generate(floor_plan, current_revision)
        except (PlanningError, EditingError) as error:
            return _stopped_result(
                index,
                scenario,
                _domain_failure(EvaluationStage.PATCH, error),
                extracted_intent=intent,
                floor_plan=floor_plan,
                intent_matches=intent_matches,
                plan_valid=plan_valid,
            )
        if proposal is None:
            return _stopped_result(
                index,
                scenario,
                EvaluationFailure(
                    stage=EvaluationStage.PATCH,
                    code="PATCH_NOT_PRODUCED",
                    path="/patch_proposal",
                    message="Patch generator returned no proposal.",
                ),
                extracted_intent=intent,
                floor_plan=floor_plan,
                intent_matches=intent_matches,
                plan_valid=plan_valid,
            )
        if type(proposal) is not PatchProposal:
            return _stopped_result(
                index,
                scenario,
                _contract_failure(EvaluationStage.PATCH, "PatchProposal", proposal),
                extracted_intent=intent,
                floor_plan=floor_plan,
                intent_matches=intent_matches,
                plan_valid=plan_valid,
            )

        try:
            validation = self.patch_validator.validate(proposal, current_revision)
        except (PlanningError, EditingError) as error:
            return _stopped_result(
                index,
                scenario,
                _domain_failure(EvaluationStage.PATCH, error),
                extracted_intent=intent,
                floor_plan=floor_plan,
                patch_proposal=proposal,
                intent_matches=intent_matches,
                plan_valid=plan_valid,
            )
        if not isinstance(validation, ValidationReport):
            return _stopped_result(
                index,
                scenario,
                _contract_failure(EvaluationStage.PATCH, "ValidationReport", validation),
                extracted_intent=intent,
                floor_plan=floor_plan,
                patch_proposal=proposal,
                intent_matches=intent_matches,
                plan_valid=plan_valid,
            )
        issue_codes = tuple(issue.code for issue in validation.issues)
        failures: tuple[EvaluationFailure, ...] = ()
        if not validation.valid:
            failures = (
                EvaluationFailure(
                    stage=EvaluationStage.PATCH,
                    code="PATCH_VALIDATION_FAILED",
                    message=f"Patch validation returned {validation.error_count} error(s).",
                ),
            )
        return ScenarioEvaluation(
            scenario_index=index,
            scenario=scenario,
            extracted_intent=intent,
            floor_plan=floor_plan,
            patch_proposal=proposal,
            intent_matches=intent_matches,
            plan_valid=plan_valid,
            patch_valid=validation.valid,
            validation_issue_codes=issue_codes,
            failures=failures,
        )


def _ensure_mutable_paths(proposal: PatchProposal) -> None:
    for index, operation in enumerate(proposal.operations):
        try:
            tokens = decode_pointer(operation.path)
        except InvalidPatchError as error:
            raise InvalidPatchError(
                str(error),
                path=error.path,
                details={**error.details, "operation_index": index},
            ) from error
        if not tokens:
            raise ProtectedPathError(
                "Replacing the model document root is not allowed.",
                path=operation.path,
                details={"operation_index": index, "protected_member": "<root>"},
            )
        if tokens[0] in _PROTECTED_ROOT_MEMBERS:
            raise ProtectedPathError(
                f"Patch path targets protected member {tokens[0]!r}.",
                path=operation.path,
                details={"operation_index": index, "protected_member": tokens[0]},
            )


def _domain_failure(
    stage: EvaluationStage,
    error: PlanningError | EditingError,
) -> EvaluationFailure:
    return EvaluationFailure(
        stage=stage,
        code=error.code,
        path=error.path,
        message=str(error),
    )


def _contract_failure(
    stage: EvaluationStage,
    expected_type: str,
    actual: object,
) -> EvaluationFailure:
    return EvaluationFailure(
        stage=stage,
        code="EVALUATION_DEPENDENCY_CONTRACT_VIOLATION",
        path=f"/{stage.value}",
        message=(
            f"Evaluation dependency returned {type(actual).__name__}; expected {expected_type}."
        ),
    )


def _stopped_result(
    index: int,
    scenario: Scenario,
    failure: EvaluationFailure,
    *,
    extracted_intent: DesignIntent | None = None,
    floor_plan: FloorPlanProposal | None = None,
    patch_proposal: PatchProposal | None = None,
    intent_matches: bool = False,
    plan_valid: bool = False,
) -> ScenarioEvaluation:
    return ScenarioEvaluation(
        scenario_index=index,
        scenario=scenario,
        extracted_intent=extracted_intent,
        floor_plan=floor_plan,
        patch_proposal=patch_proposal,
        intent_matches=intent_matches,
        plan_valid=plan_valid,
        patch_valid=False,
        validation_issue_codes=(),
        failures=(failure,),
    )
