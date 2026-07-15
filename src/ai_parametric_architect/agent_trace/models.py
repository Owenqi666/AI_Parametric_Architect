"""Immutable, content-free observability values for agent execution."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from ai_parametric_architect.agent_trace.hashing import TRACE_HASH_ALGORITHM

TRACE_SCHEMA_VERSION: Final = "2.0.0"

_AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_AGENT_VERSION_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?$"
)
_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ToolCallStatus(StrEnum):
    """Content-free outcome of a controlled tool invocation."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True, init=False)
class ToolCallMetadata:
    """Allowlisted tool metadata without arguments, results, or error text."""

    sequence: int
    tool_name: str
    status: ToolCallStatus

    def __init__(
        self,
        *,
        sequence: int,
        tool_name: str,
        status: ToolCallStatus | str,
    ) -> None:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError("Tool-call sequence must be a positive integer.")
        if not isinstance(tool_name, str) or _TOOL_NAME_PATTERN.fullmatch(tool_name) is None:
            raise ValueError("tool_name must be a canonical registered tool identifier.")
        try:
            status_value = ToolCallStatus(status)
        except (TypeError, ValueError) as error:
            raise ValueError("Tool-call status is not supported.") from error

        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "status", status_value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ToolCallMetadata:
        if set(value) != {"sequence", "tool_name", "status"}:
            raise ValueError("Tool-call metadata has missing or unexpected fields.")
        sequence = value.get("sequence")
        tool_name = value.get("tool_name")
        status = value.get("status")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ValueError("Tool-call sequence must be an integer.")
        if not isinstance(tool_name, str):
            raise ValueError("tool_name must be a string.")
        if not isinstance(status, str):
            raise ValueError("Tool-call status must be a string.")
        return cls(sequence=sequence, tool_name=tool_name, status=status)

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "tool_name": self.tool_name,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, init=False)
class AgentTrace:
    """One immutable, content-free observable execution trace.

    HMAC values provide scoped correlation and integrity fingerprints.  They do
    not make trace records private or anonymous.
    """

    agent_name: str
    agent_version: str
    trace_id: str
    tenant_id: str
    key_id: str
    hash_algorithm: str
    input_hash: str
    output_hash: str
    tool_calls: tuple[ToolCallMetadata, ...]
    timestamp: datetime
    schema_version: str

    def __init__(
        self,
        *,
        agent_name: str,
        agent_version: str,
        trace_id: str,
        tenant_id: str,
        key_id: str,
        input_hash: str,
        output_hash: str,
        tool_calls: tuple[ToolCallMetadata, ...],
        timestamp: datetime,
        schema_version: str = TRACE_SCHEMA_VERSION,
        hash_algorithm: str = TRACE_HASH_ALGORITHM,
    ) -> None:
        if schema_version != TRACE_SCHEMA_VERSION:
            raise ValueError("Agent trace schema_version is not supported.")
        if not isinstance(agent_name, str) or _AGENT_NAME_PATTERN.fullmatch(agent_name) is None:
            raise ValueError("agent_name must be a canonical agent identifier.")
        if (
            not isinstance(agent_version, str)
            or _AGENT_VERSION_PATTERN.fullmatch(agent_version) is None
        ):
            raise ValueError("agent_version must be a canonical semantic version.")
        _require_identifier(trace_id, "trace_id")
        _require_identifier(tenant_id, "tenant_id")
        _require_identifier(key_id, "key_id")
        if hash_algorithm != TRACE_HASH_ALGORITHM:
            raise ValueError("Agent trace hash_algorithm is not supported.")
        _require_hash(input_hash, "input_hash")
        _require_hash(output_hash, "output_hash")
        if not isinstance(tool_calls, tuple) or not all(
            isinstance(tool_call, ToolCallMetadata) for tool_call in tool_calls
        ):
            raise ValueError("tool_calls must be an immutable tuple of ToolCallMetadata values.")
        expected_sequences = tuple(range(1, len(tool_calls) + 1))
        if tuple(tool_call.sequence for tool_call in tool_calls) != expected_sequences:
            raise ValueError("Tool-call sequences must be contiguous and execution ordered.")
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise ValueError("Agent trace timestamp must be timezone-aware.")

        object.__setattr__(self, "agent_name", agent_name)
        object.__setattr__(self, "agent_version", agent_version)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "hash_algorithm", hash_algorithm)
        object.__setattr__(self, "input_hash", input_hash)
        object.__setattr__(self, "output_hash", output_hash)
        object.__setattr__(self, "tool_calls", tool_calls)
        object.__setattr__(self, "timestamp", timestamp.astimezone(UTC))
        object.__setattr__(self, "schema_version", schema_version)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AgentTrace:
        expected = {
            "schema_version",
            "agent_name",
            "agent_version",
            "trace_id",
            "tenant_id",
            "key_id",
            "hash_algorithm",
            "input_hash",
            "output_hash",
            "tool_calls",
            "timestamp",
        }
        if set(value) != expected:
            raise ValueError("Agent trace has missing or unexpected fields.")

        tool_calls_value = value.get("tool_calls")
        if not isinstance(tool_calls_value, Sequence) or isinstance(tool_calls_value, (str, bytes)):
            raise ValueError("tool_calls must be an array.")
        tool_calls: list[ToolCallMetadata] = []
        for index, tool_call in enumerate(tool_calls_value):
            if not isinstance(tool_call, Mapping):
                raise ValueError(f"tool_calls/{index} must be an object.")
            try:
                tool_calls.append(ToolCallMetadata.from_dict(tool_call))
            except ValueError as error:
                raise ValueError(f"tool_calls/{index}: {error}") from error

        timestamp_value = value.get("timestamp")
        if not isinstance(timestamp_value, str):
            raise ValueError("timestamp must be an ISO-8601 string.")
        try:
            timestamp = datetime.fromisoformat(timestamp_value)
        except ValueError as error:
            raise ValueError("timestamp must be a valid ISO-8601 string.") from error

        schema_version = _string_member(value, "schema_version")
        agent_name = _string_member(value, "agent_name")
        agent_version = _string_member(value, "agent_version")
        trace_id = _string_member(value, "trace_id")
        tenant_id = _string_member(value, "tenant_id")
        key_id = _string_member(value, "key_id")
        hash_algorithm = _string_member(value, "hash_algorithm")
        input_hash = _string_member(value, "input_hash")
        output_hash = _string_member(value, "output_hash")

        return cls(
            schema_version=schema_version,
            agent_name=agent_name,
            agent_version=agent_version,
            trace_id=trace_id,
            tenant_id=tenant_id,
            key_id=key_id,
            hash_algorithm=hash_algorithm,
            input_hash=input_hash,
            output_hash=output_hash,
            tool_calls=tuple(tool_calls),
            timestamp=timestamp,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "key_id": self.key_id,
            "hash_algorithm": self.hash_algorithm,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "tool_calls": [tool_call.to_dict() for tool_call in self.tool_calls],
            "timestamp": self.timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }


def _require_hash(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest.")


def _string_member(value: Mapping[str, Any], field_name: str) -> str:
    member = value.get(field_name)
    if not isinstance(member, str):
        raise ValueError(f"{field_name} must be a string.")
    return member


def _require_identifier(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(character.isspace() or not character.isprintable() for character in value)
    ):
        raise ValueError(f"{field_name} must be a canonical non-empty identifier.")
