"""Revision history persistence port."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ai_parametric_architect.domain import (
    AuditEntry,
    ModelRevision,
    RestorationPreview,
    TrustedAuditIdentity,
)


class RevisionRepository(Protocol):
    """Atomic persistence contract for immutable revision histories.

    Implementations must return restoration previews without mutation, then use
    compare-and-swap semantics for patch and restoration commits.
    A successful transition stores the snapshot, head, history stacks, and audit
    entry atomically; a failed transition must leave all four unchanged.
    Returned revisions and audit values must not expose mutable stored state.
    """

    def initialize(
        self,
        revision: ModelRevision,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision: ...

    def head(self, model_id: str) -> ModelRevision: ...

    def get(self, model_id: str, revision_number: int) -> ModelRevision: ...

    def commit_patch(
        self,
        revision: ModelRevision,
        *,
        expected_revision: int,
        provenance: str,
        rationale: str,
        details: Mapping[str, object],
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision: ...

    def preview_undo(self, model_id: str, expected_revision: int) -> RestorationPreview: ...

    def preview_redo(self, model_id: str, expected_revision: int) -> RestorationPreview: ...

    def commit_restoration(
        self,
        preview: RestorationPreview,
        revision: ModelRevision,
        *,
        provenance: str,
        rationale: str,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision: ...

    def audit_log(self, model_id: str) -> tuple[AuditEntry, ...]: ...
