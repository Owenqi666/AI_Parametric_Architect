"""Production monotonic clock for benchmark duration measurements."""

from __future__ import annotations

import time


class SystemMonotonicClock:
    """Read the system monotonic clock without exposing wall-clock timestamps."""

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()
