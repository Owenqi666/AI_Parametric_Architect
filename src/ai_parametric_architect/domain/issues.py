"""Stable validation result vocabulary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast

from ai_parametric_architect.domain.editing_errors import NonJsonValueError
from ai_parametric_architect.domain.json_values import ensure_json_value
from ai_parametric_architect.domain.model import ModelDocument


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_EMPTY_DETAILS: Mapping[str, object] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    path: str
    entity_ids: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=lambda: _EMPTY_DETAILS)

    def __post_init__(self) -> None:
        if not isinstance(self.details, Mapping):
            raise NonJsonValueError(
                "Validation issue details must be a JSON object.",
                path="/details",
                details={"reason": "NON_JSON_TYPE", "type": type(self.details).__name__},
            )
        details = dict(self.details)
        ensure_json_value(details)
        object.__setattr__(self, "details", MappingProxyType(deepcopy(details)))

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "path": self.path,
            "entity_ids": list(self.entity_ids),
            "message": self.message,
            "details": deepcopy(dict(self.details)),
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    model_id: str | None
    revision: int | None
    issues: tuple[ValidationIssue, ...]

    @classmethod
    def create(cls, model: object, issues: Iterable[ValidationIssue]) -> ValidationReport:
        document = cast(ModelDocument, model) if type(model) is dict else {}
        model_id_value = document.get("model_id")
        revision_value = document.get("revision")
        model_id = model_id_value if isinstance(model_id_value, str) else None
        revision = (
            revision_value
            if isinstance(revision_value, int) and not isinstance(revision_value, bool)
            else None
        )
        return cls(model_id=model_id, revision=revision, issues=tuple(issues))

    @property
    def valid(self) -> bool:
        return all(issue.severity is not Severity.ERROR for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(issue.severity is Severity.ERROR for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "model_id": self.model_id,
            "revision": self.revision,
            "error_count": self.error_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }
