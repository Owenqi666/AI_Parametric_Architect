from __future__ import annotations

import pytest

from ai_parametric_architect.domain import GeometryPrecisionPolicy


def test_policy_is_derived_from_model_tolerance() -> None:
    policy = GeometryPrecisionPolicy.from_model(
        {"geometry_settings": {"linear_tolerance": 0.000001}}
    )

    assert policy.linear_tolerance == 0.000001
    assert policy.area_tolerance == pytest.approx(0.000000000001)
    assert policy.decimal_places == 6


def test_policy_centralizes_zero_and_point_comparisons() -> None:
    policy = GeometryPrecisionPolicy(linear_tolerance=0.001, decimal_places=3)

    assert policy.is_zero_length(0.001)
    assert not policy.is_zero_length(0.0011)
    assert policy.is_zero_area(0.000001)
    assert policy.points_equal((0.0, 0.0), (0.0006, 0.0006))


def test_number_formatting_is_fixed_and_normalizes_negative_zero() -> None:
    policy = GeometryPrecisionPolicy(linear_tolerance=0.000001, decimal_places=6)

    assert policy.format_number(1.25) == "1.250000"
    assert policy.format_number(-0.0000001) == "0.000000"


@pytest.mark.parametrize(
    "tolerance",
    [0.0, -1.0, 1e-13, 0.1, float("inf"), float("nan")],
)
def test_policy_rejects_invalid_tolerance(tolerance: float) -> None:
    with pytest.raises(ValueError, match="linear_tolerance"):
        GeometryPrecisionPolicy(linear_tolerance=tolerance, decimal_places=6)


@pytest.mark.parametrize("decimal_places", [-1, 13])
def test_policy_rejects_invalid_decimal_places(decimal_places: int) -> None:
    with pytest.raises(ValueError, match="decimal_places"):
        GeometryPrecisionPolicy(linear_tolerance=0.001, decimal_places=decimal_places)
