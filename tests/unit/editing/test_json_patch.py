from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from ai_parametric_architect.domain import InvalidPatchError, PatchOperation
from ai_parametric_architect.editing import JsonPatchEngine


@pytest.fixture
def engine() -> JsonPatchEngine:
    return JsonPatchEngine()


def apply(
    engine: JsonPatchEngine,
    document: object,
    *operations: PatchOperation,
) -> object:
    return engine.apply(document, operations)


def test_object_operations_apply_sequentially(engine: JsonPatchEngine) -> None:
    source = {"name": "House", "metadata": {"obsolete": True}}

    result = apply(
        engine,
        source,
        PatchOperation("add", "/metadata/author", "architect"),
        PatchOperation("replace", "/name", "Courtyard House"),
        PatchOperation("remove", "/metadata/obsolete"),
    )

    assert result == {"name": "Courtyard House", "metadata": {"author": "architect"}}
    assert source == {"name": "House", "metadata": {"obsolete": True}}


def test_add_replaces_existing_object_member_per_rfc6902(engine: JsonPatchEngine) -> None:
    result = apply(engine, {"name": "Old"}, PatchOperation("add", "/name", "New"))

    assert result == {"name": "New"}


def test_array_add_inserts_and_dash_appends(engine: JsonPatchEngine) -> None:
    result = apply(
        engine,
        {"items": ["a", "c"]},
        PatchOperation("add", "/items/1", "b"),
        PatchOperation("add", "/items/-", "d"),
        PatchOperation("add", "/items/4", "e"),
    )

    assert result == {"items": ["a", "b", "c", "d", "e"]}


def test_array_remove_and_replace(engine: JsonPatchEngine) -> None:
    result = apply(
        engine,
        {"items": ["old", "remove", "keep"]},
        PatchOperation("replace", "/items/0", "new"),
        PatchOperation("remove", "/items/1"),
    )

    assert result == {"items": ["new", "keep"]}


def test_array_can_be_traversed_to_nested_target(engine: JsonPatchEngine) -> None:
    result = apply(
        engine,
        {"items": [{"name": "old"}]},
        PatchOperation("replace", "/items/0/name", "new"),
    )

    assert result == {"items": [{"name": "new"}]}


def test_escaped_pointer_and_empty_object_key(engine: JsonPatchEngine) -> None:
    result = apply(
        engine,
        {"a/b": {"~key": 1}, "": "old"},
        PatchOperation("replace", "/a~1b/~0key", 2),
        PatchOperation("replace", "/", "new"),
    )

    assert result == {"a/b": {"~key": 2}, "": "new"}


def test_dash_is_a_normal_object_key(engine: JsonPatchEngine) -> None:
    assert apply(engine, {}, PatchOperation("add", "/-", 1)) == {"-": 1}


@pytest.mark.parametrize("operation", ["add", "replace"])
def test_add_and_replace_can_replace_document_root(engine: JsonPatchEngine, operation: str) -> None:
    value: dict[str, object] = {"replacement": [1]}
    patch = PatchOperation(operation, "", value)

    result = apply(engine, {"old": True}, patch)
    value["replacement"] = []

    assert result == {"replacement": [1]}


def test_root_remove_is_rejected(engine: JsonPatchEngine) -> None:
    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {"value": 1}, PatchOperation("remove", ""))

    assert error.value.details == {
        "operation_index": 0,
        "reason": "ROOT_REMOVE_UNSUPPORTED",
    }


@pytest.mark.parametrize("operation", ["remove", "replace"])
def test_remove_and_replace_require_existing_object_target(
    engine: JsonPatchEngine, operation: str
) -> None:
    patch = (
        PatchOperation(operation, "/missing")
        if operation == "remove"
        else PatchOperation(operation, "/missing", 1)
    )

    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {}, patch)

    assert error.value.details["reason"] == "TARGET_NOT_FOUND"


def test_parent_must_exist(engine: JsonPatchEngine) -> None:
    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {}, PatchOperation("add", "/missing/child", 1))

    assert error.value.details["reason"] == "PARENT_NOT_FOUND"


@pytest.mark.parametrize("path", ["/scalar/child/grandchild", "/scalar/child"])
def test_path_cannot_traverse_or_target_scalar_parent(engine: JsonPatchEngine, path: str) -> None:
    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {"scalar": 1}, PatchOperation("add", path, 2))

    assert error.value.details["reason"] in {"SCALAR_TRAVERSAL", "INVALID_TARGET_PARENT"}


@pytest.mark.parametrize(
    ("operation", "token", "reason"),
    [
        ("add", "01", "INVALID_ARRAY_INDEX"),
        ("add", "", "INVALID_ARRAY_INDEX"),
        ("add", "-1", "INVALID_ARRAY_INDEX"),
        ("add", "\N{ARABIC-INDIC DIGIT ONE}", "INVALID_ARRAY_INDEX"),
        ("remove", "-", "INVALID_ARRAY_INDEX"),
        ("replace", "-", "INVALID_ARRAY_INDEX"),
        ("add", "2", "ARRAY_INDEX_OUT_OF_BOUNDS"),
        ("remove", "1", "ARRAY_INDEX_OUT_OF_BOUNDS"),
        ("replace", "1", "ARRAY_INDEX_OUT_OF_BOUNDS"),
        ("remove", "0", "ARRAY_INDEX_OUT_OF_BOUNDS"),
    ],
)
def test_array_index_validation(
    engine: JsonPatchEngine, operation: str, token: str, reason: str
) -> None:
    items: list[object] = [] if operation == "remove" and token == "0" else ["a"]
    patch = (
        PatchOperation(operation, f"/items/{token}")
        if operation == "remove"
        else PatchOperation(operation, f"/items/{token}", "value")
    )

    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {"items": items}, patch)

    assert error.value.details["reason"] == reason


def test_huge_array_index_is_reported_without_integer_conversion_failure(
    engine: JsonPatchEngine,
) -> None:
    token = "9" * 10_000

    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {"items": []}, PatchOperation("add", f"/items/{token}", 1))

    assert error.value.details["reason"] == "ARRAY_INDEX_OUT_OF_BOUNDS"


def test_intermediate_array_index_is_validated(engine: JsonPatchEngine) -> None:
    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {"items": []}, PatchOperation("add", "/items/0/name", "new"))

    assert error.value.details["reason"] == "ARRAY_INDEX_OUT_OF_BOUNDS"


def test_malformed_pointer_reports_operation_index(engine: JsonPatchEngine) -> None:
    operation = PatchOperation("add", "/bad~2key", 1)

    with pytest.raises(InvalidPatchError) as error:
        apply(engine, {}, PatchOperation("add", "/ok", 1), operation)

    assert error.value.path == "/bad~2key"
    assert error.value.details["operation_index"] == 1
    assert error.value.details["reason"] == "INVALID_POINTER_ESCAPE"


def test_failed_patch_is_atomic_and_does_not_mutate_patch_value(engine: JsonPatchEngine) -> None:
    source: dict[str, Any] = {"items": []}
    value: dict[str, object] = {"nested": [1]}
    operation = PatchOperation("add", "/items/-", value)

    with pytest.raises(InvalidPatchError):
        apply(
            engine,
            source,
            operation,
            PatchOperation("remove", "/missing"),
        )

    returned_value = operation.value
    assert source == {"items": []}
    assert returned_value == {"nested": [1]}


def test_empty_patch_returns_an_independent_copy(engine: JsonPatchEngine) -> None:
    source = {"items": [1]}

    result = engine.apply(source, ())
    assert result == source
    assert result is not source


def test_patch_source_must_be_json_compatible(engine: JsonPatchEngine) -> None:
    with pytest.raises(InvalidPatchError) as error:
        engine.apply({"created_at": datetime(2026, 7, 14, tzinfo=UTC)}, ())

    assert error.value.path == "/created_at"
    assert error.value.details["reason"] == "NON_JSON_TYPE"
