"""Shapely-backed geometry calculations with neutral public results."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

from shapely.geometry import Polygon
from shapely.validation import explain_validity

from ai_parametric_architect.domain import (
    Entity,
    GeometryPrecisionPolicy,
    Point2,
    PolygonProjection,
    Ring2,
    RoomAnalysis,
    SegmentAnalysis,
    SegmentProjection,
)
from ai_parametric_architect.domain.numbers import finite_float


def _point(value: object) -> Point2:
    coordinates = cast(Sequence[int | float], value)
    x_coordinate = finite_float(coordinates[0])
    y_coordinate = finite_float(coordinates[1])
    return (
        math.inf if x_coordinate is None else x_coordinate,
        math.inf if y_coordinate is None else y_coordinate,
    )


def _segment_points(segment: Entity) -> tuple[Point2, Point2]:
    return _point(segment["start"]), _point(segment["end"])


def _room_rings(room: Entity) -> tuple[Ring2, tuple[Ring2, ...]]:
    geometry = cast(Mapping[str, Any], room["geometry"])
    exterior_values = cast(Sequence[object], geometry["exterior"])
    hole_values = cast(Sequence[Sequence[object]], geometry["holes"])
    exterior = tuple(_point(value) for value in exterior_values)
    holes = tuple(tuple(_point(value) for value in ring) for ring in hole_values)
    return exterior, holes


def _all_finite(rings: Sequence[Sequence[Point2]]) -> bool:
    return all(math.isfinite(value) for ring in rings for point in ring for value in point)


def _polygon(room: Entity) -> Polygon:
    exterior, holes = _room_rings(room)
    return Polygon(exterior, holes)


def _rectangle_around_segment(
    segment: Entity,
    left_offset: float,
    right_offset: float,
    precision: GeometryPrecisionPolicy,
) -> PolygonProjection:
    start, end = _segment_points(segment)
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length = math.hypot(delta_x, delta_y)
    if not math.isfinite(length) or precision.is_zero_length(length):
        raise ValueError("Cannot project a footprint around a non-finite or zero-length segment")
    if not math.isfinite(left_offset) or not math.isfinite(right_offset):
        raise ValueError("Footprint offsets must be finite")

    normal_x = -delta_y / length
    normal_y = delta_x / length

    def offset(point: Point2, distance: float) -> Point2:
        return (point[0] + normal_x * distance, point[1] + normal_y * distance)

    first = offset(start, left_offset)
    exterior = (
        first,
        offset(end, left_offset),
        offset(end, right_offset),
        offset(start, right_offset),
        first,
    )
    if not all(math.isfinite(value) for point in exterior for value in point):
        raise ValueError("Footprint projection produced non-finite coordinates")
    return PolygonProjection(exterior=exterior)


class ShapelyGeometryEngine:
    """Concrete geometry engine; no Shapely object crosses its public boundary."""

    def analyze_room(self, room: Entity, precision: GeometryPrecisionPolicy) -> RoomAnalysis:
        exterior, holes = _room_rings(room)
        rings = (exterior, *holes)
        finite = _all_finite(rings)
        if not finite:
            return RoomAnalysis(
                has_finite_coordinates=False,
                rings_closed=False,
                is_valid=False,
                area=0.0,
                validity_reason="Non-finite coordinate",
            )

        rings_closed = all(
            bool(ring) and precision.points_equal(ring[0], ring[-1]) for ring in rings
        )
        x_values = [point[0] for ring in rings for point in ring]
        y_values = [point[1] for ring in rings for point in ring]
        bounding_width = max(x_values) - min(x_values)
        bounding_height = max(y_values) - min(y_values)
        if not all(
            math.isfinite(value)
            for value in (bounding_width, bounding_height, bounding_width * bounding_height)
        ):
            return RoomAnalysis(
                has_finite_coordinates=True,
                rings_closed=rings_closed,
                is_valid=False,
                area=0.0,
                validity_reason="Non-finite derived polygon bounds",
            )
        polygon = Polygon(exterior, holes)
        derived_area = float(polygon.area)
        finite_area = math.isfinite(derived_area)
        area = derived_area if finite_area else 0.0
        valid = bool(polygon.is_valid) and finite_area
        return RoomAnalysis(
            has_finite_coordinates=True,
            rings_closed=rings_closed,
            is_valid=valid,
            area=area,
            validity_reason=(
                None
                if valid
                else (
                    explain_validity(polygon) if finite_area else "Non-finite derived polygon area"
                )
            ),
        )

    def analyze_segment(self, segment: Entity) -> SegmentAnalysis:
        start, end = _segment_points(segment)
        finite_coordinates = all(math.isfinite(value) for point in (start, end) for value in point)
        length = math.dist(start, end) if finite_coordinates else 0.0
        finite_geometry = finite_coordinates and math.isfinite(length)
        return SegmentAnalysis(
            has_finite_coordinates=finite_geometry,
            length=length if finite_geometry else 0.0,
        )

    def room_overlap_area(self, first: Entity, second: Entity) -> float:
        area = float(_polygon(first).intersection(_polygon(second)).area)
        if not math.isfinite(area):
            raise ValueError("Room overlap produced a non-finite area")
        return area

    def wall_footprint(self, wall: Entity, precision: GeometryPrecisionPolicy) -> PolygonProjection:
        thickness = finite_float(wall["thickness"])
        if thickness is None or precision.is_zero_length(thickness):
            raise ValueError("Wall thickness must be finite and positive")

        alignment = str(wall["alignment"])
        if alignment == "center":
            left_offset, right_offset = thickness / 2, -thickness / 2
        elif alignment == "left":
            left_offset, right_offset = thickness, 0.0
        elif alignment == "right":
            left_offset, right_offset = 0.0, -thickness
        else:
            raise ValueError(f"Unsupported wall alignment: {alignment}")
        axis = cast(Entity, wall["axis"])
        return _rectangle_around_segment(axis, left_offset, right_offset, precision)

    def opening_projection(
        self,
        wall: Entity,
        center_offset: float,
        width: float,
        precision: GeometryPrecisionPolicy,
    ) -> SegmentProjection:
        axis = cast(Entity, wall["axis"])
        start, end = _segment_points(axis)
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        length = math.hypot(delta_x, delta_y)
        if not math.isfinite(length) or precision.is_zero_length(length):
            raise ValueError("Cannot place an opening on a non-finite or zero-length wall")
        if (
            not math.isfinite(center_offset)
            or not math.isfinite(width)
            or precision.is_zero_length(width)
        ):
            raise ValueError("Opening placement values must be finite and width must be positive")

        unit_x = delta_x / length
        unit_y = delta_y / length

        def point_at(offset: float) -> Point2:
            return (start[0] + unit_x * offset, start[1] + unit_y * offset)

        half_width = width / 2
        projection = SegmentProjection(
            start=point_at(center_offset - half_width),
            end=point_at(center_offset + half_width),
        )
        if not all(
            math.isfinite(value) for point in (projection.start, projection.end) for value in point
        ):
            raise ValueError("Opening projection produced non-finite coordinates")
        return projection

    def stair_footprint(
        self, stair: Entity, precision: GeometryPrecisionPolicy
    ) -> PolygonProjection:
        width = finite_float(stair["width"])
        if width is None or precision.is_zero_length(width):
            raise ValueError("Stair width must be finite and positive")
        run = cast(Entity, stair["run"])
        return _rectangle_around_segment(run, width / 2, -width / 2, precision)
