from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    PlanningRecord,
    RoomAssignment,
    derive_affected_entity_ids,
)


def _record(*, area: int) -> PlanningRecord:
    return PlanningRecord(
        intent=DesignIntent(
            building_type="house",
            area=area,
            rooms=("bedroom",),
        ),
        assignments=(RoomAssignment("rom_a", "bedroom", "Bedroom 1"),),
        unverified_constraints=("area", "building_type"),
    )


def test_entity_differences_are_reported_once_in_canonical_order() -> None:
    before: dict[str, Any] = {
        "entities": {
            "rooms": {
                "rom_b": {"id": "rom_b", "name": "B"},
                "rom_a": {"id": "rom_a", "name": "A"},
            },
            "walls": {"wal_a": {"id": "wal_a", "length": 5}},
        }
    }
    after: dict[str, Any] = deepcopy(before)
    after["entities"]["rooms"]["rom_a"]["name"] = "Bedroom 1"
    del after["entities"]["rooms"]["rom_b"]
    after["entities"]["walls"]["wal_a"]["length"] = 6

    assert derive_affected_entity_ids(before, after) == (
        "rom_a",
        "rom_b",
        "wal_a",
    )
    assert derive_affected_entity_ids(before, before) == ()


def test_changed_planning_record_reports_assignments_even_without_entity_delta() -> None:
    before = {
        "extensions": {PLANNING_EXTENSION_KEY: _record(area=50).to_dict()},
    }
    after = {
        "extensions": {PLANNING_EXTENSION_KEY: _record(area=60).to_dict()},
    }

    assert derive_affected_entity_ids(before, after) == ("rom_a",)
    assert derive_affected_entity_ids(before, {}) == ("rom_a",)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"entities": []}, "entity registry"),
        ({"entities": {1: {}}}, "registry name"),
        ({"entities": {"rooms": []}}, "entity registry"),
        ({"entities": {"rooms": {1: {}}}}, "entity ID"),
        ({"extensions": []}, "extensions"),
        (
            {"extensions": {PLANNING_EXTENSION_KEY: []}},
            "planning record",
        ),
        (
            {"extensions": {PLANNING_EXTENSION_KEY: {"invalid": True}}},
            "planning record",
        ),
    ],
)
def test_malformed_validated_context_is_reported_as_validator_contract_failure(
    document: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        derive_affected_entity_ids(cast(dict[str, Any], document), {})
