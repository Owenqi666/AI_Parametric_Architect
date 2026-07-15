"""Safe conversion at the JSON-number to floating-geometry boundary."""

from __future__ import annotations

import math


def finite_float(value: int | float) -> float | None:
    """Return a finite float, or ``None`` when conversion exceeds float range."""

    try:
        converted = float(value)
    except OverflowError:
        return None
    return converted if math.isfinite(converted) else None
