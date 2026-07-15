"""Thread-safe in-memory revision history with compensating undo and redo."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import RLock
from typing import Never

from ai_parametric_architect.domain import (
    AuditAction,
    AuditEntry,
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelRevision,
    RedoUnavailableError,
    RestorationPreview,
    RevisionConflictError,
    RevisionNotFoundError,
    TrustedAuditIdentity,
    UndoUnavailableError,
)


@dataclass(slots=True)
class _ModelHistory:
    revisions: dict[int, ModelRevision]
    head_revision: int
    undo_targets: list[int] = field(default_factory=list)
    redo_targets: list[int] = field(default_factory=list)
    audit_entries: list[AuditEntry] = field(default_factory=list)


class InMemoryRevisionRepository:
    """Keep immutable snapshots and all history metadata under one lock."""

    def __init__(self) -> None:
        self._histories: dict[str, _ModelHistory] = {}
        self._lock = RLock()

    def initialize(
        self,
        revision: ModelRevision,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        with self._lock:
            if revision.model_id in self._histories:
                raise ModelAlreadyExistsError(
                    f"Model {revision.model_id!r} already has a revision history.",
                    details={"model_id": revision.model_id},
                )
            if revision.parent_revision is not None:
                raise ValueError("Initial revision cannot have a parent_revision")

            stored = _copy_revision(revision)
            history = _ModelHistory(
                revisions={revision.revision_number: stored},
                head_revision=revision.revision_number,
            )
            self._append_audit(
                history,
                AuditEntry(
                    sequence=None,
                    model_id=revision.model_id,
                    action=AuditAction.INITIALIZE,
                    from_revision=None,
                    to_revision=revision.revision_number,
                    created_at=revision.created_at,
                    actor_id=audit_identity.actor_id,
                    actor_type=audit_identity.actor_type,
                    agent_version=audit_identity.agent_version,
                    trace_id=audit_identity.trace_id,
                    provenance=provenance,
                    rationale=rationale,
                ),
            )
            self._histories[revision.model_id] = history
            return _copy_revision(stored)

    def head(self, model_id: str) -> ModelRevision:
        with self._lock:
            history = self._history(model_id)
            return _copy_revision(history.revisions[history.head_revision])

    def get(self, model_id: str, revision_number: int) -> ModelRevision:
        with self._lock:
            self._require_revision_number(revision_number, "revision_number")
            history = self._history(model_id)
            try:
                revision = history.revisions[revision_number]
            except KeyError as error:
                raise RevisionNotFoundError(
                    f"Revision {revision_number} does not exist for model {model_id!r}.",
                    details={"model_id": model_id, "revision_number": revision_number},
                ) from error
            return _copy_revision(revision)

    def commit_patch(
        self,
        revision: ModelRevision,
        *,
        expected_revision: int,
        provenance: str,
        rationale: str,
        details: Mapping[str, object],
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        with self._lock:
            self._require_revision_number(expected_revision, "expected_revision")
            history = self._history(revision.model_id)
            self._check_expected(revision.model_id, history, expected_revision)
            if revision.revision_number != expected_revision + 1:
                raise ValueError("Committed revision_number must increment the expected revision")
            if revision.parent_revision != expected_revision:
                raise ValueError("Committed parent_revision must equal the expected revision")

            stored = _copy_revision(revision)
            audit_entry = self._sequenced_audit(
                history,
                AuditEntry(
                    sequence=None,
                    model_id=stored.model_id,
                    action=AuditAction.PATCH,
                    from_revision=expected_revision,
                    to_revision=stored.revision_number,
                    created_at=stored.created_at,
                    actor_id=audit_identity.actor_id,
                    actor_type=audit_identity.actor_type,
                    agent_version=audit_identity.agent_version,
                    trace_id=audit_identity.trace_id,
                    provenance=provenance,
                    rationale=rationale,
                    _details=details,
                ),
            )
            history.revisions[stored.revision_number] = stored
            history.undo_targets.append(expected_revision)
            history.redo_targets.clear()
            history.head_revision = stored.revision_number
            history.audit_entries.append(audit_entry)
            return _copy_revision(stored)

    def preview_undo(self, model_id: str, expected_revision: int) -> RestorationPreview:
        return self._preview_restoration(model_id, expected_revision, AuditAction.UNDO)

    def preview_redo(self, model_id: str, expected_revision: int) -> RestorationPreview:
        return self._preview_restoration(model_id, expected_revision, AuditAction.REDO)

    def commit_restoration(
        self,
        preview: RestorationPreview,
        revision: ModelRevision,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        _require_trusted_identity(audit_identity)
        with self._lock:
            self._require_revision_number(preview.head_revision, "head_revision")
            self._require_revision_number(preview.target_revision, "target_revision")
            history = self._history(preview.model_id)
            self._check_expected(preview.model_id, history, preview.head_revision)
            stack = self._restoration_stack(history, preview.action)
            if not stack:
                self._raise_unavailable(preview.model_id, preview.head_revision, preview.action)
            if stack[-1] != preview.target_revision:
                raise ValueError("Restoration preview no longer matches the history stack")

            canonical_target = history.revisions[preview.target_revision]
            if preview.document != canonical_target.document:
                raise ValueError("Restoration preview document does not match stored history")
            self._validate_restoration_candidate(preview, revision, canonical_target)

            stored = _copy_revision(revision)
            audit_entry = self._restoration_audit(
                history,
                stored,
                action=preview.action,
                expected_revision=preview.head_revision,
                restored_from=preview.target_revision,
                provenance=provenance,
                rationale=rationale,
                audit_identity=audit_identity,
            )
            stack.pop()
            if preview.action is AuditAction.UNDO:
                history.redo_targets.append(preview.head_revision)
            else:
                history.undo_targets.append(preview.head_revision)
            self._store_restoration(history, stored)
            history.audit_entries.append(audit_entry)
            return _copy_revision(stored)

    def audit_log(self, model_id: str) -> tuple[AuditEntry, ...]:
        with self._lock:
            history = self._history(model_id)
            return tuple(_copy_audit(entry) for entry in history.audit_entries)

    def _history(self, model_id: str) -> _ModelHistory:
        try:
            return self._histories[model_id]
        except KeyError as error:
            raise ModelNotFoundError(
                f"Model {model_id!r} does not have a revision history.",
                details={"model_id": model_id},
            ) from error

    @staticmethod
    def _check_expected(
        model_id: str,
        history: _ModelHistory,
        expected_revision: int,
    ) -> None:
        if history.head_revision != expected_revision:
            raise RevisionConflictError(model_id, expected_revision, history.head_revision)

    @staticmethod
    def _require_revision_number(value: int, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")

    def _preview_restoration(
        self,
        model_id: str,
        expected_revision: int,
        action: AuditAction,
    ) -> RestorationPreview:
        with self._lock:
            self._require_revision_number(expected_revision, "expected_revision")
            history = self._history(model_id)
            self._check_expected(model_id, history, expected_revision)
            stack = self._restoration_stack(history, action)
            if not stack:
                self._raise_unavailable(model_id, expected_revision, action)
            target_revision = stack[-1]
            return RestorationPreview(
                model_id=model_id,
                action=action,
                head_revision=expected_revision,
                target_revision=target_revision,
                document=history.revisions[target_revision].document,
            )

    @staticmethod
    def _restoration_stack(history: _ModelHistory, action: AuditAction) -> list[int]:
        if action is AuditAction.UNDO:
            return history.undo_targets
        if action is AuditAction.REDO:
            return history.redo_targets
        raise ValueError("Restoration action must be undo or redo")

    @staticmethod
    def _raise_unavailable(model_id: str, revision: int, action: AuditAction) -> Never:
        details = {"model_id": model_id, "revision": revision}
        if action is AuditAction.UNDO:
            raise UndoUnavailableError(
                f"Model {model_id!r} has no revision to undo.",
                details=details,
            )
        raise RedoUnavailableError(
            f"Model {model_id!r} has no revision to redo.",
            details=details,
        )

    @staticmethod
    def _validate_restoration_candidate(
        preview: RestorationPreview,
        revision: ModelRevision,
        canonical_target: ModelRevision,
    ) -> None:
        if revision.model_id != preview.model_id:
            raise ValueError("Restoration revision has the wrong model_id")
        if revision.revision_number != preview.head_revision + 1:
            raise ValueError("Restoration revision_number must increment the preview head")
        if revision.parent_revision != preview.head_revision:
            raise ValueError("Restoration parent_revision must equal the preview head")
        expected_document = canonical_target.document
        expected_document["revision"] = preview.head_revision + 1
        if revision.document != expected_document:
            raise ValueError("Restoration candidate must match the target snapshot")

    @staticmethod
    def _store_restoration(history: _ModelHistory, revision: ModelRevision) -> None:
        history.revisions[revision.revision_number] = revision
        history.head_revision = revision.revision_number

    def _restoration_audit(
        self,
        history: _ModelHistory,
        revision: ModelRevision,
        *,
        action: AuditAction,
        expected_revision: int,
        restored_from: int,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> AuditEntry:
        return self._sequenced_audit(
            history,
            AuditEntry(
                sequence=None,
                model_id=revision.model_id,
                action=action,
                from_revision=expected_revision,
                to_revision=revision.revision_number,
                restored_from_revision=restored_from,
                created_at=revision.created_at,
                actor_id=audit_identity.actor_id,
                actor_type=audit_identity.actor_type,
                agent_version=audit_identity.agent_version,
                trace_id=audit_identity.trace_id,
                provenance=provenance,
                rationale=rationale,
            ),
        )

    @staticmethod
    def _append_audit(history: _ModelHistory, entry: AuditEntry) -> None:
        history.audit_entries.append(InMemoryRevisionRepository._sequenced_audit(history, entry))

    @staticmethod
    def _sequenced_audit(history: _ModelHistory, entry: AuditEntry) -> AuditEntry:
        return entry.with_sequence(len(history.audit_entries) + 1)


def _copy_revision(revision: ModelRevision) -> ModelRevision:
    return ModelRevision(
        model_id=revision.model_id,
        revision_number=revision.revision_number,
        created_at=revision.created_at,
        parent_revision=revision.parent_revision,
        document=revision.document,
    )


def _copy_audit(entry: AuditEntry) -> AuditEntry:
    return AuditEntry(
        sequence=entry.sequence,
        model_id=entry.model_id,
        action=entry.action,
        from_revision=entry.from_revision,
        to_revision=entry.to_revision,
        restored_from_revision=entry.restored_from_revision,
        created_at=entry.created_at,
        actor_id=entry.actor_id,
        actor_type=entry.actor_type,
        agent_version=entry.agent_version,
        trace_id=entry.trace_id,
        provenance=entry.provenance,
        rationale=entry.rationale,
        _details=entry.details,
    )


def _require_trusted_identity(value: object) -> None:
    if type(value) is not TrustedAuditIdentity:
        raise TypeError("A trusted audit identity is required for every repository write")
