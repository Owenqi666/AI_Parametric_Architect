from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from ai_parametric_architect.contracts import (
    UnsupportedSchemaVersionError,
    create_model_validator,
    load_model_schema,
)

PROJECT_ROOT = Path(__file__).parents[2]


@pytest.fixture
def valid_model() -> dict[str, Any]:
    path = PROJECT_ROOT / "examples" / "valid_simple_house.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def validation_errors(model: dict[str, Any]) -> list[str]:
    validator = create_model_validator(model.get("schema_version", "1.0.0"))
    return [error.message for error in validator.iter_errors(model)]


def test_schema_is_valid_draft_2020_12() -> None:
    schema = load_model_schema("1.0.0")

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_simple_house_matches_schema(valid_model: dict[str, Any]) -> None:
    assert validation_errors(valid_model) == []


@pytest.mark.parametrize("name", ["invalid_overlap.json", "invalid_opening.json"])
def test_semantic_error_fixtures_still_match_structural_schema(name: str) -> None:
    path = PROJECT_ROOT / "examples" / name
    model = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    assert validation_errors(model) == []


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("revision",), -1),
        (("units", "length"), "mm"),
        (("geometry_settings", "linear_tolerance"), 1e-13),
        (("entities", "walls", "wal_south", "thickness"), 0),
        (("entities", "doors", "dor_entry", "width"), -0.9),
    ],
)
def test_schema_rejects_invalid_values(
    valid_model: dict[str, Any], path: tuple[str, ...], replacement: object
) -> None:
    candidate = copy.deepcopy(valid_model)
    target: dict[str, Any] = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    assert validation_errors(candidate)


def test_schema_rejects_unknown_core_fields(valid_model: dict[str, Any]) -> None:
    candidate = copy.deepcopy(valid_model)
    candidate["entities"]["rooms"]["rom_living"]["llm_guess"] = True

    errors = validation_errors(candidate)

    assert any("Additional properties are not allowed" in message for message in errors)


def test_schema_rejects_wrong_registry_key_type(valid_model: dict[str, Any]) -> None:
    candidate = copy.deepcopy(valid_model)
    wall = candidate["entities"]["walls"].pop("wal_south")
    candidate["entities"]["walls"]["rom_not_a_wall"] = wall

    assert validation_errors(candidate)


def test_loading_unknown_schema_version_is_explicit() -> None:
    with pytest.raises(UnsupportedSchemaVersionError, match=r"2\.0\.0"):
        load_model_schema("2.0.0")


def test_schema_accepts_straight_stair_entity(valid_model: dict[str, Any]) -> None:
    valid_model["entities"]["floors"]["flr_upper"] = {
        "id": "flr_upper",
        "entity_type": "floor",
        "name": "Upper Floor",
        "building_id": "bld_simple_house",
        "elevation": 3.0,
        "height": 2.8,
    }
    valid_model["entities"]["stairs"]["str_main"] = {
        "id": "str_main",
        "entity_type": "stair",
        "name": "Main Stair",
        "from_floor_id": "flr_ground",
        "to_floor_id": "flr_upper",
        "run": {"type": "Segment2D", "start": [2.0, 1.0], "end": [2.0, 4.0]},
        "width": 1.0,
        "step_count": 16,
    }

    assert validation_errors(valid_model) == []
