"""Geometry-engine port."""

from __future__ import annotations

from typing import Protocol

from ai_parametric_architect.domain import (
    Entity,
    GeometryPrecisionPolicy,
    PolygonProjection,
    RoomAnalysis,
    SegmentAnalysis,
    SegmentProjection,
)


class GeometryEngine(Protocol):
    def analyze_room(self, room: Entity, precision: GeometryPrecisionPolicy) -> RoomAnalysis: ...

    def analyze_segment(self, segment: Entity) -> SegmentAnalysis: ...

    def room_overlap_area(self, first: Entity, second: Entity) -> float: ...

    def wall_footprint(
        self, wall: Entity, precision: GeometryPrecisionPolicy
    ) -> PolygonProjection: ...

    def opening_projection(
        self,
        wall: Entity,
        center_offset: float,
        width: float,
        precision: GeometryPrecisionPolicy,
    ) -> SegmentProjection: ...

    def stair_footprint(
        self, stair: Entity, precision: GeometryPrecisionPolicy
    ) -> PolygonProjection: ...
