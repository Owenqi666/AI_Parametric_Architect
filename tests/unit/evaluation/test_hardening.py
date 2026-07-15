from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    InvalidPatchError,
    ModelComplexityPolicy,
    ModelDocument,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    ValidationReport,
)
from ai_parametric_architect.evaluation import DetachedPatchValidator


class AcceptingValidator:
    def validate(self, model: ModelDocument) -> ValidationReport:
        return ValidationReport.create(model, ())


class NonJsonPatchEngine:
    def apply(self, document: object, operations: object) -> object:
        return {"model_id": "mdl_eval", "revision": 0, "metadata": {"unsafe": {1}}}


class CapturingPatchEngine:
    def __init__(self) -> None:
        self.called = False

    def apply(self, document: object, operations: object) -> object:
        self.called = True
        return document


def revision() -> ModelRevision:
    return ModelRevision(
        model_id="mdl_eval",
        revision_number=0,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        parent_revision=None,
        document={"model_id": "mdl_eval", "revision": 0},
    )


def proposal(*operations: PatchOperation) -> PatchProposal:
    return PatchProposal(
        base_model_id="mdl_eval",
        base_revision=0,
        operations=operations,
        provenance="evaluation:test",
        rationale="Exercise detached hardening.",
    )


def test_detached_evaluation_rejects_non_json_adapter_output() -> None:
    validator = DetachedPatchValidator(
        cast(Any, NonJsonPatchEngine()),
        AcceptingValidator(),
    )

    with pytest.raises(InvalidPatchError) as error:
        validator.validate(proposal(PatchOperation("add", "/metadata", {})), revision())

    assert error.value.details["reason"] == "NON_JSON_TYPE"
    assert error.value.path == "/metadata/unsafe"


def test_detached_evaluation_checks_operation_budget_before_adapter_call() -> None:
    engine = CapturingPatchEngine()
    validator = DetachedPatchValidator(
        cast(Any, engine),
        AcceptingValidator(),
        complexity_policy=ModelComplexityPolicy(max_patch_operations=1),
    )
    candidate = proposal(
        PatchOperation("add", "/first", 1),
        PatchOperation("add", "/second", 2),
    )

    with pytest.raises(InvalidPatchError) as error:
        validator.validate(candidate, revision())

    assert error.value.details == {
        "actual": 2,
        "maximum": 1,
        "reason": "PATCH_OPERATION_LIMIT_EXCEEDED",
    }
    assert not engine.called
