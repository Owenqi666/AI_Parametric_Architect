from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from ai_parametric_architect.application import EditingService
from ai_parametric_architect.domain import (
    AuditActorType,
    ModelDocument,
    TrustedAuditIdentity,
    ValidationReport,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.infrastructure import SystemClock
from ai_parametric_architect.repositories import InMemoryRevisionRepository
from ai_parametric_architect.validation import ModelValidator


def _identity(trace_id: str) -> TrustedAuditIdentity:
    return TrustedAuditIdentity(
        actor_id="security-test",
        actor_type=AuditActorType.SYSTEM,
        trace_id=trace_id,
    )


class BlockingValidator:
    """Pause after EditingService has transferred ownership of its snapshot."""

    def __init__(self, delegate: ModelValidator) -> None:
        self._delegate = delegate
        self.entered = Event()
        self.release = Event()
        self.observed: ModelDocument | None = None

    def validate(self, model: ModelDocument) -> ValidationReport:
        self.observed = model
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("Test did not release the validation barrier")
        return self._delegate.validate(model)


def _editing(validator: ModelValidator | BlockingValidator) -> EditingService:
    return EditingService(
        validator=validator,
        repository=InMemoryRevisionRepository(),
        patch_engine=JsonPatchEngine(),
        clock=SystemClock(),
    )


def test_validator_accepted_model_can_initialize_revision(
    valid_simple_house: ModelDocument,
) -> None:
    validator = ModelValidator(ShapelyGeometryEngine())

    assert validator.validate(valid_simple_house).valid

    revision = _editing(validator).initialize(
        valid_simple_house,
        provenance="security:consistency-test",
        rationale="Prove validation and revision admission use one JSON boundary.",
        audit_identity=_identity("trace-json-consistency"),
    )

    assert revision.document == valid_simple_house
    assert validator.validate(revision.document).valid


def test_concurrent_caller_mutation_cannot_change_validated_initial_snapshot(
    valid_simple_house: ModelDocument,
) -> None:
    validator = ModelValidator(ShapelyGeometryEngine())
    blocking = BlockingValidator(validator)
    original_floor = valid_simple_house["entities"]["floors"]["flr_ground"]

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _editing(blocking).initialize,
            valid_simple_house,
            provenance="security:race-test",
            rationale="Exercise defensive initialization ownership.",
            audit_identity=_identity("trace-initialize-race"),
        )
        assert blocking.entered.wait(timeout=5)
        try:
            assert blocking.observed is not valid_simple_house
            del valid_simple_house["entities"]["floors"]["flr_ground"]
        finally:
            blocking.release.set()
        revision = future.result(timeout=5)

    stored = revision.document
    assert stored["entities"]["floors"]["flr_ground"] == original_floor
    assert validator.validate(stored).valid
    assert not validator.validate(valid_simple_house).valid
