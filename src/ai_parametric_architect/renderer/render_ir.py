"""Deterministic, read-only projection from the validated World Model to Render IR."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from ai_parametric_architect.domain import (
    Entity,
    GeometryPrecisionPolicy,
    ModelDocument,
    OpeningPanelGeometry,
    OpeningRenderObject,
    Point3,
    PolygonSurfaceGeometry,
    RenderBounds,
    RenderCoordinateSystem,
    RenderFloor,
    RenderIR,
    RenderObject,
    RenderSourceModel,
    RoomRenderObject,
    VerticalExtrusionGeometry,
    WallRenderObject,
)
from ai_parametric_architect.ports import (
    FloorNotFoundError,
    GeometryEngine,
    NoRenderableGeometryError,
)


def _registries(model: ModelDocument) -> Mapping[str, Mapping[str, Entity]]:
    return cast(Mapping[str, Mapping[str, Entity]], model["entities"])


def _finite_number(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        numeric = float(value)
    except OverflowError as error:
        raise ValueError(f"{field_name} must be a finite number") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be a finite number")
    return numeric


def _finite_sum(field_name: str, *values: float) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as error:
        raise ValueError(f"{field_name} produced a non-finite coordinate") from error
    if not math.isfinite(result):
        raise ValueError(f"{field_name} produced a non-finite coordinate")
    return result


def _point3(value: object, elevation: float | None = None) -> Point3:
    coordinates = cast(Sequence[object], value)
    x_coordinate = _finite_number(coordinates[0], "x coordinate")
    y_coordinate = _finite_number(coordinates[1], "y coordinate")
    if elevation is None:
        z_coordinate = _finite_number(coordinates[2], "z coordinate")
    else:
        z_coordinate = elevation
    return (x_coordinate, y_coordinate, z_coordinate)


def _room_geometry(room: Entity, elevation: float) -> PolygonSurfaceGeometry:
    geometry = cast(Mapping[str, Any], room["geometry"])
    exterior_values = cast(Sequence[object], geometry["exterior"])
    hole_values = cast(Sequence[Sequence[object]], geometry["holes"])
    return PolygonSurfaceGeometry(
        exterior=tuple(_point3(value, elevation) for value in exterior_values),
        holes=tuple(tuple(_point3(value, elevation) for value in ring) for ring in hole_values),
    )


def _elevate_ring(points: Sequence[tuple[float, float]], elevation: float) -> tuple[Point3, ...]:
    return tuple((point[0], point[1], elevation) for point in points)


def _object_points(item: RenderObject) -> tuple[Point3, ...]:
    if isinstance(item, RoomRenderObject):
        return (
            *item.geometry.exterior,
            *(point for ring in item.geometry.holes for point in ring),
        )
    if isinstance(item, WallRenderObject):
        top = tuple(
            (point[0], point[1], _finite_sum("wall top", point[2], item.geometry.height))
            for point in item.geometry.footprint
        )
        return (*item.geometry.footprint, *top)
    top_elevation = _finite_sum("opening top", item.geometry.start[2], item.geometry.height)
    return (
        item.geometry.start,
        item.geometry.end,
        (item.geometry.start[0], item.geometry.start[1], top_elevation),
        (item.geometry.end[0], item.geometry.end[1], top_elevation),
    )


class WorldModelRenderIRProjector:
    """Build an immutable visualization projection without changing model geometry."""

    def __init__(self, geometry: GeometryEngine) -> None:
        self._geometry = geometry

    def project(self, model: ModelDocument, floor_id: str | None = None) -> RenderIR:
        precision = GeometryPrecisionPolicy.from_model(model)
        registries = _registries(model)
        selected_floors = self._select_floors(model, registries, floor_id)
        floor_entities = {entity_id: floor for entity_id, floor in selected_floors}
        floors = tuple(
            RenderFloor(
                entity_id=entity_id,
                name=str(floor["name"]),
                elevation=_finite_number(floor["elevation"], "floor elevation"),
                height=_finite_number(floor["height"], "floor height"),
            )
            for entity_id, floor in selected_floors
        )

        room_objects = self._rooms(registries, floor_entities)
        walls, wall_objects = self._walls(registries, floor_entities, precision)
        opening_objects = self._openings(registries, walls, floor_entities, precision)
        objects: tuple[RenderObject, ...] = (*room_objects, *wall_objects, *opening_objects)
        if not objects:
            selected_ids = ", ".join(repr(entity_id) for entity_id, _floor in selected_floors)
            raise NoRenderableGeometryError(
                f"Selected floor(s) {selected_ids} contain no renderable room, wall, "
                "door, or window geometry"
            )

        points = tuple(point for item in objects for point in _object_points(item))
        bounds = RenderBounds(
            minimum=(
                min(point[0] for point in points),
                min(point[1] for point in points),
                min(point[2] for point in points),
            ),
            maximum=(
                max(point[0] for point in points),
                max(point[1] for point in points),
                max(point[2] for point in points),
            ),
        )
        coordinate_system = cast(Mapping[str, object], model["coordinate_system"])
        return RenderIR(
            source_model=RenderSourceModel(
                schema_version=str(model["schema_version"]),
                model_id=str(model["model_id"]),
                revision=cast(int, model["revision"]),
                root_building_id=str(model["root_building_id"]),
            ),
            coordinate_system=RenderCoordinateSystem(
                origin=_point3(coordinate_system["origin"]),
            ),
            bounds=bounds,
            floors=floors,
            objects=objects,
        )

    @staticmethod
    def _select_floors(
        model: ModelDocument,
        registries: Mapping[str, Mapping[str, Entity]],
        requested_floor_id: str | None,
    ) -> tuple[tuple[str, Entity], ...]:
        root_building_id = str(model["root_building_id"])
        eligible = {
            entity_id: floor
            for entity_id, floor in registries["floors"].items()
            if floor["building_id"] == root_building_id
        }
        if requested_floor_id is not None:
            floor = eligible.get(requested_floor_id)
            if floor is None:
                raise FloorNotFoundError(
                    f"Floor {requested_floor_id!r} is not part of "
                    f"root building {root_building_id!r}"
                )
            return ((requested_floor_id, floor),)
        if not eligible:
            raise FloorNotFoundError(f"Root building {root_building_id!r} has no floor")
        return tuple(
            sorted(
                eligible.items(),
                key=lambda item: (
                    _finite_number(item[1]["elevation"], "floor elevation"),
                    item[0],
                ),
            )
        )

    @staticmethod
    def _rooms(
        registries: Mapping[str, Mapping[str, Entity]],
        floors: Mapping[str, Entity],
    ) -> tuple[RoomRenderObject, ...]:
        values: list[RoomRenderObject] = []
        for entity_id, room in sorted(registries["rooms"].items()):
            floor_id = str(room["floor_id"])
            floor = floors.get(floor_id)
            if floor is None:
                continue
            elevation = _finite_number(floor["elevation"], "floor elevation")
            values.append(
                RoomRenderObject(
                    entity_id=entity_id,
                    floor_id=floor_id,
                    name=str(room["name"]),
                    geometry=_room_geometry(room, elevation),
                )
            )
        return tuple(values)

    def _walls(
        self,
        registries: Mapping[str, Mapping[str, Entity]],
        floors: Mapping[str, Entity],
        precision: GeometryPrecisionPolicy,
    ) -> tuple[dict[str, Entity], tuple[WallRenderObject, ...]]:
        selected: dict[str, Entity] = {}
        values: list[WallRenderObject] = []
        for entity_id, wall in sorted(registries["walls"].items()):
            floor_id = str(wall["floor_id"])
            floor = floors.get(floor_id)
            if floor is None:
                continue
            base_elevation = _finite_sum(
                "wall base",
                _finite_number(floor["elevation"], "floor elevation"),
                _finite_number(wall["base_offset"], "wall base offset"),
            )
            projection = self._geometry.wall_footprint(wall, precision)
            selected[entity_id] = wall
            values.append(
                WallRenderObject(
                    entity_id=entity_id,
                    floor_id=floor_id,
                    name=str(wall["name"]),
                    geometry=VerticalExtrusionGeometry(
                        footprint=_elevate_ring(projection.exterior, base_elevation),
                        height=_finite_number(wall["height"], "wall height"),
                    ),
                )
            )
        return selected, tuple(values)

    def _openings(
        self,
        registries: Mapping[str, Mapping[str, Entity]],
        walls: Mapping[str, Entity],
        floors: Mapping[str, Entity],
        precision: GeometryPrecisionPolicy,
    ) -> tuple[OpeningRenderObject, ...]:
        values: list[OpeningRenderObject] = []
        registry_types: tuple[tuple[str, Literal["door", "window"]], ...] = (
            ("doors", "door"),
            ("windows", "window"),
        )
        for registry_name, entity_type in registry_types:
            for entity_id, opening in sorted(registries[registry_name].items()):
                wall_id = str(opening["host_wall_id"])
                wall = walls.get(wall_id)
                if wall is None:
                    continue
                floor_id = str(wall["floor_id"])
                floor = floors[floor_id]
                wall_base = _finite_sum(
                    "wall base",
                    _finite_number(floor["elevation"], "floor elevation"),
                    _finite_number(wall["base_offset"], "wall base offset"),
                )
                panel_base = _finite_sum(
                    "opening base",
                    wall_base,
                    _finite_number(opening["bottom_offset"], "opening bottom offset"),
                )
                projection = self._geometry.opening_projection(
                    wall,
                    _finite_number(opening["center_offset"], "opening center offset"),
                    _finite_number(opening["width"], "opening width"),
                    precision,
                )
                values.append(
                    OpeningRenderObject(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        floor_id=floor_id,
                        name=str(opening["name"]),
                        host_wall_id=wall_id,
                        geometry=OpeningPanelGeometry(
                            start=(projection.start[0], projection.start[1], panel_base),
                            end=(projection.end[0], projection.end[1], panel_base),
                            height=_finite_number(opening["height"], "opening height"),
                            thickness=_finite_number(wall["thickness"], "wall thickness"),
                        ),
                    )
                )
        return tuple(values)
