from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_parametric_architect.agent_trace import (
    AgentTraceRecorder,
    TenantTraceHasher,
    ToolCallMetadata,
    TraceDigestDomain,
)

KEY = b"tenant-a-trace-key-material-0001"


@dataclass
class FixedClock:
    value: datetime
    calls: int = 0

    def now(self) -> datetime:
        self.calls += 1
        return self.value


def test_recorder_hashes_values_uses_clock_and_retains_no_content() -> None:
    clock = FixedClock(datetime(2026, 7, 15, 2, 0, tzinfo=UTC))
    hasher = TenantTraceHasher(tenant_id="tenant-a", key_id="key-1", key=KEY)
    recorder = AgentTraceRecorder(clock, hasher)
    input_value: dict[str, Any] = {
        "requirement": "PRIVATE natural-language requirement",
    }
    output_value: dict[str, Any] = {
        "proposal": {"private_geometry": [1, 2, 3]},
    }
    trace = recorder.record(
        agent_name="requirement-agent",
        agent_version="1.0.0",
        trace_id="trace-recorder-1",
        input_value=input_value,
        output_value=output_value,
        tool_calls=(
            ToolCallMetadata(
                sequence=1,
                tool_name="validate_model",
                status="succeeded",
            ),
        ),
    )

    assert trace.input_hash == hasher.digest(input_value, domain=TraceDigestDomain.INPUT)
    assert trace.output_hash == hasher.digest(output_value, domain=TraceDigestDomain.OUTPUT)
    assert (trace.tenant_id, trace.key_id) == ("tenant-a", "key-1")
    assert trace.timestamp == clock.value
    assert clock.calls == 1
    assert "PRIVATE" not in json.dumps(trace.to_dict())
    assert "private_geometry" not in json.dumps(trace.to_dict())
    assert repr(recorder) == "AgentTraceRecorder()"
    assert {name for name in dir(recorder) if not name.startswith("_")} == {"record"}


def test_mutating_observed_values_after_recording_cannot_change_trace() -> None:
    recorder = AgentTraceRecorder(
        FixedClock(datetime(2026, 7, 15, tzinfo=UTC)),
        TenantTraceHasher(tenant_id="tenant-a", key_id="key-1", key=KEY),
    )
    input_value: dict[str, Any] = {"rooms": ["bedroom"]}
    output_value: dict[str, Any] = {"operations": []}

    trace = recorder.record(
        agent_name="patch-agent",
        agent_version="1.0.0",
        trace_id="trace-recorder-2",
        input_value=input_value,
        output_value=output_value,
    )
    before = trace.to_dict()
    input_value["rooms"] = []
    output_value["operations"] = [{"op": "remove", "path": "/secret"}]

    assert trace.to_dict() == before
    assert trace.tool_calls == ()


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 7, 15), "2026-07-15T00:00:00Z"],
)
def test_recorder_rejects_invalid_clock_values(timestamp: object) -> None:
    recorder = AgentTraceRecorder(
        FixedClock(timestamp),  # type: ignore[arg-type]
        TenantTraceHasher(tenant_id="tenant-a", key_id="key-1", key=KEY),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        recorder.record(
            agent_name="requirement-agent",
            agent_version="1.0.0",
            trace_id="trace-invalid-clock",
            input_value={},
            output_value={},
        )
