from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import RequirementParseError
from ai_parametric_architect.planning.rule_parser import RuleBasedRequirementParser


def test_parses_exact_chinese_mvp_requirement() -> None:
    intent = RuleBasedRequirementParser().parse("设计一个120平方米三室住宅")

    assert intent.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom", "bedroom", "bedroom"],
        "orientation": None,
    }


@pytest.mark.parametrize(
    "requirement",
    [
        "设计一个１２０㎡三室住宅",
        "设计一个120 m²三室住宅",
        "设计一个120 m^2三室住宅",
        "设计一个120平米三室住宅",
        "Design a 120 square metres house with 3 bedrooms.",
        "Create a 120 sqm three bedroom house.",
    ],
    ids=["nfkc", "superscript", "caret", "pingmi", "english-unit", "roadmap-sqm"],
)
def test_normalizes_supported_area_units(requirement: str) -> None:
    intent = RuleBasedRequirementParser().parse(requirement)

    assert intent.area == 120
    assert intent.rooms == ("bedroom",) * 3


def test_parses_explicit_chinese_room_counts_without_counting_dining_as_living() -> None:
    intent = RuleBasedRequirementParser().parse("设计一个１２０㎡三室一厅一餐厅一厨房两卫生间住宅")

    assert intent.rooms == (
        "living",
        "dining",
        "kitchen",
        "bedroom",
        "bedroom",
        "bedroom",
        "bathroom",
        "bathroom",
    )


def test_parses_english_counts_orientation_and_room_order() -> None:
    intent = RuleBasedRequirementParser().parse(
        "Design a 120 square metre south-facing house with 3 bedrooms, "
        "1 living room, 1 dining room, 1 kitchen, and 2 bathrooms."
    )

    assert intent.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": [
            "living",
            "dining",
            "kitchen",
            "bedroom",
            "bedroom",
            "bedroom",
            "bathroom",
            "bathroom",
        ],
        "orientation": "south",
    }


def test_parses_word_and_hyphenated_english_counts() -> None:
    intent = RuleBasedRequirementParser().parse(
        "Design a 120 m2 three-bedroom house with one living room."
    )

    assert intent.rooms == ("living", "bedroom", "bedroom", "bedroom")


def test_rule_parser_is_deterministic() -> None:
    parser = RuleBasedRequirementParser()
    requirement = "Design a south-facing 88.5 m2 apartment with 2 bedrooms."

    first = parser.parse(requirement)
    second = parser.parse(requirement)

    assert first == second
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    ("requirement", "expected_path", "reason"),
    [
        ("", "", "EMPTY_REQUIREMENT"),
        ("   ", "", "EMPTY_REQUIREMENT"),
        ("120平方米三室", "/building_type", "MISSING_REQUIRED_FIELD"),
        ("三室住宅", "/area", "MISSING_REQUIRED_FIELD"),
        ("120平方米住宅", "/rooms", "MISSING_REQUIRED_FIELD"),
        (
            "120 m2 house and office with 1 bedroom",
            "/building_type",
            "AMBIGUOUS_FIELD",
        ),
        ("120 m2 and 140 m2 house with 1 bedroom", "/area", "AMBIGUOUS_FIELD"),
        ("120平方米三室和两卧室住宅", "/rooms", "AMBIGUOUS_FIELD"),
        (
            "120 m2 house with 2 bedrooms and 3 bedrooms",
            "/rooms",
            "AMBIGUOUS_FIELD",
        ),
        (
            "Design an approximately 120 m2 house with 1 bedroom",
            "/area",
            "UNSUPPORTED_AREA_RELATION",
        ),
        (
            "Design a gross area 120 square metres house with 1 bedroom",
            "/area",
            "UNSUPPORTED_AREA_BASIS",
        ),
        ("-120 m2 house with 1 bedroom", "/area", "INVALID_AREA"),
        ("0 m2 house with 1 bedroom", "/area", "INVALID_AREA"),
        ("一百二十平方米三室住宅", "/area", "UNSUPPORTED_AREA_NUMBER"),
        (
            "120平方米或一百平方米住宅三室",
            "/area",
            "UNSUPPORTED_AREA_NUMBER",
        ),
        (
            "120 m2 south-east-facing house with 1 bedroom",
            "/orientation",
            "UNSUPPORTED_ORIENTATION",
        ),
        (
            "120 m2 south and east facing house with 1 bedroom",
            "/orientation",
            "AMBIGUOUS_FIELD",
        ),
        ("120平方米三室办公楼", "/rooms", "AMBIGUOUS_ROOM_SEMANTICS"),
        ("120 m2 house with -2 bedrooms", "/rooms", "INVALID_ROOM_COUNT"),
        ("120平方米住宅 -两卧室", "/rooms", "INVALID_ROOM_COUNT"),
        ("120 m2 house with 0 bedrooms", "/rooms", "INVALID_ROOM_COUNT"),
        ("120 m2 house with 65 bedrooms", "/rooms", "INVALID_ROOM_COUNT"),
        ("120平方米住宅, 一百间卧室", "/rooms", "UNSUPPORTED_ROOM_COUNT"),
    ],
)
def test_rejects_invalid_or_ambiguous_requirements_structurally(
    requirement: str,
    expected_path: str,
    reason: str,
) -> None:
    with pytest.raises(RequirementParseError) as captured:
        RuleBasedRequirementParser().parse(requirement)

    assert captured.value.code == "REQUIREMENT_PARSE_FAILED"
    assert captured.value.path == expected_path
    assert captured.value.details["reason"] == reason


def test_wraps_total_room_overflow_from_domain_validation() -> None:
    with pytest.raises(RequirementParseError) as captured:
        RuleBasedRequirementParser().parse("120 m2 house with 33 bedrooms and 32 bathrooms")

    assert captured.value.path == "/rooms"
    assert captured.value.details == {
        "reason": "INVALID_DESIGN_INTENT",
        "cause": "INVALID_DESIGN_INTENT",
        "cause_details": {"maximum": 64},
    }


def test_rejects_non_string_requirement_without_leaking_type_errors() -> None:
    with pytest.raises(RequirementParseError) as captured:
        RuleBasedRequirementParser().parse(cast(Any, None))

    assert captured.value.details == {"reason": "EMPTY_REQUIREMENT"}
