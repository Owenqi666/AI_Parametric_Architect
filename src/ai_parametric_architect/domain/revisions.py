"""Immutable revision envelopes around authoritative JSON model snapshots."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ai_parametric_architect.domain.json_values import ensure_json_value
from ai_parametric_architect.domain.model import ModelDocument


@dataclass(frozen=True, slots=True, init=False)
class ModelRevision:
    model_id: str
    revision_number: int
    created_at: datetime
    parent_revision: int | None
    _document: dict[str, Any] = field(repr=False)

    def __init__(
        self,
        *,
        model_id: str,
        revision_number: int,
        created_at: datetime,
        parent_revision: int | None,
        document: ModelDocument,
    ) -> None:
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("model_id cannot be empty")
        if (
            not isinstance(revision_number, int)
            or isinstance(revision_number, bool)
            or revision_number < 0
        ):
            raise ValueError("revision_number must be a non-negative integer")
        if not isinstance(created_at, datetime) or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if parent_revision is not None and (
            not isinstance(parent_revision, int)
            or isinstance(parent_revision, bool)
            or parent_revision < 0
            or parent_revision >= revision_number
        ):
            raise ValueError("parent_revision must be lower than revision_number")

        ensure_json_value(document)
        snapshot = deepcopy(document)
        ensure_json_value(snapshot)
        if snapshot.get("model_id") != model_id:
            raise ValueError("Revision model_id must equal document model_id")
        document_revision = snapshot.get("revision")
        if (
            not isinstance(document_revision, int)
            or isinstance(document_revision, bool)
            or document_revision != revision_number
        ):
            raise ValueError("revision_number must equal document revision")

        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "parent_revision", parent_revision)
        object.__setattr__(self, "_document", snapshot)

    @property
    def document(self) -> dict[str, Any]:
        return deepcopy(self._document)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "revision_number": self.revision_number,
            "created_at": self.created_at.isoformat(),
            "parent_revision": self.parent_revision,
            "document": self.document,
        }
