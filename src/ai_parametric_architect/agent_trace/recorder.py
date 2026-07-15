"""Stateless recorder for content-free observable agent traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ai_parametric_architect.agent_trace.hashing import TenantTraceHasher, TraceDigestDomain
from ai_parametric_architect.agent_trace.models import AgentTrace, ToolCallMetadata


class TraceClock(Protocol):
    """Minimal injected time source; implementations need no other authority."""

    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class AgentTraceRecorder:
    """Record correlation hashes and discard observed content immediately.

    Trace HMACs are not a privacy mechanism; access control and data
    minimization remain mandatory for the surrounding trace store.
    """

    _clock: TraceClock = field(repr=False)
    _hasher: TenantTraceHasher = field(repr=False)

    def record(
        self,
        *,
        agent_name: str,
        agent_version: str,
        trace_id: str,
        input_value: object,
        output_value: object,
        tool_calls: tuple[ToolCallMetadata, ...] = (),
    ) -> AgentTrace:
        timestamp = self._clock.now()
        input_hash = self._hasher.digest(input_value, domain=TraceDigestDomain.INPUT)
        output_hash = self._hasher.digest(output_value, domain=TraceDigestDomain.OUTPUT)
        return AgentTrace(
            agent_name=agent_name,
            agent_version=agent_version,
            trace_id=trace_id,
            tenant_id=self._hasher.tenant_id,
            key_id=self._hasher.key_id,
            input_hash=input_hash,
            output_hash=output_hash,
            tool_calls=tool_calls,
            timestamp=timestamp,
        )
