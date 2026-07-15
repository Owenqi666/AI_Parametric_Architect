from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import MAX_JSON_DEPTH, NonJsonValueError, ensure_json_value


def test_standard_json_value_is_allowed() -> None:
    value: list[object] = [None, True, 3, 1.5, "text"]

    ensure_json_value({"first": value, "second": ["independent"]})


@pytest.mark.parametrize("shared", [[1], {"value": 1}])
def test_shared_container_references_are_rejected(shared: object) -> None:
    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value({"first": shared, "second": shared})

    assert error.value.path == "/second"
    assert error.value.details["reason"] == "SHARED_REFERENCE"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value({"metadata": {"number": value}})

    assert error.value.path == "/metadata/number"
    assert error.value.details["reason"] == "NON_FINITE_NUMBER"


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 7, 14, tzinfo=UTC),
        (1, 2),
        {1, 2},
    ],
)
def test_non_json_python_types_are_rejected(value: object) -> None:
    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value({"metadata": value})

    assert error.value.path == "/metadata"
    assert error.value.details["reason"] == "NON_JSON_TYPE"


def test_object_keys_must_be_plain_strings() -> None:
    value = cast(dict[str, object], cast(Any, {1: "not-json"}))

    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value(value)

    assert error.value.path == ""
    assert error.value.details == {"reason": "NON_STRING_KEY", "key_type": "int"}


@pytest.mark.parametrize("container_type", ["list", "dict"])
def test_cyclic_references_are_rejected(container_type: str) -> None:
    if container_type == "list":
        value: object = []
        cast(list[object], value).append(value)
    else:
        value = {}
        cast(dict[str, object], value)["self"] = value

    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value(value)

    assert error.value.details["reason"] == "CYCLIC_REFERENCE"


def test_error_paths_use_json_pointer_escaping() -> None:
    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value({"a/b~c": datetime(2026, 7, 14, tzinfo=UTC)})

    assert error.value.path == "/a~1b~0c"


def test_excessive_depth_is_rejected_before_recursive_consumers() -> None:
    value: object = "leaf"
    for _ in range(MAX_JSON_DEPTH + 1):
        value = [value]

    with pytest.raises(NonJsonValueError) as error:
        ensure_json_value(value)

    assert error.value.details == {
        "reason": "JSON_DEPTH_EXCEEDED",
        "max_depth": MAX_JSON_DEPTH,
    }
