from __future__ import annotations

import copy
import math
from typing import Any, cast

import pytest

from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.renderer import (
    FloorNotFoundError,
    NoRenderableGeometryError,
    WorldModelRenderIRProjector,
)


@pytest.fixture
def projector() -> WorldModelRenderIRProjector:
    return WorldModelRenderIRProjector(ShapelyGeometryEngine())


def test_render_ir_has_stable_entity_order_native_z_coordinates_and_bounds(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
) -> None:
    first = cast(dict[str, Any], projector.project(valid_simple_house).to_dict())
    second = cast(dict[str, Any], projector.project(valid_simple_house).to_dict())

    assert first == second
    assert first["source_model"] == {
        "schema_version": "1.0.0",
        "model_id": "mdl_simple_house",
        "revision": 0,
        "root_building_id": "bld_simple_house",
    }
    assert first["coordinate_system"] == {
        "type": "local_cartesian",
        "handedness": "right",
        "up_axis": "Z",
        "origin": [0.0, 0.0, 0.0],
    }
    assert first["bounds"] == {"min": [-0.1, -0.1, 0.0], "max": [8.1, 6.1, 2.8]}
    assert [item["entity_id"] for item in first["objects"]] == [
        "rom_living",
        "wal_east",
        "wal_north",
        "wal_south",
        "wal_west",
        "dor_entry",
        "win_south",
    ]
    assert first["objects"][0]["geometry"]["exterior"][0] == [0.1, 0.1, 0.0]
    assert first["objects"][3]["geometry"] == {
        "kind": "vertical_extrusion",
        "footprint": [
            [0.0, 0.1, 0.0],
            [8.0, 0.1, 0.0],
            [8.0, -0.1, 0.0],
            [0.0, -0.1, 0.0],
            [0.0, 0.1, 0.0],
        ],
        "height": 2.8,
    }
    assert first["objects"][-2]["geometry"] == {
        "kind": "opening_panel",
        "start": [1.05, 0.0, 0.0],
        "end": [1.95, 0.0, 0.0],
        "height": 2.1,
        "thickness": 0.2,
    }
    assert first["objects"][-1]["geometry"]["start"] == [4.1, 0.0, 0.9]


def test_projection_is_read_only_and_does_not_share_output_containers(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
) -> None:
    before = copy.deepcopy(valid_simple_house)
    projected = projector.project(valid_simple_house)
    output = cast(dict[str, Any], projected.to_dict())

    output["floors"][0]["name"] = "mutated output"

    assert valid_simple_house == before
    assert projected.to_dict()["floors"] != output["floors"]


def test_all_root_floors_are_sorted_and_an_explicit_floor_filters_objects(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
) -> None:
    valid_simple_house["entities"]["floors"]["flr_upper"] = {
        "id": "flr_upper",
        "entity_type": "floor",
        "name": "Upper",
        "building_id": "bld_simple_house",
        "elevation": 3.0,
        "height": 2.8,
    }
    upper_room = copy.deepcopy(valid_simple_house["entities"]["rooms"]["rom_living"])
    upper_room.update({"id": "rom_upper", "name": "Upper Room", "floor_id": "flr_upper"})
    valid_simple_house["entities"]["rooms"]["rom_upper"] = upper_room

    complete = projector.project(valid_simple_house).to_dict()
    selected = projector.project(valid_simple_house, "flr_upper").to_dict()

    assert [floor["entity_id"] for floor in cast(list[dict[str, Any]], complete["floors"])] == [
        "flr_ground",
        "flr_upper",
    ]
    assert selected["floors"] == [
        {
            "entity_id": "flr_upper",
            "entity_type": "floor",
            "name": "Upper",
            "elevation": 3.0,
            "height": 2.8,
        }
    ]
    assert [item["entity_id"] for item in cast(list[dict[str, Any]], selected["objects"])] == [
        "rom_upper"
    ]
    room_geometry = cast(list[dict[str, Any]], selected["objects"])[0]["geometry"]
    assert cast(dict[str, Any], room_geometry)["exterior"][0][2] == 3.0


def test_requested_floor_must_belong_to_the_root_building(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
) -> None:
    with pytest.raises(FloorNotFoundError, match="flr_missing"):
        projector.project(valid_simple_house, "flr_missing")


def test_empty_selection_is_rejected_without_inventing_floor_geometry(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
) -> None:
    for registry_name in ("rooms", "walls", "doors", "windows", "stairs"):
        valid_simple_house["entities"][registry_name] = {}

    with pytest.raises(NoRenderableGeometryError, match="no renderable"):
        projector.project(valid_simple_house)


@pytest.mark.parametrize("failure", ["origin", "derived-height"])
def test_direct_projection_refuses_non_finite_input_or_derived_coordinates(
    projector: WorldModelRenderIRProjector,
    valid_simple_house: dict[str, Any],
    failure: str,
) -> None:
    if failure == "origin":
        valid_simple_house["coordinate_system"]["origin"][2] = math.inf
    else:
        valid_simple_house["entities"]["floors"]["flr_ground"]["elevation"] = 1e308
        valid_simple_house["entities"]["walls"]["wal_south"]["base_offset"] = 1e308

    with pytest.raises(ValueError, match="finite"):
        projector.project(valid_simple_house)
