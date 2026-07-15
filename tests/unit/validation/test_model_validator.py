from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    PlanningRecord,
    RoomAssignment,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.validation import ModelValidator, ValidationLevel


@pytest.fixture
def validator() -> ModelValidator:
    return ModelValidator(ShapelyGeometryEngine())


def issue_codes(validator: ModelValidator, model: dict[str, Any]) -> set[str]:
    return {issue.code for issue in validator.validate(model).issues}


def test_valid_simple_house_has_no_issues(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    report = validator.validate(valid_simple_house)

    assert report.valid
    assert report.issues == ()


def test_invalid_overlap_fixture_returns_required_code(
    validator: ModelValidator, invalid_overlap: dict[str, Any]
) -> None:
    report = validator.validate(invalid_overlap)

    assert not report.valid
    assert [issue.code for issue in report.issues] == ["ROOM_OVERLAP"]


def test_invalid_opening_fixture_returns_required_code(
    validator: ModelValidator, invalid_opening: dict[str, Any]
) -> None:
    assert "OPENING_OUT_OF_WALL_BOUNDS" in issue_codes(validator, invalid_opening)


def test_key_id_equality_and_global_uniqueness_are_checked(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    walls = valid_simple_house["entities"]["walls"]
    walls["wal_alias"] = copy.deepcopy(walls["wal_south"])

    codes = issue_codes(validator, valid_simple_house)

    assert "KEY_ID_MISMATCH" in codes
    assert "DUPLICATE_ENTITY_ID" in codes


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("root", "ROOT_BUILDING_NOT_FOUND"),
        ("room_floor", "ROOM_FLOOR_NOT_FOUND"),
        ("wall_floor", "WALL_FLOOR_NOT_FOUND"),
        ("opening_host", "OPENING_HOST_NOT_FOUND"),
    ],
)
def test_reference_integrity(
    validator: ModelValidator,
    valid_simple_house: dict[str, Any],
    mutation: str,
    expected_code: str,
) -> None:
    if mutation == "root":
        valid_simple_house["root_building_id"] = "bld_missing"
    elif mutation == "room_floor":
        valid_simple_house["entities"]["rooms"]["rom_living"]["floor_id"] = "flr_missing"
    elif mutation == "wall_floor":
        valid_simple_house["entities"]["walls"]["wal_south"]["floor_id"] = "flr_missing"
    else:
        valid_simple_house["entities"]["doors"]["dor_entry"]["host_wall_id"] = "wal_missing"

    assert expected_code in issue_codes(validator, valid_simple_house)


def test_strict_json_boundary_rejects_non_finite_coordinate(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["walls"]["wal_south"]["axis"]["end"][0] = math.inf

    assert issue_codes(validator, valid_simple_house) == {"JSON_TREE_INVALID"}


def test_l1_detects_unclosed_and_self_intersecting_polygon(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    room = valid_simple_house["entities"]["rooms"]["rom_living"]
    room["geometry"]["exterior"] = [
        [0.0, 0.0],
        [2.0, 2.0],
        [0.0, 2.0],
        [2.0, 0.0],
        [0.5, 0.0],
    ]

    codes = issue_codes(validator, valid_simple_house)

    assert "POLYGON_NOT_CLOSED" in codes
    assert "ROOM_SELF_INTERSECTION" in codes


def test_l1_detects_zero_area_and_wall_length(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    room = valid_simple_house["entities"]["rooms"]["rom_living"]
    room["geometry"]["exterior"] = [
        [0.0, 0.0],
        [1.0, 0.0],
        [2.0, 0.0],
        [3.0, 0.0],
        [0.0, 0.0],
    ]
    wall = valid_simple_house["entities"]["walls"]["wal_south"]
    wall["axis"]["end"] = list(wall["axis"]["start"])

    codes = issue_codes(validator, valid_simple_house)

    assert "ROOM_ZERO_AREA" in codes
    assert "WALL_ZERO_LENGTH" in codes


def test_l2_detects_opening_overlap(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["windows"]["win_overlap"] = {
        "id": "win_overlap",
        "entity_type": "window",
        "name": "Overlapping Window",
        "host_wall_id": "wal_south",
        "center_offset": 1.6,
        "width": 0.6,
        "height": 1.0,
        "bottom_offset": 0.5,
    }

    assert "OPENING_OVERLAP" in issue_codes(validator, valid_simple_house)


def test_schema_errors_stop_geometry_rules(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["unexpected"] = True

    report = validator.validate(valid_simple_house)

    assert not report.valid
    assert {issue.code for issue in report.issues} == {"SCHEMA_ADDITIONAL_PROPERTIES"}


def test_validation_does_not_mutate_model(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    before = copy.deepcopy(valid_simple_house)

    validator.validate(valid_simple_house)

    assert valid_simple_house == before


def test_rules_are_registered_in_level_order(validator: ModelValidator) -> None:
    levels = [rule.level for rule in validator.rules]

    assert levels == sorted(levels)
    assert levels[0] is ValidationLevel.BASIC_GEOMETRY


def test_unsupported_schema_version_is_reported_without_running_rules(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["schema_version"] = "2.0.0"

    assert [issue.code for issue in validator.validate(valid_simple_house).issues] == [
        "SCHEMA_VERSION_UNSUPPORTED"
    ]


def test_non_finite_precision_is_rejected_at_strict_json_boundary(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["geometry_settings"]["linear_tolerance"] = math.nan

    assert [issue.code for issue in validator.validate(valid_simple_house).issues] == [
        "JSON_TREE_INVALID"
    ]


def test_non_finite_coordinate_system_origin_is_rejected_at_json_boundary(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["coordinate_system"]["origin"][2] = math.inf

    assert issue_codes(validator, valid_simple_house) == {"JSON_TREE_INVALID"}


def test_root_building_requires_a_floor(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["floors"] = {}
    for registry_name in ("rooms", "walls", "doors", "windows", "stairs"):
        valid_simple_house["entities"][registry_name] = {}

    assert "BUILDING_HAS_NO_FLOORS" in issue_codes(validator, valid_simple_house)


def test_floor_must_reference_existing_building(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["floors"]["flr_ground"]["building_id"] = "bld_missing"

    assert "FLOOR_BUILDING_NOT_FOUND" in issue_codes(validator, valid_simple_house)


def _add_stair(model: dict[str, Any], *, to_floor_id: str, to_elevation: float = 3.0) -> None:
    if to_floor_id != "flr_missing":
        model["entities"]["floors"][to_floor_id] = {
            "id": to_floor_id,
            "entity_type": "floor",
            "name": "Upper Floor",
            "building_id": "bld_simple_house",
            "elevation": to_elevation,
            "height": 2.8,
        }
    model["entities"]["stairs"]["str_main"] = {
        "id": "str_main",
        "entity_type": "stair",
        "name": "Main Stair",
        "from_floor_id": "flr_ground",
        "to_floor_id": to_floor_id,
        "run": {"type": "Segment2D", "start": [2.0, 1.0], "end": [2.0, 4.0]},
        "width": 1.0,
        "step_count": 16,
    }


def test_stair_references_and_elevation_are_validated(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    missing_floor = copy.deepcopy(valid_simple_house)
    _add_stair(missing_floor, to_floor_id="flr_missing")
    assert "STAIR_FLOOR_NOT_FOUND" in issue_codes(validator, missing_floor)

    invalid_elevation = copy.deepcopy(valid_simple_house)
    _add_stair(invalid_elevation, to_floor_id="flr_upper", to_elevation=0.0)
    assert "STAIR_ELEVATION_INVALID" in issue_codes(validator, invalid_elevation)


def test_stair_cannot_connect_different_buildings(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["buildings"]["bld_other"] = {
        "id": "bld_other",
        "entity_type": "building",
        "name": "Other Building",
    }
    _add_stair(valid_simple_house, to_floor_id="flr_other", to_elevation=3.0)
    valid_simple_house["entities"]["floors"]["flr_other"]["building_id"] = "bld_other"

    assert "STAIR_BUILDING_MISMATCH" in issue_codes(validator, valid_simple_house)


def test_non_finite_entity_geometry_values_are_rejected_at_json_boundary(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["walls"]["wal_east"]["height"] = math.inf
    valid_simple_house["entities"]["windows"]["win_south"]["center_offset"] = math.nan
    _add_stair(valid_simple_house, to_floor_id="flr_upper")
    valid_simple_house["entities"]["stairs"]["str_main"]["run"]["end"][1] = math.inf

    assert issue_codes(validator, valid_simple_house) == {"JSON_TREE_INVALID"}


def test_adjacent_rooms_do_not_count_as_overlap(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["rooms"]["rom_adjacent"] = {
        "id": "rom_adjacent",
        "entity_type": "room",
        "name": "Adjacent Room",
        "floor_id": "flr_ground",
        "geometry": {
            "type": "Polygon2D",
            "exterior": [[7.9, 0.1], [9.9, 0.1], [9.9, 5.9], [7.9, 5.9], [7.9, 0.1]],
            "holes": [],
        },
    }

    assert "ROOM_OVERLAP" not in issue_codes(validator, valid_simple_house)


def test_out_of_float_range_json_number_returns_issue_instead_of_crashing(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["walls"]["wal_south"]["axis"]["end"][0] = 10**400

    assert issue_codes(validator, valid_simple_house) == {"MODEL_COORDINATE_RANGE_EXCEEDED"}


def test_dimensions_below_precision_are_rejected(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["walls"]["wal_south"]["thickness"] = 1e-20
    valid_simple_house["entities"]["doors"]["dor_entry"]["width"] = 1e-20

    assert "GEOMETRY_DIMENSION_BELOW_TOLERANCE" in issue_codes(validator, valid_simple_house)


def _planning_record(*, room_id: str = "rom_living") -> dict[str, object]:
    return PlanningRecord(
        intent=DesignIntent(
            building_type="house",
            area=120,
            rooms=("bedroom",),
            orientation="south",
        ),
        assignments=(RoomAssignment(room_id, "bedroom", "Bedroom"),),
        unverified_constraints=("area", "building_type", "orientation"),
    ).to_dict()


def test_valid_planning_record_must_match_authoritative_room_semantics(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    room = valid_simple_house["entities"]["rooms"]["rom_living"]
    room["usage"] = "bedroom"
    room["name"] = "Bedroom"
    valid_simple_house["extensions"] = {PLANNING_EXTENSION_KEY: _planning_record()}

    report = validator.validate(valid_simple_house)

    assert report.valid
    room["usage"] = "living"
    issue = next(
        issue
        for issue in validator.validate(valid_simple_house).issues
        if issue.code == "PLANNING_ASSIGNMENT_MISMATCH"
    )
    assert issue.path == "/entities/rooms/rom_living"
    assert issue.entity_ids == ("rom_living",)
    assert issue.details["expected_usage"] == "bedroom"
    assert issue.details["actual_usage"] == "living"


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-object",
        {
            "schema_version": "2.0.0",
            "intent": {},
            "realization": {},
        },
    ],
)
def test_malformed_owned_planning_record_is_rejected(
    validator: ModelValidator,
    valid_simple_house: dict[str, Any],
    payload: object,
) -> None:
    valid_simple_house["extensions"] = {PLANNING_EXTENSION_KEY: payload}

    issue = next(
        issue
        for issue in validator.validate(valid_simple_house).issues
        if issue.code == "PLANNING_RECORD_INVALID"
    )

    assert issue.path.startswith("/extensions/dev.ai-parametric-architect.design-intent")


def test_planning_record_cannot_reference_a_missing_room(
    validator: ModelValidator, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["extensions"] = {
        PLANNING_EXTENSION_KEY: _planning_record(room_id="rom_missing")
    }

    issue = next(
        issue
        for issue in validator.validate(valid_simple_house).issues
        if issue.code == "PLANNING_ASSIGNMENT_ROOM_NOT_FOUND"
    )

    assert issue.entity_ids == ("rom_missing",)
