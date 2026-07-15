from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_parametric_architect.domain import (
    ModelComplexityError,
    ModelComplexityPolicy,
    NonJsonValueError,
    StrictJsonTreeGuard,
)


def test_strict_json_guard_accepts_standard_tree_without_mutation() -> None:
    value: dict[str, object] = {"rooms": [{"id": "rom_a"}], "enabled": True}
    before = copy.deepcopy(value)
    guard = StrictJsonTreeGuard()

    guard.require(value)

    assert guard.issue(value) is None
    assert value == before


@pytest.mark.parametrize(
    ("value", "path", "reason"),
    [
        ({"metadata": {"value": float("nan")}}, "/metadata/value", "NON_FINITE_NUMBER"),
        ({"metadata": {"value": float("inf")}}, "/metadata/value", "NON_FINITE_NUMBER"),
        (
            {"metadata": {"value": datetime(2026, 7, 15, tzinfo=UTC)}},
            "/metadata/value",
            "NON_JSON_TYPE",
        ),
        ({"metadata": {"value": (1, 2)}}, "/metadata/value", "NON_JSON_TYPE"),
        ({"metadata": {"value": {1, 2}}}, "/metadata/value", "NON_JSON_TYPE"),
        ({"metadata": {"value": object()}}, "/metadata/value", "NON_JSON_TYPE"),
    ],
)
def test_strict_json_guard_has_one_stable_issue_contract(
    value: object,
    path: str,
    reason: str,
) -> None:
    guard = StrictJsonTreeGuard()

    with pytest.raises(NonJsonValueError):
        guard.require(value)
    issue = guard.issue(value)

    assert issue is not None
    assert issue.code == "JSON_TREE_INVALID"
    assert issue.path == path
    assert issue.details["reason"] == reason


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_total_entities": 0},
        {"max_polygon_vertices": True},
        {"max_coordinate_magnitude": float("inf")},
        {"max_coordinate_magnitude": 10**400},
        {"max_room_area": 0.0},
        {"max_wall_length": -1.0},
        {"max_patch_operations": 1.5},
    ],
)
def test_complexity_policy_rejects_invalid_configuration(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ModelComplexityPolicy(**overrides)  # type: ignore[arg-type]


def test_complexity_policy_limits_patch_operations() -> None:
    policy = ModelComplexityPolicy(max_patch_operations=2)

    policy.require_patch_operations(2)
    with pytest.raises(ModelComplexityError) as error:
        policy.require_patch_operations(3)

    assert error.value.code == "PATCH_OPERATION_LIMIT_EXCEEDED"
    assert error.value.path == "/operations"
    assert error.value.details == {"actual": 3, "maximum": 2}


@pytest.mark.parametrize(
    ("policy", "mutation", "code"),
    [
        (
            ModelComplexityPolicy(max_total_entities=1),
            lambda _model: None,
            "MODEL_ENTITY_LIMIT_EXCEEDED",
        ),
        (
            ModelComplexityPolicy(max_polygon_vertices=4),
            lambda _model: None,
            "MODEL_POLYGON_VERTEX_LIMIT_EXCEEDED",
        ),
        (
            ModelComplexityPolicy(max_coordinate_magnitude=5.0),
            lambda _model: None,
            "MODEL_COORDINATE_RANGE_EXCEEDED",
        ),
        (
            ModelComplexityPolicy(max_room_area=10.0),
            lambda _model: None,
            "MODEL_AREA_LIMIT_EXCEEDED",
        ),
        (
            ModelComplexityPolicy(max_wall_length=5.0),
            lambda _model: None,
            "MODEL_WALL_LENGTH_LIMIT_EXCEEDED",
        ),
    ],
)
def test_complexity_policy_rejects_each_bounded_resource(
    valid_simple_house: dict[str, Any],
    policy: ModelComplexityPolicy,
    mutation: object,
    code: str,
) -> None:
    del mutation
    before = copy.deepcopy(valid_simple_house)

    with pytest.raises(ModelComplexityError) as error:
        policy.require_model(valid_simple_house)

    assert error.value.code == code
    assert valid_simple_house == before


def test_complexity_policy_reports_non_finite_derived_room_area(
    valid_simple_house: dict[str, Any],
) -> None:
    valid_simple_house["entities"]["rooms"]["rom_living"]["geometry"]["exterior"] = [
        [1e308, 1e308],
        [-1e308, 1e308],
        [-1e308, -1e308],
        [1e308, -1e308],
        [1e308, 1e308],
    ]
    policy = ModelComplexityPolicy(
        max_coordinate_magnitude=1e308,
        max_room_area=1e308,
    )

    with pytest.raises(ModelComplexityError) as error:
        policy.require_model(valid_simple_house)

    assert error.value.code == "MODEL_DERIVED_GEOMETRY_NON_FINITE"
    assert error.value.details == {"quantity": "area"}
