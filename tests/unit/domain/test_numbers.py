from __future__ import annotations

import math

from ai_parametric_architect.domain.numbers import finite_float


def test_finite_float_accepts_representable_json_numbers() -> None:
    assert finite_float(42) == 42.0
    assert finite_float(1.25) == 1.25


def test_finite_float_rejects_non_finite_and_out_of_range_numbers() -> None:
    assert finite_float(math.inf) is None
    assert finite_float(math.nan) is None
    assert finite_float(10**400) is None
