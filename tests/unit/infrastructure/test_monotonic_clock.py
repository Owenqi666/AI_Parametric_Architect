from __future__ import annotations

from ai_parametric_architect.infrastructure import SystemMonotonicClock


def test_system_monotonic_clock_returns_non_decreasing_nanoseconds() -> None:
    clock = SystemMonotonicClock()

    first = clock.monotonic_ns()
    second = clock.monotonic_ns()

    assert first >= 0
    assert second >= first
