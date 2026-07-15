from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from ai_parametric_architect.intent.validator import IntentValidator


@pytest.fixture
def valid_intent() -> dict[str, Any]:
    return {
        "building_type": "house",
        "area": 120,
        "rooms": ["living", "bedroom"],
        "orientation": None,
    }


def test_valid_expanded_intent_has_no_issues(valid_intent: dict[str, Any]) -> None:
    assert IntentValidator().validate(valid_intent) == ()


def test_valid_compact_intent_with_constraint_has_no_issues() -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "room_requirements": [
            {"room_type": "living", "count": 1},
            {"room_type": "bedroom", "count": 2},
        ],
        "orientation": "south",
        "spatial_constraints": [
            {
                "source_room_type": "living",
                "relation": "adjacent_to",
                "target_room_type": "bedroom",
                "required": True,
            }
        ],
    }
    before = copy.deepcopy(intent)

    assert IntentValidator().validate(intent) == ()
    assert intent == before
    assert "room_requirements" in intent
    assert "rooms" not in intent


@pytest.mark.parametrize(
    "relation",
    [
        "adjacent_to",
        "near",
        "separated_from",
        "north_of",
        "south_of",
        "east_of",
        "west_of",
    ],
)
def test_all_v1_spatial_relations_are_supported(
    valid_intent: dict[str, Any],
    relation: str,
) -> None:
    valid_intent["spatial_constraints"] = [
        {
            "source_room_type": "living",
            "relation": relation,
            "target_room_type": "bedroom",
            "required": False,
        }
    ]

    assert IntentValidator().validate(valid_intent) == ()


def test_validation_is_deterministic(valid_intent: dict[str, Any]) -> None:
    valid_intent.update(
        {
            "building_type": "House",
            "area": 0,
            "rooms": [],
            "orientation": "northeast",
            "unexpected": True,
        }
    )
    validator = IntentValidator()

    first = validator.validate(valid_intent)
    second = validator.validate(valid_intent)

    assert first == second
    assert first == tuple(sorted(first, key=lambda issue: (issue.code, issue.path, issue.message)))
    assert {
        "INTENT_SCHEMA_ADDITIONAL_PROPERTIES",
        "INTENT_SCHEMA_ENUM",
        "INTENT_SCHEMA_EXCLUSIVE_MINIMUM",
        "INTENT_SCHEMA_MIN_ITEMS",
        "INTENT_SCHEMA_PATTERN",
    }.issubset({issue.code for issue in first})


def test_validation_does_not_mutate_input(valid_intent: dict[str, Any]) -> None:
    before = copy.deepcopy(valid_intent)

    IntentValidator().validate(valid_intent)

    assert valid_intent == before


@pytest.mark.parametrize("area", [math.inf, -math.inf, math.nan])
def test_non_finite_area_is_a_structured_issue(
    valid_intent: dict[str, Any],
    area: float,
) -> None:
    valid_intent["area"] = area

    assert [issue.to_dict() for issue in IntentValidator().validate(valid_intent)] == [
        {
            "code": "INTENT_SEMANTIC_INVALID",
            "severity": "error",
            "path": "/area",
            "entity_ids": [],
            "message": "Design intent numbers must be finite.",
            "details": {"reason": "NON_FINITE_NUMBER"},
        }
    ]


def test_out_of_float_range_area_is_a_structured_issue(
    valid_intent: dict[str, Any],
) -> None:
    valid_intent["area"] = 10**400

    issues = IntentValidator().validate(valid_intent)

    assert [issue.code for issue in issues] == ["INTENT_SEMANTIC_INVALID"]
    assert issues[0].path == "/area"
    assert issues[0].message == "Design area must be a positive finite number."
    assert issues[0].details == {}


def test_non_json_input_returns_an_issue_instead_of_raising(
    valid_intent: dict[str, Any],
) -> None:
    valid_intent["spatial_constraints"] = {"not", "json"}

    issues = IntentValidator().validate(valid_intent)

    assert len(issues) == 1
    assert issues[0].code == "INTENT_JSON_INVALID"
    assert issues[0].path == "/spatial_constraints"


def test_self_referencing_constraint_is_a_semantic_issue(
    valid_intent: dict[str, Any],
) -> None:
    valid_intent["spatial_constraints"] = [
        {
            "source_room_type": "bedroom",
            "relation": "near",
            "target_room_type": "bedroom",
            "required": True,
        }
    ]

    issues = IntentValidator().validate(valid_intent)

    assert [issue.code for issue in issues] == ["INTENT_SEMANTIC_INVALID"]
    assert issues[0].path == "/spatial_constraints/0/target_room_type"
    assert issues[0].details == {}


def test_constraint_room_types_must_be_requested(valid_intent: dict[str, Any]) -> None:
    valid_intent["spatial_constraints"] = [
        {
            "source_room_type": "garage",
            "relation": "separated_from",
            "target_room_type": "garden",
            "required": True,
        }
    ]

    issues = IntentValidator().validate(valid_intent)

    assert [issue.code for issue in issues] == ["INTENT_SEMANTIC_INVALID"]
    assert issues[0].path == "/spatial_constraints/0"
    assert issues[0].details == {"missing_room_types": ["garage", "garden"]}


def test_compact_total_room_count_is_bounded_semantically() -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "room_requirements": [
            {"room_type": "bedroom", "count": 64},
            {"room_type": "living", "count": 1},
        ],
    }

    issues = IntentValidator().validate(intent)

    assert [issue.code for issue in issues] == ["INTENT_SEMANTIC_INVALID"]
    assert issues[0].path == "/room_requirements"
    assert issues[0].details == {"maximum": 64}


def test_compact_room_types_must_be_unique() -> None:
    intent = {
        "building_type": "house",
        "area": 120,
        "room_requirements": [
            {"room_type": "bedroom", "count": 1},
            {"room_type": "bedroom", "count": 2},
        ],
    }

    issues = IntentValidator().validate(intent)

    assert [issue.code for issue in issues] == ["INTENT_SEMANTIC_INVALID"]
    assert issues[0].path == "/room_requirements"
    assert issues[0].details == {}


def test_duplicate_spatial_constraints_are_rejected_structurally(
    valid_intent: dict[str, Any],
) -> None:
    constraint = {
        "source_room_type": "living",
        "relation": "adjacent_to",
        "target_room_type": "bedroom",
        "required": True,
    }
    valid_intent["spatial_constraints"] = [constraint, copy.deepcopy(constraint)]

    issues = IntentValidator().validate(valid_intent)

    assert [issue.code for issue in issues] == ["INTENT_SCHEMA_UNIQUE_ITEMS"]
    assert issues[0].path == "/spatial_constraints"
