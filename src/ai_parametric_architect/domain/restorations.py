"""Immutable tokens for validated undo and redo transactions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ai_parametric_architect.domain.audit import AuditAction
from ai_parametric_architect.domain.json_values import ensure_json_value
from ai_parametric_architect.domain.model import ModelDocument


@dataclass(frozen=True, slots=True, init=False)
class RestorationPreview:
    model_id: str
    action: AuditAction
    head_revision: int
    target_revision: int
    _document: dict[str, Any] = field(repr=False)

    def __init__(
        self,
        *,
        model_id: str,
        action: AuditAction,
        head_revision: int,
        target_revision: int,
        document: ModelDocument,
    ) -> None:
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("Restoration model_id cannot be empty")
        if not isinstance(action, AuditAction) or action not in {
            AuditAction.UNDO,
            AuditAction.REDO,
        }:
            raise ValueError("Restoration action must be undo or redo")
        _require_revision(head_revision, "head_revision")
        _require_revision(target_revision, "target_revision")
        if target_revision >= head_revision:
            raise ValueError("Restoration target must precede the current head")

        snapshot = dict(document)
        ensure_json_value(snapshot)
        if snapshot.get("model_id") != model_id:
            raise ValueError("Restoration model_id must equal document model_id")
        document_revision = snapshot.get("revision")
        if (
            not isinstance(document_revision, int)
            or isinstance(document_revision, bool)
            or document_revision != target_revision
        ):
            raise ValueError("Restoration target_revision must equal document revision")

        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "head_revision", head_revision)
        object.__setattr__(self, "target_revision", target_revision)
        object.__setattr__(self, "_document", deepcopy(snapshot))

    @property
    def document(self) -> dict[str, Any]:
        return deepcopy(self._document)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "action": self.action.value,
            "head_revision": self.head_revision,
            "target_revision": self.target_revision,
            "document": self.document,
        }


def _require_revision(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Restoration {field_name} must be a non-negative integer")
