from __future__ import annotations

import copy
from importlib.resources import files
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from ai_parametric_architect.intent.models import (
    MAX_INTENT_ROOMS,
    MAX_SPATIAL_CONSTRAINTS,
    DesignIntent,
    RoomRequirement,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.intent.schema import (
    UnsupportedIntentSchemaVersionError,
    create_intent_schema_validator,
    load_intent_schema,
)


def test_design_intent_schema_is_valid_draft_2020_12() -> None:
    schema = load_intent_schema("1.0.0")

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_design_intent_schema_is_a_packaged_resource() -> None:
    resource = files("ai_parametric_architect.intent.schemas").joinpath(
        "design-intent-1.0.0.schema.json"
    )

    assert resource.is_file()


def test_loading_schema_returns_a_fresh_copy() -> None:
    first = load_intent_schema()
    first["title"] = "caller mutation"

    assert load_intent_schema()["title"] != "caller mutation"


def test_loading_unknown_intent_schema_version_is_explicit() -> None:
    with pytest.raises(UnsupportedIntentSchemaVersionError, match=r"2\.0\.0"):
        load_intent_schema("2.0.0")


def test_current_expanded_payload_matches_contract() -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom", "bedroom", "bedroom"],
        "orientation": "south",
    }

    assert list(create_intent_schema_validator().iter_errors(cast(Any, intent))) == []


def test_compact_payload_and_spatial_constraint_match_contract() -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "room_requirements": [
            {"room_type": "bedroom", "count": 2},
            {"room_type": "living", "count": 1},
        ],
        "spatial_constraints": [
            {
                "source_room_type": "living",
                "relation": "adjacent_to",
                "target_room_type": "bedroom",
                "required": True,
            }
        ],
    }

    assert list(create_intent_schema_validator().iter_errors(cast(Any, intent))) == []


def test_reusable_definitions_are_referenced_by_root_properties() -> None:
    schema = load_intent_schema()
    properties = cast(dict[str, Any], schema["properties"])
    room_requirements = cast(dict[str, Any], properties["room_requirements"])
    spatial_constraints = cast(dict[str, Any], properties["spatial_constraints"])

    assert room_requirements["items"] == {"$ref": "#/$defs/RoomRequirement"}
    assert room_requirements["uniqueItems"] is True
    assert spatial_constraints["items"] == {"$ref": "#/$defs/SpatialConstraint"}
    assert {"RoomRequirement", "SpatialConstraint"}.issubset(schema["$defs"])


def test_schema_limits_and_relations_match_public_intent_models() -> None:
    schema = load_intent_schema()
    properties = cast(dict[str, Any], schema["properties"])
    definitions = cast(dict[str, Any], schema["$defs"])
    room_requirement = cast(dict[str, Any], definitions["RoomRequirement"])
    room_properties = cast(dict[str, Any], room_requirement["properties"])
    constraint = cast(dict[str, Any], definitions["SpatialConstraint"])
    constraint_properties = cast(dict[str, Any], constraint["properties"])

    assert properties["rooms"]["maxItems"] == MAX_INTENT_ROOMS
    assert room_properties["count"]["maximum"] == MAX_INTENT_ROOMS
    assert properties["spatial_constraints"]["maxItems"] == MAX_SPATIAL_CONSTRAINTS
    assert constraint_properties["relation"]["enum"] == [
        relation.value for relation in SpatialRelation
    ]


def test_public_model_expanded_and_compact_outputs_match_schema() -> None:
    intent = DesignIntent(
        building_type="house",
        area=120,
        room_requirements=(
            RoomRequirement("living", 1),
            RoomRequirement("bedroom", 2),
        ),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="living",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="bedroom",
                required=True,
            ),
        ),
    )
    validator = create_intent_schema_validator()

    assert list(validator.iter_errors(cast(Any, intent.to_dict()))) == []
    assert list(validator.iter_errors(cast(Any, intent.to_compact_dict()))) == []


@pytest.mark.parametrize("included", [(), ("rooms", "room_requirements")])
def test_exactly_one_room_representation_is_required(included: tuple[str, ...]) -> None:
    intent: dict[str, object] = {"building_type": "house", "area": 120}
    if "rooms" in included:
        intent["rooms"] = ["bedroom"]
    if "room_requirements" in included:
        intent["room_requirements"] = [{"room_type": "bedroom", "count": 1}]

    assert list(create_intent_schema_validator().iter_errors(cast(Any, intent)))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("building_type",), "House"),
        (("area",), 0),
        (("area",), True),
        (("rooms",), []),
        (("rooms",), ["bedroom"] * 65),
        (("rooms", 0), "Bedroom"),
        (("orientation",), "northeast"),
    ],
)
def test_schema_rejects_invalid_canonical_values(
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    intent: dict[str, Any] = {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom"],
        "orientation": None,
    }
    candidate = copy.deepcopy(intent)
    if len(path) == 1:
        candidate[cast(str, path[0])] = replacement
    else:
        candidate[cast(str, path[0])][cast(int, path[1])] = replacement

    assert list(create_intent_schema_validator().iter_errors(cast(Any, candidate)))


@pytest.mark.parametrize(
    "constraint",
    [
        {
            "source_room_type": "living",
            "relation": "touches",
            "target_room_type": "bedroom",
            "required": True,
        },
        {
            "source_room_type": "living",
            "relation": "near",
            "target_room_type": "bedroom",
        },
        {
            "source_room_type": "living",
            "relation": "near",
            "target_room_type": "bedroom",
            "required": True,
            "distance": 2,
        },
    ],
)
def test_schema_rejects_malformed_spatial_constraints(
    constraint: dict[str, object],
) -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "rooms": ["living", "bedroom"],
        "spatial_constraints": [constraint],
    }

    assert list(create_intent_schema_validator().iter_errors(cast(Any, intent)))


def test_schema_rejects_exact_duplicate_compact_room_requirements() -> None:
    requirement = {"room_type": "bedroom", "count": 2}
    intent = {
        "building_type": "house",
        "area": 120,
        "room_requirements": [requirement, copy.deepcopy(requirement)],
    }

    errors = list(create_intent_schema_validator().iter_errors(cast(Any, intent)))

    assert len(errors) == 1
    assert errors[0].validator == "uniqueItems"
    assert list(errors[0].absolute_path) == ["room_requirements"]
