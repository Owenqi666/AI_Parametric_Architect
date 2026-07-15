from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any, Literal, cast

import pytest

from ai_parametric_architect.domain import (
    OpeningPanelGeometry,
    OpeningRenderObject,
    Point3,
    PolygonSurfaceGeometry,
    RenderBounds,
    RenderCoordinateSystem,
    RenderFloor,
    RenderIR,
    RenderSourceModel,
    RoomRenderObject,
    VerticalExtrusionGeometry,
    WallRenderObject,
    ensure_json_value,
)


def _ring(elevation: float = 0.0) -> tuple[Point3, ...]:
    return (
        (0.0, 0.0, elevation),
        (2.0, 0.0, elevation),
        (2.0, 2.0, elevation),
        (0.0, 2.0, elevation),
        (0.0, 0.0, elevation),
    )


def _render_ir() -> RenderIR:
    return RenderIR(
        source_model=RenderSourceModel(
            schema_version="1.0.0",
            model_id="mdl_test",
            revision=3,
            root_building_id="bld_test",
        ),
        coordinate_system=RenderCoordinateSystem(origin=(0.0, 0.0, 0.0)),
        bounds=RenderBounds(minimum=(0.0, 0.0, 0.0), maximum=(2.0, 2.0, 2.8)),
        floors=(RenderFloor("flr_ground", "Ground", 0.0, 2.8),),
        objects=(
            RoomRenderObject(
                entity_id="rom_one",
                floor_id="flr_ground",
                name="Room",
                geometry=PolygonSurfaceGeometry(exterior=_ring()),
            ),
            WallRenderObject(
                entity_id="wal_one",
                floor_id="flr_ground",
                name="Wall",
                geometry=VerticalExtrusionGeometry(footprint=_ring(), height=2.8),
            ),
            OpeningRenderObject(
                entity_id="dor_one",
                entity_type="door",
                floor_id="flr_ground",
                name="Door",
                host_wall_id="wal_one",
                geometry=OpeningPanelGeometry(
                    start=(0.5, 0.0, 0.0),
                    end=(1.4, 0.0, 0.0),
                    height=2.1,
                    thickness=0.2,
                ),
            ),
        ),
    )


def test_render_ir_is_immutable_and_serializes_to_a_fresh_strict_json_tree() -> None:
    value = _render_ir()
    first = cast(dict[str, Any], value.to_dict())
    second = cast(dict[str, Any], value.to_dict())

    assert first == second
    assert first is not second
    assert first["render_ir_version"] == "1.0.0"
    assert first["units"] == {"length": "m", "angle": "degree"}
    assert [item["geometry"]["kind"] for item in first["objects"]] == [
        "polygon_surface",
        "vertical_extrusion",
        "opening_panel",
    ]
    first["floors"][0]["name"] = "changed"
    assert value.to_dict()["floors"] != first["floors"]
    ensure_json_value(second)
    with pytest.raises(FrozenInstanceError):
        cast(Any, value).render_ir_version = "2.0.0"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RenderSourceModel("1.0.0", "mdl_test", -1, "bld_test"),
        lambda: RenderCoordinateSystem(
            origin=(0.0, 0.0, math.inf),
        ),
        lambda: RenderBounds((1.0, 0.0, 0.0), (0.0, 1.0, 1.0)),
        lambda: RenderFloor("flr_ground", "Ground", 0.0, 0.0),
        lambda: PolygonSurfaceGeometry(exterior=_ring()[:-1]),
        lambda: PolygonSurfaceGeometry(
            exterior=_ring(),
            holes=(cast(tuple[Point3, ...], ((0.5, 0.5, 1.0),) * 4),),
        ),
        lambda: VerticalExtrusionGeometry(footprint=_ring(), height=0.0),
        lambda: OpeningPanelGeometry(
            start=(0.0, 0.0, 0.0),
            end=(1.0, 0.0, 1.0),
            height=2.0,
            thickness=0.2,
        ),
        lambda: OpeningPanelGeometry(
            start=(0.0, 0.0, 0.0),
            end=(0.0, 0.0, 0.0),
            height=2.0,
            thickness=0.2,
        ),
        lambda: OpeningRenderObject(
            entity_id="dor_one",
            entity_type=cast(Literal["door", "window"], "other"),
            floor_id="flr_ground",
            name="Door",
            host_wall_id="wal_one",
            geometry=OpeningPanelGeometry(
                start=(0.0, 0.0, 0.0),
                end=(1.0, 0.0, 0.0),
                height=2.0,
                thickness=0.2,
            ),
        ),
    ],
)
def test_render_values_reject_invalid_or_non_finite_geometry(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        factory()


def test_render_ir_rejects_duplicate_or_broken_entity_references() -> None:
    valid = _render_ir()
    duplicate_floor = RenderFloor("flr_ground", "Duplicate", 3.0, 2.8)

    with pytest.raises(ValueError, match="floor entity IDs"):
        RenderIR(
            valid.source_model,
            valid.coordinate_system,
            valid.bounds,
            (*valid.floors, duplicate_floor),
            valid.objects,
        )
    with pytest.raises(ValueError, match="host wall"):
        RenderIR(
            valid.source_model,
            valid.coordinate_system,
            valid.bounds,
            valid.floors,
            tuple(item for item in valid.objects if not isinstance(item, WallRenderObject)),
        )
    with pytest.raises(ValueError, match="render_ir_version"):
        RenderIR(
            valid.source_model,
            valid.coordinate_system,
            valid.bounds,
            valid.floors,
            valid.objects,
            render_ir_version="2.0.0",
        )
