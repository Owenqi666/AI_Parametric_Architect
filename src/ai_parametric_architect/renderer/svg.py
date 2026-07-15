"""Deterministic SVG floor-plan renderer."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from xml.etree import ElementTree

from ai_parametric_architect.domain import (
    Entity,
    GeometryPrecisionPolicy,
    ModelDocument,
    Point2,
    PolygonProjection,
)
from ai_parametric_architect.ports import (
    FloorNotFoundError,
    GeometryEngine,
    NoRenderableGeometryError,
)

SVG_MEDIA_TYPE = "image/svg+xml"


@dataclass(frozen=True, slots=True)
class SvgStyle:
    """Presentation-only settings; none of these values alter source geometry."""

    padding: float = 0.5
    room_fill: str = "#f6f2e8"
    room_stroke: str = "#8c7f6b"
    wall_fill: str = "#30343b"
    wall_stroke: str = "#17191d"
    door_stroke: str = "#fffdf7"
    window_stroke: str = "#3c91e6"
    stair_fill: str = "#d9dde3"
    stair_stroke: str = "#626975"
    room_stroke_width: float = 0.01
    wall_stroke_width: float = 0.005
    stair_stroke_width: float = 0.01
    opening_stroke_scale: float = 1.2

    def __post_init__(self) -> None:
        if not math.isfinite(self.padding) or self.padding < 0:
            raise ValueError("SVG padding cannot be negative")
        positive_values = (
            self.room_stroke_width,
            self.wall_stroke_width,
            self.stair_stroke_width,
            self.opening_stroke_scale,
        )
        if not all(math.isfinite(value) and value > 0 for value in positive_values):
            raise ValueError("SVG stroke widths and scale must be finite and positive")


def _registries(model: ModelDocument) -> Mapping[str, Mapping[str, Entity]]:
    return cast(Mapping[str, Mapping[str, Entity]], model["entities"])


def _point(value: object) -> Point2:
    coordinates = cast(Sequence[int | float], value)
    return (float(coordinates[0]), float(coordinates[1]))


def _room_projection(room: Entity) -> PolygonProjection:
    geometry = cast(Mapping[str, Any], room["geometry"])
    exterior_values = cast(Sequence[object], geometry["exterior"])
    hole_values = cast(Sequence[Sequence[object]], geometry["holes"])
    exterior = tuple(_point(value) for value in exterior_values)
    holes = tuple(tuple(_point(value) for value in ring) for ring in hole_values)
    return PolygonProjection(exterior=exterior, holes=holes)


def _format_points(points: Sequence[Point2], precision: GeometryPrecisionPolicy) -> str:
    return " ".join(f"{precision.format_number(x)},{precision.format_number(y)}" for x, y in points)


def _format_path(projection: PolygonProjection, precision: GeometryPrecisionPolicy) -> str:
    commands: list[str] = []
    for ring in (projection.exterior, *projection.holes):
        first, *remaining = ring
        commands.append(
            " ".join(
                (
                    f"M {precision.format_number(first[0])} {precision.format_number(first[1])}",
                    *(
                        f"L {precision.format_number(point[0])} {precision.format_number(point[1])}"
                        for point in remaining
                    ),
                    "Z",
                )
            )
        )
    return " ".join(commands)


class SvgRenderer:
    media_type = SVG_MEDIA_TYPE

    def __init__(self, geometry: GeometryEngine, style: SvgStyle | None = None) -> None:
        self._geometry = geometry
        self._style = SvgStyle() if style is None else style

    def render(self, model: ModelDocument, floor_id: str | None = None) -> str:
        precision = GeometryPrecisionPolicy.from_model(model)
        registries = _registries(model)
        selected_floor_id = self._select_floor(model, registries, floor_id)

        rooms = {
            entity_id: entity
            for entity_id, entity in registries["rooms"].items()
            if entity["floor_id"] == selected_floor_id
        }
        walls = {
            entity_id: entity
            for entity_id, entity in registries["walls"].items()
            if entity["floor_id"] == selected_floor_id
        }
        doors = {
            entity_id: entity
            for entity_id, entity in registries["doors"].items()
            if entity["host_wall_id"] in walls
        }
        windows = {
            entity_id: entity
            for entity_id, entity in registries["windows"].items()
            if entity["host_wall_id"] in walls
        }
        stairs = {
            entity_id: entity
            for entity_id, entity in registries["stairs"].items()
            if entity["from_floor_id"] == selected_floor_id
        }

        room_projections = {
            entity_id: _room_projection(entity) for entity_id, entity in sorted(rooms.items())
        }
        wall_projections = {
            entity_id: self._geometry.wall_footprint(entity, precision)
            for entity_id, entity in sorted(walls.items())
        }
        stair_projections = {
            entity_id: self._geometry.stair_footprint(entity, precision)
            for entity_id, entity in sorted(stairs.items())
        }

        projections = (
            *room_projections.values(),
            *wall_projections.values(),
            *stair_projections.values(),
        )
        all_points = [
            point
            for projection in projections
            for ring in (projection.exterior, *projection.holes)
            for point in ring
        ]
        if not all_points:
            raise NoRenderableGeometryError(
                f"Floor {selected_floor_id!r} contains no renderable room, wall, or stair geometry"
            )

        root = self._create_root(model, selected_floor_id, all_points, precision)
        floor_group = ElementTree.SubElement(
            root,
            "g",
            {
                "id": f"floor-{selected_floor_id}",
                "data-entity-id": selected_floor_id,
                "data-entity-type": "floor",
                "transform": "scale(1 -1)",
            },
        )

        room_group = ElementTree.SubElement(floor_group, "g", {"id": "rooms"})
        for entity_id, projection in room_projections.items():
            ElementTree.SubElement(
                room_group,
                "path",
                {
                    "id": f"room-{entity_id}",
                    "data-entity-id": entity_id,
                    "data-entity-type": "room",
                    "d": _format_path(projection, precision),
                    "fill": self._style.room_fill,
                    "fill-rule": "evenodd",
                    "stroke": self._style.room_stroke,
                    "stroke-width": precision.format_number(self._style.room_stroke_width),
                },
            )

        wall_group = ElementTree.SubElement(floor_group, "g", {"id": "walls"})
        for entity_id, projection in wall_projections.items():
            ElementTree.SubElement(
                wall_group,
                "polygon",
                {
                    "id": f"wall-{entity_id}",
                    "data-entity-id": entity_id,
                    "data-entity-type": "wall",
                    "points": _format_points(projection.exterior, precision),
                    "fill": self._style.wall_fill,
                    "stroke": self._style.wall_stroke,
                    "stroke-width": precision.format_number(self._style.wall_stroke_width),
                },
            )

        self._render_openings(floor_group, doors, walls, "door", self._style.door_stroke, precision)
        self._render_openings(
            floor_group, windows, walls, "window", self._style.window_stroke, precision
        )

        stair_group = ElementTree.SubElement(floor_group, "g", {"id": "stairs"})
        for entity_id, projection in stair_projections.items():
            stair = stairs[entity_id]
            ElementTree.SubElement(
                stair_group,
                "polygon",
                {
                    "id": f"stair-{entity_id}",
                    "data-entity-id": entity_id,
                    "data-entity-type": "stair",
                    "data-step-count": str(stair["step_count"]),
                    "points": _format_points(projection.exterior, precision),
                    "fill": self._style.stair_fill,
                    "stroke": self._style.stair_stroke,
                    "stroke-width": precision.format_number(self._style.stair_stroke_width),
                },
            )

        return ElementTree.tostring(root, encoding="unicode", short_empty_elements=True)

    @staticmethod
    def _select_floor(
        model: ModelDocument,
        registries: Mapping[str, Mapping[str, Entity]],
        requested_floor_id: str | None,
    ) -> str:
        root_building_id = str(model["root_building_id"])
        eligible = {
            entity_id: floor
            for entity_id, floor in registries["floors"].items()
            if floor["building_id"] == root_building_id
        }
        if requested_floor_id is not None:
            if requested_floor_id not in eligible:
                raise FloorNotFoundError(
                    f"Floor {requested_floor_id!r} is not part of "
                    f"root building {root_building_id!r}"
                )
            return requested_floor_id
        if not eligible:
            raise FloorNotFoundError(f"Root building {root_building_id!r} has no floor")
        return min(
            eligible,
            key=lambda entity_id: (float(eligible[entity_id]["elevation"]), entity_id),
        )

    def _create_root(
        self,
        model: ModelDocument,
        floor_id: str,
        points: Sequence[Point2],
        precision: GeometryPrecisionPolicy,
    ) -> ElementTree.Element:
        minimum_x = min(point[0] for point in points) - self._style.padding
        maximum_x = max(point[0] for point in points) + self._style.padding
        minimum_y = min(point[1] for point in points) - self._style.padding
        maximum_y = max(point[1] for point in points) + self._style.padding
        view_box = " ".join(
            precision.format_number(value)
            for value in (
                minimum_x,
                -maximum_y,
                maximum_x - minimum_x,
                maximum_y - minimum_y,
            )
        )
        return ElementTree.Element(
            "svg",
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "version": "1.1",
                "viewBox": view_box,
                "data-model-id": str(model["model_id"]),
                "data-revision": str(model["revision"]),
                "data-building-id": str(model["root_building_id"]),
                "data-floor-id": floor_id,
            },
        )

    def _render_openings(
        self,
        floor_group: ElementTree.Element,
        openings: Mapping[str, Entity],
        walls: Mapping[str, Entity],
        entity_type: str,
        stroke: str,
        precision: GeometryPrecisionPolicy,
    ) -> None:
        group = ElementTree.SubElement(floor_group, "g", {"id": f"{entity_type}s"})
        for entity_id, opening in sorted(openings.items()):
            wall = walls[str(opening["host_wall_id"])]
            projection = self._geometry.opening_projection(
                wall,
                float(opening["center_offset"]),
                float(opening["width"]),
                precision,
            )
            stroke_width = float(wall["thickness"]) * self._style.opening_stroke_scale
            ElementTree.SubElement(
                group,
                "line",
                {
                    "id": f"{entity_type}-{entity_id}",
                    "data-entity-id": entity_id,
                    "data-entity-type": entity_type,
                    "data-host-wall-id": str(opening["host_wall_id"]),
                    "x1": precision.format_number(projection.start[0]),
                    "y1": precision.format_number(projection.start[1]),
                    "x2": precision.format_number(projection.end[0]),
                    "y2": precision.format_number(projection.end[1]),
                    "stroke": stroke,
                    "stroke-width": precision.format_number(stroke_width),
                    "stroke-linecap": "butt",
                },
            )
