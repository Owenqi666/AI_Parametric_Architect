from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    InvalidDesignIntentError,
    PlanningRecord,
    RoomAssignment,
    SpatialConstraint,
    ensure_json_value,
)


def intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=120,
        rooms=("bedroom", "bedroom"),
        orientation="south",
    )


def record() -> PlanningRecord:
    return PlanningRecord(
        intent=intent(),
        assignments=(
            RoomAssignment("rom_a", "bedroom", "Bedroom 1"),
            RoomAssignment("rom_b", "bedroom", "Bedroom 2"),
        ),
        unverified_constraints=("area", "building_type", "orientation"),
    )


def test_planning_record_has_versioned_stable_json_shape() -> None:
    value = record().to_dict()

    assert PLANNING_EXTENSION_KEY == "dev.ai-parametric-architect.design-intent"
    assert value == {
        "schema_version": "1.0.0",
        "intent": {
            "building_type": "house",
            "area": 120,
            "rooms": ["bedroom", "bedroom"],
            "orientation": "south",
        },
        "realization": {
            "scope": "semantic-room-assignment",
            "assignments": [
                {"room_id": "rom_a", "usage": "bedroom", "name": "Bedroom 1"},
                {"room_id": "rom_b", "usage": "bedroom", "name": "Bedroom 2"},
            ],
            "unverified_constraints": ["area", "building_type", "orientation"],
        },
    }
    assert PlanningRecord.from_dict(value) == record()
    ensure_json_value(value)


@pytest.mark.parametrize(
    "arguments",
    [
        {"room_id": "", "usage": "bedroom", "name": "Bedroom"},
        {"room_id": "rom_a", "usage": "", "name": "Bedroom"},
        {"room_id": "rom_a", "usage": "bedroom", "name": " "},
    ],
)
def test_room_assignment_requires_complete_semantics(arguments: dict[str, str]) -> None:
    with pytest.raises(InvalidDesignIntentError):
        RoomAssignment(**arguments)


def test_planning_record_rejects_duplicate_or_mismatched_assignments() -> None:
    duplicate = RoomAssignment("rom_a", "bedroom", "Bedroom 2")
    with pytest.raises(InvalidDesignIntentError, match="unique"):
        PlanningRecord(
            intent=intent(),
            assignments=(RoomAssignment("rom_a", "bedroom", "Bedroom 1"), duplicate),
            unverified_constraints=("area",),
        )
    with pytest.raises(InvalidDesignIntentError, match="requested"):
        PlanningRecord(
            intent=intent(),
            assignments=(
                RoomAssignment("rom_a", "living", "Living Room"),
                RoomAssignment("rom_b", "bedroom", "Bedroom"),
            ),
            unverified_constraints=("area",),
        )


@pytest.mark.parametrize(
    "constraints",
    [
        ("orientation", "area"),
        ("area", "area"),
        ("area", "building_type"),
        ("area", "building_type", "orientation", "site"),
        cast(Any, ["area"]),
        cast(Any, (1,)),
    ],
)
def test_unverified_constraints_are_sorted_unique_tuple(constraints: object) -> None:
    with pytest.raises(InvalidDesignIntentError):
        PlanningRecord(
            intent=intent(),
            assignments=record().assignments,
            unverified_constraints=cast(Any, constraints),
        )


def test_planning_record_requires_supported_version_and_typed_values() -> None:
    with pytest.raises(InvalidDesignIntentError, match="version"):
        PlanningRecord(
            schema_version="2.0.0",
            intent=intent(),
            assignments=record().assignments,
            unverified_constraints=("area",),
        )
    with pytest.raises(InvalidDesignIntentError, match="intent"):
        PlanningRecord(
            intent=cast(Any, {}),
            assignments=record().assignments,
            unverified_constraints=("area",),
        )
    with pytest.raises(InvalidDesignIntentError, match="immutable"):
        PlanningRecord(
            intent=intent(),
            assignments=cast(Any, list(record().assignments)),
            unverified_constraints=("area",),
        )


def test_planning_record_discloses_spatial_constraints_as_unverified() -> None:
    constrained_intent = DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "kitchen"),
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation="adjacent_to",
                target_room_type="living",
            ),
        ),
    )
    assignments = (
        RoomAssignment("rom_a", "living", "Living Room"),
        RoomAssignment("rom_b", "kitchen", "Kitchen"),
    )

    planning_record = PlanningRecord(
        intent=constrained_intent,
        assignments=assignments,
        unverified_constraints=("area", "building_type", "spatial_constraints"),
    )

    assert PlanningRecord.from_dict(planning_record.to_dict()) == planning_record
    with pytest.raises(InvalidDesignIntentError, match="every unverified"):
        PlanningRecord(
            intent=constrained_intent,
            assignments=assignments,
            unverified_constraints=("area", "building_type"),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"extra": True}),
        lambda value: value.update({"intent": []}),
        lambda value: value.update({"realization": []}),
        lambda value: cast(dict[str, Any], value["realization"]).update({"extra": True}),
        lambda value: cast(dict[str, Any], value["realization"]).update({"scope": "other"}),
        lambda value: cast(dict[str, Any], value["realization"]).update({"assignments": "bad"}),
        lambda value: cast(dict[str, Any], value["realization"]).update({"assignments": ["bad"]}),
        lambda value: cast(dict[str, Any], value["realization"]).update(
            {"assignments": [{"room_id": 1, "usage": "bedroom", "name": "Bedroom"}]}
        ),
        lambda value: cast(dict[str, Any], value["realization"]).update(
            {"unverified_constraints": "area"}
        ),
        lambda value: cast(dict[str, Any], value["realization"]).update(
            {"unverified_constraints": [1]}
        ),
        lambda value: value.update({"schema_version": 1}),
    ],
)
def test_from_dict_rejects_malformed_record(mutate: Any) -> None:
    value = record().to_dict()
    mutate(value)

    with pytest.raises(InvalidDesignIntentError):
        PlanningRecord.from_dict(value)
