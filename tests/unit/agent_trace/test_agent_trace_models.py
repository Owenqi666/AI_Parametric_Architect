from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from ai_parametric_architect.agent_trace import (
    TRACE_HASH_ALGORITHM,
    TRACE_SCHEMA_VERSION,
    AgentTrace,
    ToolCallMetadata,
    ToolCallStatus,
)

INPUT_HASH = "1" * 64
OUTPUT_HASH = "a" * 64
TIMESTAMP = datetime(2026, 7, 15, 9, 30, 1, 42, tzinfo=timezone(timedelta(hours=8)))


def tool_call(
    sequence: int = 1,
    *,
    tool_name: str = "validate_model",
    status: ToolCallStatus | str = ToolCallStatus.SUCCEEDED,
) -> ToolCallMetadata:
    return ToolCallMetadata(sequence=sequence, tool_name=tool_name, status=status)


def trace(**overrides: Any) -> AgentTrace:
    arguments: dict[str, Any] = {
        "agent_name": "architecture-planner",
        "agent_version": "1.0.0",
        "trace_id": "trace-01J2Y8F8K6W0",
        "tenant_id": "tenant-a",
        "key_id": "key-2026-07",
        "input_hash": INPUT_HASH,
        "output_hash": OUTPUT_HASH,
        "tool_calls": (
            tool_call(),
            tool_call(2, tool_name="preview_patch", status=ToolCallStatus.REJECTED),
        ),
        "timestamp": TIMESTAMP,
    }
    arguments.update(overrides)
    return AgentTrace(**arguments)


def test_safe_trace_has_exact_stable_json_shape_and_utc_timestamp() -> None:
    value = trace()

    assert value.schema_version == TRACE_SCHEMA_VERSION
    assert value.timestamp.tzinfo is UTC
    assert value.to_dict() == {
        "schema_version": "2.0.0",
        "agent_name": "architecture-planner",
        "agent_version": "1.0.0",
        "trace_id": "trace-01J2Y8F8K6W0",
        "tenant_id": "tenant-a",
        "key_id": "key-2026-07",
        "hash_algorithm": TRACE_HASH_ALGORITHM,
        "input_hash": INPUT_HASH,
        "output_hash": OUTPUT_HASH,
        "tool_calls": [
            {
                "sequence": 1,
                "tool_name": "validate_model",
                "status": "succeeded",
            },
            {
                "sequence": 2,
                "tool_name": "preview_patch",
                "status": "rejected",
            },
        ],
        "timestamp": "2026-07-15T01:30:01.000042Z",
    }


def test_trace_json_never_contains_observed_content_or_sensitive_fields() -> None:
    serialized_value = trace().to_dict()
    serialized = json.dumps(serialized_value, sort_keys=True)
    forbidden_keys = {
        "arguments",
        "chain_of_thought",
        "input",
        "output",
        "parameters",
        "prompt",
        "rationale",
        "reasoning",
        "result",
    }

    assert set(serialized_value) == {
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
    assert forbidden_keys.isdisjoint(serialized_value)
    assert set(tool_call().to_dict()) == {"sequence", "tool_name", "status"}
    assert all(f'"{key}"' not in serialized for key in forbidden_keys)


def test_trace_and_tool_metadata_are_frozen() -> None:
    value = trace()
    call = tool_call()

    with pytest.raises(FrozenInstanceError):
        value.agent_name = "different"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        call.tool_name = "different"  # type: ignore[misc]


def test_trace_from_dict_round_trip_is_exact() -> None:
    value = trace()

    assert AgentTrace.from_dict(value.to_dict()) == value
    assert ToolCallMetadata.from_dict(tool_call().to_dict()) == tool_call()


@pytest.mark.parametrize(
    ("sequence", "tool_name", "status"),
    [
        (0, "validate_model", "succeeded"),
        (-1, "validate_model", "succeeded"),
        (True, "validate_model", "succeeded"),
        (1.5, "validate_model", "succeeded"),
        (1, "", "succeeded"),
        (1, "Validate Model", "succeeded"),
        (1, "a" * 129, "succeeded"),
        (1, "validate_model", "unknown"),
        (1, "validate_model", 1),
    ],
)
def test_tool_metadata_rejects_unsafe_or_invalid_values(
    sequence: object,
    tool_name: object,
    status: object,
) -> None:
    with pytest.raises(ValueError):
        ToolCallMetadata(
            sequence=sequence,  # type: ignore[arg-type]
            tool_name=tool_name,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"sequence": 1, "tool_name": "validate_model", "status": "succeeded", "args": {}},
        {"sequence": "1", "tool_name": "validate_model", "status": "succeeded"},
        {"sequence": 1, "tool_name": 7, "status": "succeeded"},
        {"sequence": 1, "tool_name": "validate_model", "status": False},
    ],
)
def test_tool_metadata_from_dict_is_strict(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ToolCallMetadata.from_dict(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "1.0.0"},
        {"agent_name": ""},
        {"agent_name": "Architecture Planner"},
        {"agent_name": "a" * 65},
        {"agent_version": "v1"},
        {"agent_version": "01.0.0"},
        {"trace_id": ""},
        {"trace_id": "trace with spaces"},
        {"tenant_id": ""},
        {"tenant_id": "tenant a"},
        {"key_id": ""},
        {"hash_algorithm": "sha256"},
        {"input_hash": "a" * 63},
        {"input_hash": "A" * 64},
        {"output_hash": 7},
        {"tool_calls": [tool_call()]},
        {"tool_calls": (object(),)},
        {"tool_calls": (tool_call(2),)},
        {"tool_calls": (tool_call(), tool_call(3))},
        {"timestamp": datetime(2026, 7, 15)},
        {"timestamp": "2026-07-15T00:00:00Z"},
    ],
)
def test_trace_rejects_invalid_or_mutable_metadata(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        trace(**overrides)


def test_trace_accepts_canonical_prerelease_agent_version() -> None:
    assert trace(agent_version="2.1.0-rc.1").agent_version == "2.1.0-rc.1"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("agent_name"),
        lambda value: value.update({"prompt": "do not retain"}),
        lambda value: value.update({"timestamp": 123}),
        lambda value: value.update({"timestamp": "not-a-timestamp"}),
        lambda value: value.update({"timestamp": "2026-07-15T00:00:00"}),
        lambda value: value.update({"input_hash": 1}),
        lambda value: value.update({"tool_calls": "not-an-array"}),
        lambda value: value.update({"tool_calls": ["not-an-object"]}),
        lambda value: value.update(
            {"tool_calls": [{"sequence": 1, "tool_name": "validate_model", "status": "bad"}]}
        ),
    ],
)
def test_trace_from_dict_is_strict(mutate: Any) -> None:
    payload = trace().to_dict()
    mutate(payload)

    with pytest.raises(ValueError):
        AgentTrace.from_dict(payload)
