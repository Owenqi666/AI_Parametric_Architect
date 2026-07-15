from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_parametric_architect.application import (
    EditingService,
    ModelValidationError,
    PatchedModelValidationError,
    RestoredModelValidationError,
)
from ai_parametric_architect.domain import (
    AuditActorType,
    InvalidPatchError,
    ModelComplexityPolicy,
    ModelDocument,
    ModelNotFoundError,
    NonJsonValueError,
    PatchModelMismatchError,
    PatchOperation,
    PatchProposal,
    ProtectedPathError,
    RevisionConflictError,
    Severity,
    TrustedAuditIdentity,
    ValidationIssue,
    ValidationReport,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.ports import PatchEngine
from ai_parametric_architect.repositories import InMemoryRevisionRepository

AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="test-editing-service",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:test-editing-service",
)


class FixedClock:
    def __init__(self) -> None:
        self._minute = 0

    def now(self) -> datetime:
        current = datetime(2026, 7, 14, 10, self._minute, tzinfo=UTC)
        self._minute += 1
        return current


class StubValidator:
    def __init__(
        self,
        reject_when: Callable[[ModelDocument], bool] | None = None,
    ) -> None:
        self._reject_when = reject_when

    def validate(self, model: ModelDocument) -> ValidationReport:
        issues = (
            (
                ValidationIssue(
                    code="TEST_INVALID",
                    severity=Severity.ERROR,
                    path="/name",
                    message="Rejected by test validator.",
                ),
            )
            if self._reject_when is not None and self._reject_when(model)
            else ()
        )
        return ValidationReport.create(model, issues)


class NonObjectPatchEngine:
    def apply(self, document: object, operations: Sequence[PatchOperation]) -> object:
        return []


class RecordingPatchEngine:
    def __init__(self) -> None:
        self.called = False

    def apply(self, document: object, operations: Sequence[PatchOperation]) -> object:
        self.called = True
        return document


def model(*, name: str = "Initial") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "model_id": "mdl_house",
        "revision": 0,
        "name": name,
    }


def proposal(
    *operations: PatchOperation,
    base_model_id: str = "mdl_house",
    base_revision: int = 0,
    affected_entity_ids: tuple[str, ...] = (),
) -> PatchProposal:
    return PatchProposal(
        base_model_id=base_model_id,
        base_revision=base_revision,
        operations=operations,
        provenance="source:architect-request",
        rationale="Apply requested design edit.",
        affected_entity_ids=affected_entity_ids,
    )


def service(
    *,
    validator: StubValidator | None = None,
    repository: InMemoryRevisionRepository | None = None,
    patch_engine: PatchEngine | None = None,
    complexity_policy: ModelComplexityPolicy | None = None,
) -> EditingService:
    return EditingService(
        validator=StubValidator() if validator is None else validator,
        repository=InMemoryRevisionRepository() if repository is None else repository,
        patch_engine=JsonPatchEngine() if patch_engine is None else patch_engine,
        clock=FixedClock(),
        complexity_policy=complexity_policy,
    )


def initialize(editing: EditingService) -> None:
    editing.initialize(
        model(),
        provenance="import:test",
        rationale="Start editing history.",
        audit_identity=AUDIT_IDENTITY,
    )


def test_initialize_exposes_current_revision_history_and_audit() -> None:
    editing = service()

    created = editing.initialize(
        model(),
        provenance="import:test",
        rationale="Start editing history.",
        audit_identity=AUDIT_IDENTITY,
    )

    assert created.revision_number == 0
    assert created.created_at == datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
    assert editing.current("mdl_house").document["name"] == "Initial"
    assert editing.revision("mdl_house", 0).revision_number == 0
    assert editing.audit_log("mdl_house")[0].provenance == "import:test"


def test_initialize_rejects_invalid_model_before_creating_history() -> None:
    editing = service(validator=StubValidator(lambda _model: True))

    with pytest.raises(ModelValidationError):
        initialize(editing)

    with pytest.raises(ModelNotFoundError):
        editing.current("mdl_house")


def test_initialize_defends_against_invalid_validator_contract() -> None:
    editing = service()

    with pytest.raises(ValueError, match="Validator accepted"):
        editing.initialize(
            {"schema_version": "1.0.0"},
            provenance="test",
            rationale="Invalid validator contract.",
            audit_identity=AUDIT_IDENTITY,
        )


def test_initialize_rejects_non_json_state_before_validation() -> None:
    editing = service()
    invalid = model()
    invalid["created_at"] = datetime(2026, 7, 14, tzinfo=UTC)

    with pytest.raises(NonJsonValueError):
        editing.initialize(
            invalid,
            provenance="test",
            rationale="Must remain JSON-only.",
            audit_identity=AUDIT_IDENTITY,
        )


def test_editing_service_enforces_model_budget_after_validator_acceptance() -> None:
    editing = service(complexity_policy=ModelComplexityPolicy(max_total_entities=1))
    oversized = model()
    oversized["entities"] = {"rooms": {"rom_a": {}, "rom_b": {}}}

    with pytest.raises(ModelValidationError) as error:
        editing.initialize(
            oversized,
            provenance="test",
            rationale="Application policy must not trust a permissive validator.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.report.issues[0].code == "MODEL_ENTITY_LIMIT_EXCEEDED"


@pytest.mark.parametrize(("provenance", "rationale"), [("", "why"), ("test", " ")])
def test_history_metadata_must_be_non_empty(provenance: str, rationale: str) -> None:
    editing = service()

    with pytest.raises(InvalidPatchError):
        editing.initialize(
            model(),
            provenance=provenance,
            rationale=rationale,
            audit_identity=AUDIT_IDENTITY,
        )


def test_successful_patch_validates_and_creates_next_revision() -> None:
    editing = service()
    initialize(editing)

    created = editing.apply_patch(
        "mdl_house",
        proposal(PatchOperation("replace", "/name", "Edited")),
        audit_identity=AUDIT_IDENTITY,
    )

    assert created.revision_number == 1
    assert created.parent_revision == 0
    assert created.document == {
        "schema_version": "1.0.0",
        "model_id": "mdl_house",
        "revision": 1,
        "name": "Edited",
    }
    audit = editing.audit_log("mdl_house")[-1]
    assert audit.details == {"operations": [{"op": "replace", "path": "/name"}]}


def test_stale_proposal_is_rejected_before_patch_application() -> None:
    editing = service()
    initialize(editing)
    editing.apply_patch(
        "mdl_house",
        proposal(PatchOperation("replace", "/name", "First")),
        audit_identity=AUDIT_IDENTITY,
    )

    with pytest.raises(RevisionConflictError):
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("remove", "/missing")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert editing.current("mdl_house").document["name"] == "First"
    assert len(editing.audit_log("mdl_house")) == 2


def test_editing_service_enforces_patch_budget_before_adapter_call() -> None:
    engine = RecordingPatchEngine()
    editing = service(
        patch_engine=engine,
        complexity_policy=ModelComplexityPolicy(max_patch_operations=1),
    )
    initialize(editing)

    with pytest.raises(InvalidPatchError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(
                PatchOperation("replace", "/name", "Edited"),
                PatchOperation("add", "/description", "Second operation"),
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details["reason"] == "PATCH_OPERATION_LIMIT_EXCEEDED"
    assert engine.called is False


def test_proposal_bound_to_another_model_is_rejected_before_patch_application() -> None:
    editing = service()
    initialize(editing)

    with pytest.raises(PatchModelMismatchError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(
                PatchOperation("replace", "/name", "Cross-model edit"),
                base_model_id="mdl_other",
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.code == "PATCH_MODEL_MISMATCH"
    assert error.value.details == {
        "base_model_id": "mdl_other",
        "target_model_id": "mdl_house",
    }
    assert editing.current("mdl_house").revision_number == 0


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/geometry_settings",
        "/geometry_settings/linear_tolerance",
        "/model_id",
        "/model_id/nested",
        "/revision",
        "/schema_version",
    ],
)
def test_identity_and_schema_members_are_protected(path: str) -> None:
    editing = service()
    initialize(editing)

    with pytest.raises(ProtectedPathError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("replace", path, "changed")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.path == path
    assert error.value.details["operation_index"] == 0
    assert editing.current("mdl_house").revision_number == 0


def test_protected_path_reports_correct_operation_index() -> None:
    editing = service()
    initialize(editing)

    with pytest.raises(ProtectedPathError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(
                PatchOperation("replace", "/name", "Changed"),
                PatchOperation("replace", "/revision", 99),
            ),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details["operation_index"] == 1
    assert editing.current("mdl_house").document["name"] == "Initial"


def test_malformed_pointer_is_rejected_before_any_mutation() -> None:
    editing = service()
    initialize(editing)

    with pytest.raises(InvalidPatchError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("add", "/bad~2key", 1)),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details["operation_index"] == 0
    assert editing.current("mdl_house").revision_number == 0


def test_invalid_patch_target_is_rejected_without_commit() -> None:
    editing = service()
    initialize(editing)

    with pytest.raises(InvalidPatchError):
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("remove", "/missing")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert editing.current("mdl_house").revision_number == 0
    assert len(editing.audit_log("mdl_house")) == 1


def test_patch_engine_must_return_an_object_model() -> None:
    editing = service(patch_engine=NonObjectPatchEngine())
    initialize(editing)

    with pytest.raises(InvalidPatchError, match="JSON object"):
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("replace", "/name", "Edited")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert editing.current("mdl_house").revision_number == 0


def test_invalid_patched_model_is_not_committed() -> None:
    editing = service(validator=StubValidator(lambda value: value.get("name") == "Invalid"))
    initialize(editing)

    with pytest.raises(PatchedModelValidationError) as error:
        editing.apply_patch(
            "mdl_house",
            proposal(PatchOperation("replace", "/name", "Invalid")),
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.code == "PATCHED_MODEL_INVALID"
    assert error.value.report.issues[0].code == "TEST_INVALID"
    assert editing.current("mdl_house").document["name"] == "Initial"
    assert len(editing.audit_log("mdl_house")) == 1


def test_undo_and_redo_are_exposed_as_compensating_edits() -> None:
    editing = service()
    initialize(editing)
    editing.apply_patch(
        "mdl_house",
        proposal(PatchOperation("replace", "/name", "Edited")),
        audit_identity=AUDIT_IDENTITY,
    )

    undone = editing.undo(
        "mdl_house",
        expected_revision=1,
        provenance="human:architect-7",
        rationale="Undo edit.",
        audit_identity=AUDIT_IDENTITY,
    )
    redone = editing.redo(
        "mdl_house",
        expected_revision=2,
        provenance="human:architect-7",
        rationale="Redo edit.",
        audit_identity=AUDIT_IDENTITY,
    )

    assert (undone.revision_number, undone.document["name"]) == (2, "Initial")
    assert (redone.revision_number, redone.document["name"]) == (3, "Edited")
    assert [entry.action.value for entry in editing.audit_log("mdl_house")] == [
        "initialize",
        "patch",
        "undo",
        "redo",
    ]


def test_undo_revalidates_target_with_current_policy_before_commit() -> None:
    policy = {"reject_initial": False}
    validator = StubValidator(
        lambda value: policy["reject_initial"] and value.get("name") == "Initial"
    )
    editing = service(validator=validator)
    initialize(editing)
    editing.apply_patch(
        "mdl_house",
        proposal(PatchOperation("replace", "/name", "Edited")),
        audit_identity=AUDIT_IDENTITY,
    )
    policy["reject_initial"] = True

    with pytest.raises(RestoredModelValidationError) as error:
        editing.undo(
            "mdl_house",
            expected_revision=1,
            provenance="policy-upgrade-test",
            rationale="Attempt restoration under current rules.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.code == "RESTORED_MODEL_INVALID"
    assert editing.current("mdl_house").revision_number == 1
    assert editing.current("mdl_house").document["name"] == "Edited"
    assert len(editing.audit_log("mdl_house")) == 2

    policy["reject_initial"] = False
    restored = editing.undo(
        "mdl_house",
        expected_revision=1,
        provenance="policy-upgrade-test",
        rationale="Retry after policy permits the target.",
        audit_identity=AUDIT_IDENTITY,
    )
    assert restored.revision_number == 2


@pytest.mark.parametrize("method_name", ["undo", "redo"])
def test_undo_redo_validate_history_metadata(method_name: str) -> None:
    editing = service()
    initialize(editing)
    method = getattr(editing, method_name)

    with pytest.raises(InvalidPatchError):
        method(
            "mdl_house",
            expected_revision=0,
            provenance="",
            rationale="History action.",
            audit_identity=AUDIT_IDENTITY,
        )
