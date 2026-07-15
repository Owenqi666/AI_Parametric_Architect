from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    MAX_JSON_DEPTH,
    InvalidPatchError,
    PatchOperation,
    PatchOperationType,
    PatchProposal,
)


def test_patch_operation_preserves_explicit_null_and_copies_value() -> None:
    source: dict[str, object] = {"nested": [1]}
    operation = PatchOperation("add", "/metadata", source)
    null_operation = PatchOperation.from_dict({"op": "replace", "path": "/name", "value": None})

    source["nested"] = []
    returned = cast(dict[str, object], operation.value)
    cast(list[int], returned["nested"]).append(2)

    assert operation.op is PatchOperationType.ADD
    assert operation.value == {"nested": [1]}
    assert null_operation.has_value
    assert null_operation.to_dict()["value"] is None


def test_remove_operation_ignores_supplied_value() -> None:
    operation = PatchOperation.from_dict({"op": "remove", "path": "/obsolete", "value": 3})

    assert operation.to_dict() == {"op": "remove", "path": "/obsolete"}
    with pytest.raises(AttributeError, match="has no value"):
        _ = operation.value


@pytest.mark.parametrize("op", ["copy", "move", "test", 3])
def test_patch_operation_rejects_unsupported_or_non_string_op(op: object) -> None:
    with pytest.raises(InvalidPatchError):
        PatchOperation(cast(Any, op), "/name", "value")


@pytest.mark.parametrize("path", ["name", 4])
def test_patch_operation_rejects_non_pointer_path(path: object) -> None:
    with pytest.raises(InvalidPatchError):
        PatchOperation("add", cast(Any, path), "value")


def test_patch_operation_rejects_non_json_value_with_value_path() -> None:
    with pytest.raises(InvalidPatchError) as error:
        PatchOperation(
            "add",
            "/metadata",
            {"created": datetime(2026, 7, 14, tzinfo=UTC)},
        )

    assert error.value.path == "/value/created"
    assert error.value.details["reason"] == "NON_JSON_TYPE"


def test_patch_operation_reports_excessive_value_depth_as_invalid_patch() -> None:
    value: object = "leaf"
    for _ in range(MAX_JSON_DEPTH + 1):
        value = [value]

    with pytest.raises(InvalidPatchError) as error:
        PatchOperation("add", "/metadata/deep", value)

    assert error.value.details["reason"] == "JSON_DEPTH_EXCEEDED"


@pytest.mark.parametrize("op", ["add", "replace"])
def test_value_operations_require_value(op: str) -> None:
    with pytest.raises(InvalidPatchError, match="requires a value"):
        PatchOperation(op, "/name")


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({"path": "/name"}, "/op"),
        ({"op": "remove"}, "/path"),
        ({"op": 1, "path": "/name"}, "/op"),
        ({"op": "remove", "path": 1}, "/path"),
    ],
)
def test_patch_operation_mapping_requires_typed_members(
    payload: dict[str, object], path: str
) -> None:
    with pytest.raises(InvalidPatchError) as error:
        PatchOperation.from_dict(payload)

    assert error.value.path == path


def test_patch_proposal_round_trips_stable_shape() -> None:
    payload: dict[str, Any] = {
        "base_model_id": "mdl_house",
        "base_revision": 2,
        "operations": [
            {"op": "replace", "path": "/name", "value": "Courtyard House"},
            {"op": "remove", "path": "/metadata/obsolete"},
        ],
        "provenance": "source:architect-request",
        "rationale": "Rename the design and remove stale metadata.",
    }

    proposal = PatchProposal.from_dict(payload)

    assert proposal.base_revision == 2
    assert proposal.base_model_id == "mdl_house"
    assert proposal.to_dict() == payload


def test_patch_proposal_round_trips_explicit_affected_entities() -> None:
    payload: dict[str, Any] = {
        "base_model_id": "mdl_house",
        "base_revision": 2,
        "operations": [{"op": "replace", "path": "/entities/rooms/rom_a/name", "value": "Study"}],
        "provenance": "agent:patch-generator-v1",
        "rationale": "Assign the selected room semantics.",
        "affected_entity_ids": ["rom_a"],
    }

    proposal = PatchProposal.from_dict(payload)

    assert proposal.affected_entity_ids == ("rom_a",)
    assert proposal.to_dict() == payload


@pytest.mark.parametrize("provenance", ["human", "Human : architect-7", "human/architect-7"])
def test_patch_proposal_cannot_declare_human_identity(provenance: str) -> None:
    with pytest.raises(InvalidPatchError) as error:
        PatchProposal(
            base_model_id="mdl_house",
            base_revision=0,
            operations=(PatchOperation("remove", "/metadata/obsolete"),),
            provenance=provenance,
            rationale="Untrusted generated explanation.",
        )

    assert error.value.path == "/provenance"


def test_patch_proposal_mapping_rejects_identity_fields() -> None:
    with pytest.raises(InvalidPatchError) as error:
        PatchProposal.from_dict(
            {
                "base_model_id": "mdl_house",
                "base_revision": 0,
                "operations": [{"op": "remove", "path": "/metadata/obsolete"}],
                "provenance": "llm:mock",
                "rationale": "Generated explanation.",
                "actor_id": "architect-7",
                "actor_type": "human",
            }
        )

    assert error.value.details["unexpected_fields"] == ["actor_id", "actor_type"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "base_model_id": " ",
            "base_revision": 0,
            "operations": [{"op": "remove", "path": "/x"}],
            "provenance": "human",
            "rationale": "why",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": -1,
            "operations": [{"op": "remove", "path": "/x"}],
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": True,
            "operations": [{"op": "remove", "path": "/x"}],
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": "remove",
            "provenance": "human",
            "rationale": "why",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": ["remove"],
            "provenance": "human",
            "rationale": "why",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": [],
            "provenance": "human",
            "rationale": "why",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": [{"op": "remove", "path": "/x"}],
            "provenance": " ",
            "rationale": "why",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": [{"op": "remove", "path": "/x"}],
            "provenance": "human",
            "rationale": None,
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": [{"op": "remove", "path": "/x"}],
            "provenance": "human",
            "rationale": "why",
            "affected_entity_ids": "rom_a",
        },
        {
            "base_model_id": "mdl_house",
            "base_revision": 0,
            "operations": [{"op": "remove", "path": "/x"}],
            "provenance": "human",
            "rationale": "why",
            "affected_entity_ids": ["rom_a", "rom_a"],
        },
    ],
)
def test_patch_proposal_rejects_malformed_payload(payload: dict[str, Any]) -> None:
    with pytest.raises(InvalidPatchError):
        PatchProposal.from_dict(payload)


def test_patch_proposal_prefixes_nested_operation_error_path() -> None:
    with pytest.raises(InvalidPatchError) as error:
        PatchProposal.from_dict(
            {
                "base_model_id": "mdl_house",
                "base_revision": 0,
                "operations": [
                    {"op": "remove", "path": "/valid"},
                    {"op": "replace", "path": "/missing-value"},
                ],
                "provenance": "test",
                "rationale": "Exercise structured diagnostics.",
            }
        )

    assert error.value.path == "/operations/1/value"
    assert error.value.details["operation_index"] == 1
