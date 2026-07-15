"""Immutable symbolic plans for validation-constraint resolution."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from ai_parametric_architect.domain.issues import Severity, ValidationIssue
from ai_parametric_architect.domain.json_pointers import (
    JsonPointerSyntaxError,
    decode_json_pointer,
)
from ai_parametric_architect.domain.planning_errors import PlanningContextError

CONSTRAINT_RESOLUTION_SCHEMA_VERSION: Final = "1.0.0"
RULE_BASED_CONSTRAINT_STRATEGY: Final = "rule-based-symbolic-candidates-v1"

_CANDIDATE_ID_PATTERN = re.compile(r"^candidate_[0-9]{3}$")
_ISSUE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_.]{0,127}$")
_MAX_TEXT_LENGTH = 1_000
_MAX_ENTITY_ID_LENGTH = 128


class ResolutionAction(StrEnum):
    """Symbolic actions that a later planning stage may choose to elaborate."""

    MOVE_WALL = "move_wall"
    RESIZE_ROOM = "resize_room"
    CHANGE_LAYOUT = "change_layout"


class ReasoningStatus(StrEnum):
    CANDIDATES_AVAILABLE = "candidates_available"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass(frozen=True, slots=True, init=False)
class CandidateSolution:
    """One non-geometric alternative; this is not an executable edit."""

    candidate_id: str
    action: ResolutionAction
    entity_ids: tuple[str, ...]
    rationale: str

    def __init__(
        self,
        *,
        candidate_id: str,
        action: ResolutionAction | str,
        entity_ids: tuple[str, ...],
        rationale: str,
    ) -> None:
        if (
            not isinstance(candidate_id, str)
            or _CANDIDATE_ID_PATTERN.fullmatch(candidate_id) is None
        ):
            raise PlanningContextError(
                "Candidate IDs must use the canonical candidate_NNN format.",
                path="/candidate_id",
            )
        try:
            action_value = ResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise PlanningContextError(
                "Resolution action is unsupported.", path="/action"
            ) from error
        entities = _entity_ids(entity_ids, path="/entity_ids", allow_empty=False)
        rationale_value = _non_empty_text(rationale, path="/rationale")

        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "action", action_value)
        object.__setattr__(self, "entity_ids", entities)
        object.__setattr__(self, "rationale", rationale_value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CandidateSolution:
        expected = {"candidate_id", "action", "entity_ids", "rationale"}
        if set(value) != expected:
            raise PlanningContextError("Candidate solution has missing or unexpected fields.")
        candidate_id = value.get("candidate_id")
        action = value.get("action")
        entity_ids = value.get("entity_ids")
        rationale = value.get("rationale")
        if not isinstance(candidate_id, str):
            raise PlanningContextError("candidate_id must be a string.", path="/candidate_id")
        if not isinstance(action, str):
            raise PlanningContextError("action must be a string.", path="/action")
        if not isinstance(entity_ids, Sequence) or isinstance(entity_ids, (str, bytes)):
            raise PlanningContextError("entity_ids must be an array.", path="/entity_ids")
        if not isinstance(rationale, str):
            raise PlanningContextError("rationale must be a string.", path="/rationale")
        return cls(
            candidate_id=candidate_id,
            action=action,
            entity_ids=tuple(entity_ids),
            rationale=rationale,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "action": self.action.value,
            "entity_ids": list(self.entity_ids),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True, init=False)
class ConstraintResolutionPlan:
    """A detached Plan IR that records alternatives for one validation error."""

    issue_code: str
    issue_path: str
    entity_ids: tuple[str, ...]
    status: ReasoningStatus
    candidates: tuple[CandidateSolution, ...]
    strategy: str
    schema_version: str

    def __init__(
        self,
        *,
        issue_code: str,
        issue_path: str,
        entity_ids: tuple[str, ...],
        status: ReasoningStatus | str,
        candidates: tuple[CandidateSolution, ...],
        strategy: str = RULE_BASED_CONSTRAINT_STRATEGY,
        schema_version: str = CONSTRAINT_RESOLUTION_SCHEMA_VERSION,
    ) -> None:
        if schema_version != CONSTRAINT_RESOLUTION_SCHEMA_VERSION:
            raise PlanningContextError(
                "Unsupported constraint-resolution schema version.",
                path="/schema_version",
            )
        if not isinstance(issue_code, str) or _ISSUE_CODE_PATTERN.fullmatch(issue_code) is None:
            raise PlanningContextError(
                "issue_code must be a canonical validation code.", path="/issue_code"
            )
        _json_pointer(issue_path, path="/issue_path")
        entities = _entity_ids(entity_ids, path="/entity_ids", allow_empty=True)
        try:
            status_value = ReasoningStatus(status)
        except (TypeError, ValueError) as error:
            raise PlanningContextError(
                "Reasoning status is unsupported.", path="/status"
            ) from error
        if not isinstance(candidates, tuple) or not all(
            isinstance(candidate, CandidateSolution) for candidate in candidates
        ):
            raise PlanningContextError(
                "candidates must be an immutable tuple of CandidateSolution values.",
                path="/candidates",
            )
        if status_value is ReasoningStatus.CANDIDATES_AVAILABLE and not candidates:
            raise PlanningContextError(
                "Candidate availability requires at least one solution.", path="/candidates"
            )
        if status_value is ReasoningStatus.MANUAL_REVIEW_REQUIRED and candidates:
            raise PlanningContextError(
                "Manual review plans cannot include guessed candidates.", path="/candidates"
            )
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise PlanningContextError(
                "Candidate IDs must be unique within a resolution plan.", path="/candidates"
            )
        entity_id_set = set(entities)
        if any(not set(candidate.entity_ids).issubset(entity_id_set) for candidate in candidates):
            raise PlanningContextError(
                "Candidates may only reference entities identified by the source issue.",
                path="/candidates",
            )
        strategy_value = _strategy(strategy)

        object.__setattr__(self, "issue_code", issue_code)
        object.__setattr__(self, "issue_path", issue_path)
        object.__setattr__(self, "entity_ids", entities)
        object.__setattr__(self, "status", status_value)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "strategy", strategy_value)
        object.__setattr__(self, "schema_version", schema_version)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ConstraintResolutionPlan:
        expected = {
            "schema_version",
            "strategy",
            "issue_code",
            "issue_path",
            "entity_ids",
            "status",
            "candidates",
        }
        if set(value) != expected:
            raise PlanningContextError(
                "Constraint-resolution plan has missing or unexpected fields."
            )
        issue_code = value.get("issue_code")
        issue_path = value.get("issue_path")
        entity_ids = value.get("entity_ids")
        status = value.get("status")
        candidates_value = value.get("candidates")
        strategy = value.get("strategy")
        schema_version = value.get("schema_version")
        if not isinstance(issue_code, str):
            raise PlanningContextError("issue_code must be a string.", path="/issue_code")
        if not isinstance(issue_path, str):
            raise PlanningContextError("issue_path must be a string.", path="/issue_path")
        if not isinstance(entity_ids, Sequence) or isinstance(entity_ids, (str, bytes)):
            raise PlanningContextError("entity_ids must be an array.", path="/entity_ids")
        if not isinstance(status, str):
            raise PlanningContextError("status must be a string.", path="/status")
        if not isinstance(candidates_value, Sequence) or isinstance(candidates_value, (str, bytes)):
            raise PlanningContextError("candidates must be an array.", path="/candidates")
        if not isinstance(strategy, str):
            raise PlanningContextError("strategy must be a string.", path="/strategy")
        if not isinstance(schema_version, str):
            raise PlanningContextError("schema_version must be a string.", path="/schema_version")

        candidates: list[CandidateSolution] = []
        for index, candidate in enumerate(candidates_value):
            if not isinstance(candidate, Mapping):
                raise PlanningContextError(
                    "Each candidate must be an object.", path=f"/candidates/{index}"
                )
            try:
                candidates.append(CandidateSolution.from_dict(candidate))
            except PlanningContextError as error:
                raise PlanningContextError(
                    str(error),
                    path=f"/candidates/{index}{error.path}",
                    details=error.details,
                ) from error

        return cls(
            schema_version=schema_version,
            strategy=strategy,
            issue_code=issue_code,
            issue_path=issue_path,
            entity_ids=tuple(entity_ids),
            status=status,
            candidates=tuple(candidates),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "strategy": self.strategy,
            "issue_code": self.issue_code,
            "issue_path": self.issue_path,
            "entity_ids": list(self.entity_ids),
            "status": self.status.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def _entity_ids(
    value: object,
    *,
    path: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not all(
        isinstance(entity_id, str) and entity_id and len(entity_id) <= _MAX_ENTITY_ID_LENGTH
        for entity_id in value
    ):
        raise PlanningContextError(
            "entity_ids must be an immutable tuple of non-empty strings.", path=path
        )
    if not allow_empty and not value:
        raise PlanningContextError("entity_ids cannot be empty.", path=path)
    if len(value) != len(set(value)):
        raise PlanningContextError("entity_ids must be unique.", path=path)
    return value


def _non_empty_text(value: object, *, path: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > _MAX_TEXT_LENGTH
    ):
        raise PlanningContextError(
            "Text must be non-empty, trimmed, and within the supported length.", path=path
        )
    return value


def _strategy(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip().lower()
        or re.fullmatch(r"^[a-z][a-z0-9-]*$", value) is None
    ):
        raise PlanningContextError(
            "strategy must be a canonical lowercase token.", path="/strategy"
        )
    return value


def validate_error_issue(issue: ValidationIssue, *, path: str = "/issue") -> None:
    """Validate a detached issue snapshot before any rule or provider sees it."""

    if not isinstance(issue, ValidationIssue):
        raise PlanningContextError(
            "Constraint reasoning requires a ValidationIssue.",
            path=path,
            details={"reason": "INVALID_ISSUE_TYPE"},
        )
    if not isinstance(issue.severity, Severity):
        raise PlanningContextError(
            "Validation issue severity is invalid.",
            path=f"{path}/severity",
            details={
                "reason": "INVALID_SEVERITY_TYPE",
                "actual_type": type(issue.severity).__name__,
            },
        )
    if issue.severity is not Severity.ERROR:
        raise PlanningContextError(
            "Constraint rules only accept error-severity issues.",
            path=f"{path}/severity",
            details={"reason": "NON_ERROR_ISSUE", "severity": issue.severity.value},
        )
    if not isinstance(issue.code, str) or _ISSUE_CODE_PATTERN.fullmatch(issue.code) is None:
        raise PlanningContextError("Validation issue code must be canonical.", path=f"{path}/code")
    _json_pointer(issue.path, path=f"{path}/path")
    _entity_ids(issue.entity_ids, path=f"{path}/entity_ids", allow_empty=True)
    if (
        not isinstance(issue.message, str)
        or not issue.message
        or issue.message != issue.message.strip()
    ):
        raise PlanningContextError(
            "Validation issue message must be a non-empty trimmed string.",
            path=f"{path}/message",
        )
    if not isinstance(issue.details, Mapping) or not all(
        isinstance(key, str) for key in issue.details
    ):
        raise PlanningContextError(
            "Validation issue details must be an object with string keys.",
            path=f"{path}/details",
        )


def _json_pointer(value: object, *, path: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise PlanningContextError("Value must be a JSON Pointer string.", path=path)
    try:
        return decode_json_pointer(value)
    except JsonPointerSyntaxError as error:
        raise PlanningContextError(
            "Value must be a valid RFC 6901 JSON Pointer.",
            path=path,
            details={"reason": error.reason},
        ) from error
