"""Atomic validated editing use cases."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ai_parametric_architect.application.errors import (
    ModelValidationError,
    PatchedModelValidationError,
    RestoredModelValidationError,
)
from ai_parametric_architect.domain import (
    AffectedEntitiesMismatchError,
    AuditEntry,
    InvalidPatchError,
    ModelComplexityError,
    ModelComplexityPolicy,
    ModelDocument,
    ModelRevision,
    PatchModelMismatchError,
    PatchProposal,
    ProtectedPathError,
    RestorationPreview,
    RevisionConflictError,
    StrictJsonTreeGuard,
    TrustedAuditIdentity,
    ValidationReport,
    derive_affected_entity_ids,
)
from ai_parametric_architect.editing import decode_pointer
from ai_parametric_architect.ports import Clock, PatchEngine, RevisionRepository, Validator

_PROTECTED_ROOT_MEMBERS = frozenset({"geometry_settings", "model_id", "revision", "schema_version"})


class EditingService:
    """Coordinate immutable patching, validation, and revision commits."""

    def __init__(
        self,
        validator: Validator,
        repository: RevisionRepository,
        patch_engine: PatchEngine,
        clock: Clock,
        json_guard: StrictJsonTreeGuard | None = None,
        complexity_policy: ModelComplexityPolicy | None = None,
    ) -> None:
        self._validator = validator
        self._repository = repository
        self._patch_engine = patch_engine
        self._clock = clock
        self._json_guard = StrictJsonTreeGuard() if json_guard is None else json_guard
        self._complexity_policy = (
            ModelComplexityPolicy() if complexity_policy is None else complexity_policy
        )

    def initialize(
        self,
        model: ModelDocument,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        _require_history_metadata(provenance, rationale)
        snapshot = self._defensive_snapshot(model)
        report = self._validator.validate(snapshot)
        if not report.valid:
            raise ModelValidationError(report)
        try:
            self._complexity_policy.require_model(snapshot)
        except ModelComplexityError as error:
            raise ModelValidationError(
                ValidationReport.create(snapshot, (error.to_issue(),))
            ) from error
        model_id, revision_number = _validated_identity(snapshot)
        revision = ModelRevision(
            model_id=model_id,
            revision_number=revision_number,
            created_at=self._clock.now(),
            parent_revision=None,
            document=snapshot,
        )
        return self._repository.initialize(
            revision,
            provenance=provenance,
            rationale=rationale,
            audit_identity=audit_identity,
        )

    def apply_patch(
        self,
        model_id: str,
        proposal: PatchProposal,
        *,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        if proposal.base_model_id != model_id:
            raise PatchModelMismatchError(
                "Patch proposal is bound to a different model.",
                path="/base_model_id",
                details={
                    "base_model_id": proposal.base_model_id,
                    "target_model_id": model_id,
                },
            )
        current = self._repository.head(model_id)
        if current.revision_number != proposal.base_revision:
            raise RevisionConflictError(
                model_id,
                proposal.base_revision,
                current.revision_number,
            )
        try:
            self._complexity_policy.require_patch_operations(len(proposal.operations))
        except ModelComplexityError as error:
            raise InvalidPatchError(
                str(error),
                path=error.path,
                details={**error.details, "reason": error.code},
            ) from error
        self._ensure_mutable_paths(proposal)

        patched_value = self._patch_engine.apply(current.document, proposal.operations)
        if not isinstance(patched_value, dict):
            raise InvalidPatchError("A model patch must produce a JSON object document.")
        patched: dict[str, Any] = patched_value
        next_revision = current.revision_number + 1
        patched["revision"] = next_revision

        self._json_guard.require(patched)
        report = self._validator.validate(patched)
        if not report.valid:
            raise PatchedModelValidationError(report)
        try:
            self._complexity_policy.require_model(patched)
        except ModelComplexityError as error:
            raise PatchedModelValidationError(
                ValidationReport.create(patched, (error.to_issue(),))
            ) from error

        affected_entity_ids = derive_affected_entity_ids(current.document, patched)
        if frozenset(proposal.affected_entity_ids) != frozenset(affected_entity_ids):
            raise AffectedEntitiesMismatchError(
                "Patch affected entities do not match the validated document delta.",
                path="/affected_entity_ids",
                details={
                    "actual": list(proposal.affected_entity_ids),
                    "expected": list(affected_entity_ids),
                },
            )

        revision = ModelRevision(
            model_id=model_id,
            revision_number=next_revision,
            created_at=self._clock.now(),
            parent_revision=current.revision_number,
            document=patched,
        )
        detail_values: dict[str, object] = {
            "operations": [
                {"op": operation.op.value, "path": operation.path}
                for operation in proposal.operations
            ]
        }
        if affected_entity_ids:
            detail_values["affected_entity_ids"] = list(affected_entity_ids)
        details: Mapping[str, object] = detail_values
        return self._repository.commit_patch(
            revision,
            expected_revision=current.revision_number,
            provenance=proposal.provenance,
            rationale=proposal.rationale,
            details=details,
            audit_identity=audit_identity,
        )

    def undo(
        self,
        model_id: str,
        *,
        expected_revision: int,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        _require_history_metadata(provenance, rationale)
        return self._restore(
            self._repository.preview_undo(model_id, expected_revision),
            provenance=provenance,
            rationale=rationale,
            audit_identity=audit_identity,
        )

    def redo(
        self,
        model_id: str,
        *,
        expected_revision: int,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        _require_history_metadata(provenance, rationale)
        return self._restore(
            self._repository.preview_redo(model_id, expected_revision),
            provenance=provenance,
            rationale=rationale,
            audit_identity=audit_identity,
        )

    def current(self, model_id: str) -> ModelRevision:
        return self._repository.head(model_id)

    def revision(self, model_id: str, revision_number: int) -> ModelRevision:
        return self._repository.get(model_id, revision_number)

    def audit_log(self, model_id: str) -> tuple[AuditEntry, ...]:
        return self._repository.audit_log(model_id)

    def _restore(
        self,
        preview: RestorationPreview,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        next_revision = preview.head_revision + 1
        document = preview.document
        document["revision"] = next_revision
        self._json_guard.require(document)
        report = self._validator.validate(document)
        if not report.valid:
            raise RestoredModelValidationError(report)
        try:
            self._complexity_policy.require_model(document)
        except ModelComplexityError as error:
            raise RestoredModelValidationError(
                ValidationReport.create(document, (error.to_issue(),))
            ) from error
        revision = ModelRevision(
            model_id=preview.model_id,
            revision_number=next_revision,
            created_at=self._clock.now(),
            parent_revision=preview.head_revision,
            document=document,
        )
        return self._repository.commit_restoration(
            preview,
            revision,
            provenance=provenance,
            rationale=rationale,
            audit_identity=audit_identity,
        )

    def _defensive_snapshot(self, model: ModelDocument) -> ModelDocument:
        """Own and re-check the exact JSON value used by initialization."""

        self._json_guard.require(model)
        snapshot = deepcopy(model)
        self._json_guard.require(snapshot)
        return snapshot

    @staticmethod
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


def _validated_identity(model: ModelDocument) -> tuple[str, int]:
    model_id = model.get("model_id")
    revision = model.get("revision")
    if not isinstance(model_id, str) or not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("Validator accepted a model without a typed model_id and revision")
    return model_id, revision


def _require_history_metadata(provenance: str, rationale: str) -> None:
    if not isinstance(provenance, str) or not provenance.strip():
        raise InvalidPatchError("History provenance cannot be empty.")
    if not isinstance(rationale, str) or not rationale.strip():
        raise InvalidPatchError("History rationale cannot be empty.")


def _require_trusted_identity(value: object) -> None:
    if type(value) is not TrustedAuditIdentity:
        raise TypeError("A trusted audit identity is required for every write operation")
