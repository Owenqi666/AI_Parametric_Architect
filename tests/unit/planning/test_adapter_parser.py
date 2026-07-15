from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    InvalidDesignIntentError,
    RequirementParseError,
)
from ai_parametric_architect.planning.adapter_parser import LanguageModelRequirementParser


class StubAdapter:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requirements: list[str] = []

    def extract_design_intent(self, requirement: str) -> Mapping[str, object]:
        self.requirements.append(requirement)
        return cast(Mapping[str, object], self.result)


class InvalidIntentAdapter:
    def extract_design_intent(self, requirement: str) -> Mapping[str, object]:
        raise InvalidDesignIntentError(
            f"Adapter rejected {requirement}.",
            path="/rooms",
            details={"adapter_reason": "invalid-room-list"},
        )


class FailingAdapter:
    def extract_design_intent(self, requirement: str) -> Mapping[str, object]:
        raise RuntimeError(f"provider unavailable for {requirement}")


def test_validates_adapter_payload_and_preserves_input_and_determinism() -> None:
    rooms = ["living", "bedroom"]
    payload: dict[str, object] = {
        "building_type": "house",
        "area": 120,
        "rooms": rooms,
        "orientation": "south",
    }
    adapter = StubAdapter(payload)
    parser = LanguageModelRequirementParser(adapter)
    requirement = "  Original provider-neutral requirement  "

    first = parser.parse(requirement)
    second = parser.parse(requirement)
    rooms.append("kitchen")

    assert first == second
    assert first == DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "bedroom"),
        orientation="south",
    )
    assert adapter.requirements == [requirement, requirement]


@pytest.mark.parametrize("requirement", ["", "  \n\t", None, 42])
def test_rejects_empty_or_non_string_input_before_calling_adapter(requirement: object) -> None:
    adapter = StubAdapter({})

    with pytest.raises(RequirementParseError) as captured:
        LanguageModelRequirementParser(adapter).parse(cast(Any, requirement))

    assert captured.value.path == ""
    assert captured.value.details == {"reason": "EMPTY_REQUIREMENT"}
    assert adapter.requirements == []


@pytest.mark.parametrize("payload", [None, [], "json text", 123])
def test_rejects_non_mapping_adapter_output(payload: object) -> None:
    with pytest.raises(RequirementParseError) as captured:
        LanguageModelRequirementParser(StubAdapter(payload)).parse("valid requirement")

    assert captured.value.code == "REQUIREMENT_PARSE_FAILED"
    assert captured.value.path == ""
    assert captured.value.details == {"reason": "ADAPTER_OUTPUT_INVALID"}


@pytest.mark.parametrize(
    ("payload", "expected_path"),
    [
        ({}, ""),
        (
            {
                "building_type": "house",
                "area": 120,
                "rooms": ["bedroom"],
                "unexpected": True,
            },
            "",
        ),
        ({"building_type": "House", "area": 120, "rooms": ["bedroom"]}, "/building_type"),
        ({"building_type": "house", "area": 0, "rooms": ["bedroom"]}, "/area"),
        ({"building_type": "house", "area": True, "rooms": ["bedroom"]}, "/area"),
        ({"building_type": "house", "area": 120, "rooms": []}, "/rooms"),
        ({"building_type": "house", "area": 120, "rooms": ["Bedroom"]}, "/rooms/0"),
        (
            {
                "building_type": "house",
                "area": 120,
                "rooms": ["bedroom"],
                "orientation": "northeast",
            },
            "/orientation",
        ),
        (
            {
                "building_type": "house",
                "area": 120,
                "rooms": ["bedroom"] * 65,
            },
            "/rooms",
        ),
    ],
)
def test_wraps_invalid_domain_payloads(
    payload: Mapping[str, object],
    expected_path: str,
) -> None:
    with pytest.raises(RequirementParseError) as captured:
        LanguageModelRequirementParser(StubAdapter(payload)).parse("valid requirement")

    assert captured.value.code == "REQUIREMENT_PARSE_FAILED"
    assert captured.value.path == expected_path
    assert captured.value.details["reason"] == "ADAPTER_OUTPUT_INVALID"
    assert captured.value.details["cause"] == "INVALID_DESIGN_INTENT"


def test_wraps_invalid_design_intent_raised_directly_by_adapter() -> None:
    with pytest.raises(RequirementParseError) as captured:
        LanguageModelRequirementParser(InvalidIntentAdapter()).parse("invalid rooms")

    assert captured.value.path == "/rooms"
    assert captured.value.details == {
        "reason": "ADAPTER_OUTPUT_INVALID",
        "cause": "INVALID_DESIGN_INTENT",
        "cause_details": {"adapter_reason": "invalid-room-list"},
    }


def test_wraps_numeric_overflow_from_domain_construction() -> None:
    payload: dict[str, object] = {
        "building_type": "house",
        "area": 10**400,
        "rooms": ["bedroom"],
    }

    with pytest.raises(RequirementParseError) as captured:
        LanguageModelRequirementParser(StubAdapter(payload)).parse("huge area")

    assert captured.value.path == "/area"
    assert captured.value.details == {
        "reason": "ADAPTER_OUTPUT_INVALID",
        "cause": "INVALID_DESIGN_INTENT",
        "cause_details": {},
    }


def test_does_not_misclassify_unrelated_adapter_failures_as_domain_errors() -> None:
    with pytest.raises(RuntimeError, match="provider unavailable"):
        LanguageModelRequirementParser(FailingAdapter()).parse("valid requirement")
