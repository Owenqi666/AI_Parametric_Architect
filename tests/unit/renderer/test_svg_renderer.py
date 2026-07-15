from __future__ import annotations

import copy
from typing import Any
from xml.etree import ElementTree

import pytest

from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.renderer import (
    FloorNotFoundError,
    NoRenderableGeometryError,
    SvgRenderer,
    SvgStyle,
)


@pytest.fixture
def renderer() -> SvgRenderer:
    return SvgRenderer(ShapelyGeometryEngine())


def test_svg_is_byte_deterministic(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    first = renderer.render(valid_simple_house).encode("utf-8")
    second = renderer.render(valid_simple_house).encode("utf-8")

    assert first == second
    assert b"timestamp" not in first.lower()


def test_svg_has_stable_viewbox_and_fixed_decimal_format(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    root = ElementTree.fromstring(renderer.render(valid_simple_house))

    assert root.attrib["viewBox"] == "-0.600000 -6.600000 9.200000 7.200000"
    assert root.attrib["data-model-id"] == "mdl_simple_house"
    assert root.attrib["data-floor-id"] == "flr_ground"


def test_svg_binds_entities_in_stable_type_and_id_order(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    root = ElementTree.fromstring(renderer.render(valid_simple_house))
    bound_ids = [
        element.attrib["data-entity-id"]
        for element in root.iter()
        if "data-entity-id" in element.attrib
    ]

    assert bound_ids == [
        "flr_ground",
        "rom_living",
        "wal_east",
        "wal_north",
        "wal_south",
        "wal_west",
        "dor_entry",
        "win_south",
    ]


def test_renderer_does_not_mutate_model(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    before = copy.deepcopy(valid_simple_house)

    renderer.render(valid_simple_house)

    assert valid_simple_house == before


def test_requested_floor_must_belong_to_root_building(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    with pytest.raises(FloorNotFoundError, match="flr_missing"):
        renderer.render(valid_simple_house, "flr_missing")


def test_empty_floor_is_rejected_without_inventing_geometry(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    for registry_name in ("rooms", "walls", "doors", "windows", "stairs"):
        valid_simple_house["entities"][registry_name] = {}

    with pytest.raises(NoRenderableGeometryError, match="no renderable"):
        renderer.render(valid_simple_house)


def test_stair_is_rendered_with_entity_binding(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["stairs"]["str_main"] = {
        "id": "str_main",
        "entity_type": "stair",
        "name": "Main Stair",
        "from_floor_id": "flr_ground",
        "to_floor_id": "flr_upper",
        "run": {"type": "Segment2D", "start": [2.0, 1.0], "end": [2.0, 4.0]},
        "width": 1.0,
        "step_count": 16,
    }

    root = ElementTree.fromstring(renderer.render(valid_simple_house))
    stair = next(
        element for element in root.iter() if element.attrib.get("data-entity-id") == "str_main"
    )

    assert stair.attrib["data-step-count"] == "16"


def test_explicit_existing_floor_is_rendered(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    svg = renderer.render(valid_simple_house, "flr_ground")

    assert 'data-floor-id="flr_ground"' in svg


def test_model_without_root_building_floor_is_rejected(
    renderer: SvgRenderer, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["floors"] = {}

    with pytest.raises(FloorNotFoundError, match="has no floor"):
        renderer.render(valid_simple_house)


def test_svg_style_rejects_invalid_presentation_values() -> None:
    with pytest.raises(ValueError, match="padding"):
        SvgStyle(padding=-1.0)
    with pytest.raises(ValueError, match="stroke"):
        SvgStyle(room_stroke_width=0.0)
