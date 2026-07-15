from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    AuditAction,
    AuditActorType,
    AuditEntry,
    NonJsonValueError,
    TrustedAuditIdentity,
)


def make_entry(**overrides: Any) -> AuditEntry:
    arguments: dict[str, Any] = {
        "sequence": None,
        "model_id": "mdl_house",
        "action": AuditAction.PATCH,
        "from_revision": 0,
        "to_revision": 1,
        "created_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        "actor_id": "patch-agent",
        "actor_type": AuditActorType.AGENT,
        "agent_version": "1.2.0",
        "trace_id": "trace:patch-42",
        "provenance": "untrusted:human-claim",
        "rationale": "Move a wall.",
        "_details": {"operation_paths": ["/entities/walls/wal_north"]},
    }
    arguments.update(overrides)
    return AuditEntry(**arguments)


def test_repository_can_sequence_and_serialize_audit_entry() -> None:
    details: dict[str, object] = {"operation_paths": ["/name"]}
    entry = make_entry(_details=details)
    details["operation_paths"] = []

    sequenced = entry.with_sequence(3)
    returned = sequenced.details
    returned["operation_paths"] = []

    assert sequenced.to_dict() == {
        "sequence": 3,
        "model_id": "mdl_house",
        "action": "patch",
        "from_revision": 0,
        "to_revision": 1,
        "restored_from_revision": None,
        "created_at": "2026-07-14T09:00:00+00:00",
        "actor_id": "patch-agent",
        "actor_type": "agent",
        "agent_version": "1.2.0",
        "trace_id": "trace:patch-42",
        "untrusted_provenance": "untrusted:human-claim",
        "untrusted_rationale": "Move a wall.",
        "details": {"operation_paths": ["/name"]},
    }


def test_unsequenced_audit_entry_cannot_be_serialized() -> None:
    with pytest.raises(ValueError, match="unsequenced"):
        make_entry().to_dict()


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_audit_sequence_must_be_positive_integer(sequence: object) -> None:
    with pytest.raises(ValueError, match="positive"):
        make_entry(sequence=sequence)


def test_audit_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_entry(created_at=datetime(2026, 7, 14))


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_id": ""},
        {"action": cast(Any, "bogus")},
        {"from_revision": False},
        {"to_revision": -1},
        {"restored_from_revision": 1.0},
        {"to_revision": 0},
        {"action": AuditAction.INITIALIZE, "from_revision": 0},
        {"action": AuditAction.PATCH, "from_revision": None},
        {"action": AuditAction.PATCH, "restored_from_revision": 0},
        {"action": AuditAction.UNDO, "restored_from_revision": None},
        {"action": AuditAction.REDO, "restored_from_revision": 3},
        {"provenance": " "},
        {"rationale": ""},
        {"actor_id": ""},
        {"actor_type": cast(Any, "unknown")},
        {"agent_version": None},
        {"trace_id": "trace with spaces"},
    ],
)
def test_audit_rejects_invalid_required_metadata(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_entry(**overrides)


def test_audit_details_must_be_json_compatible() -> None:
    with pytest.raises(NonJsonValueError):
        make_entry(_details={"timestamp": datetime(2026, 7, 14, tzinfo=UTC)})


def test_trusted_audit_identity_enforces_agent_version_semantics() -> None:
    identity = TrustedAuditIdentity(
        actor_id="planner-agent",
        actor_type="agent",
        agent_version="2.0.0",
        trace_id="trace:planner-1",
    )

    assert identity.actor_type is AuditActorType.AGENT
    with pytest.raises(ValueError, match="requires agent_version"):
        TrustedAuditIdentity(
            actor_id="planner-agent",
            actor_type="agent",
            trace_id="trace:planner-2",
        )
    with pytest.raises(ValueError, match="Only agent"):
        TrustedAuditIdentity(
            actor_id="architect-7",
            actor_type="human",
            agent_version="2.0.0",
            trace_id="trace:human-1",
        )
