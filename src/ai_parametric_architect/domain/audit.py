"""Append-only revision audit entries."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from ai_parametric_architect.domain.json_values import ensure_json_value


class AuditAction(StrEnum):
    INITIALIZE = "initialize"
    PATCH = "patch"
    UNDO = "undo"
    REDO = "redo"


class AuditActorType(StrEnum):
    """Trusted principal category supplied outside proposal-controlled data."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True, init=False)
class TrustedAuditIdentity:
    """Authenticated audit context carried on a separate trusted channel.

    Patch provenance and rationale are untrusted descriptive text.  They must
    never be parsed to construct this value or to infer a human actor.
    """

    actor_id: str
    actor_type: AuditActorType
    agent_version: str | None
    trace_id: str

    def __init__(
        self,
        *,
        actor_id: str,
        actor_type: AuditActorType | str,
        trace_id: str,
        agent_version: str | None = None,
    ) -> None:
        _require_identifier(actor_id, "actor_id", max_length=128)
        _require_identifier(trace_id, "trace_id", max_length=128)
        try:
            actor_type_value = AuditActorType(actor_type)
        except (TypeError, ValueError) as error:
            raise ValueError("Audit actor_type is not supported") from error
        if actor_type_value is AuditActorType.AGENT:
            if agent_version is None:
                raise ValueError("Agent audit identity requires agent_version")
            _require_identifier(agent_version, "agent_version", max_length=64)
        elif agent_version is not None:
            raise ValueError("Only agent audit identities may have agent_version")

        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "actor_type", actor_type_value)
        object.__setattr__(self, "agent_version", agent_version)
        object.__setattr__(self, "trace_id", trace_id)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Append-only transition metadata with trusted and untrusted fields.

    ``actor_*`` and ``trace_id`` originate from ``TrustedAuditIdentity``.
    ``provenance`` and ``rationale`` remain untrusted proposal/source labels
    retained for backwards-compatible diagnostics only.
    """

    sequence: int | None
    model_id: str
    action: AuditAction
    from_revision: int | None
    to_revision: int
    created_at: datetime
    actor_id: str
    actor_type: AuditActorType
    agent_version: str | None
    trace_id: str
    provenance: str
    rationale: str
    restored_from_revision: int | None = None
    _details: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.sequence is not None and (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("Audit sequence must be positive")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("Audit model_id cannot be empty")
        if not isinstance(self.action, AuditAction):
            raise ValueError("Audit action must be an AuditAction")
        _require_optional_revision(self.from_revision, "from_revision")
        _require_revision(self.to_revision, "to_revision")
        _require_optional_revision(self.restored_from_revision, "restored_from_revision")
        if self.from_revision is not None and self.to_revision != self.from_revision + 1:
            raise ValueError("Audit to_revision must increment from_revision")
        if self.action is AuditAction.INITIALIZE and (
            self.from_revision is not None or self.restored_from_revision is not None
        ):
            raise ValueError("Initialize audit cannot have source revisions")
        if self.action is AuditAction.PATCH and (
            self.from_revision is None or self.restored_from_revision is not None
        ):
            raise ValueError("Patch audit requires from_revision and no restored revision")
        if self.action in {AuditAction.UNDO, AuditAction.REDO} and (
            self.from_revision is None or self.restored_from_revision is None
        ):
            raise ValueError("Undo/redo audit requires source and restored revisions")
        if (
            self.restored_from_revision is not None
            and self.restored_from_revision >= self.to_revision
        ):
            raise ValueError("Audit restored_from_revision must precede to_revision")
        if not isinstance(self.created_at, datetime) or self.created_at.utcoffset() is None:
            raise ValueError("Audit created_at must be timezone-aware")
        TrustedAuditIdentity(
            actor_id=self.actor_id,
            actor_type=self.actor_type,
            agent_version=self.agent_version,
            trace_id=self.trace_id,
        )
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("Audit provenance cannot be empty")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("Audit rationale cannot be empty")
        details = dict(self._details)
        ensure_json_value(details)
        object.__setattr__(self, "_details", deepcopy(details))

    @property
    def details(self) -> dict[str, object]:
        return deepcopy(dict(self._details))

    def with_sequence(self, sequence: int) -> AuditEntry:
        return replace(self, sequence=sequence)

    def to_dict(self) -> dict[str, object]:
        if self.sequence is None:
            raise ValueError("Cannot serialize an unsequenced audit entry")
        return {
            "sequence": self.sequence,
            "model_id": self.model_id,
            "action": self.action.value,
            "from_revision": self.from_revision,
            "to_revision": self.to_revision,
            "restored_from_revision": self.restored_from_revision,
            "created_at": self.created_at.isoformat(),
            "actor_id": self.actor_id,
            "actor_type": self.actor_type.value,
            "agent_version": self.agent_version,
            "trace_id": self.trace_id,
            "untrusted_provenance": self.provenance,
            "untrusted_rationale": self.rationale,
            "details": self.details,
        }


def _require_revision(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Audit {field_name} must be a non-negative integer")


def _require_optional_revision(value: int | None, field_name: str) -> None:
    if value is not None:
        _require_revision(value, field_name)


def _require_identifier(value: object, field_name: str, *, max_length: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_length
        or any(character.isspace() or not character.isprintable() for character in value)
    ):
        raise ValueError(f"Audit {field_name} must be a canonical non-empty identifier")
