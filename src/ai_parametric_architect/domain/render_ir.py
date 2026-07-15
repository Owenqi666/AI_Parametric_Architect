"""Immutable, versioned values for the derived Three.js render boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

RENDER_IR_VERSION: Final = "1.0.0"

type Point3 = tuple[float, float, float]


def _require_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_finite(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        numeric = float(value)
    except OverflowError as error:
        raise ValueError(f"{field_name} must be a finite number") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be a finite number")
    return numeric


def _require_positive(value: object, field_name: str) -> None:
    if _require_finite(value, field_name) <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_point(point: object, field_name: str) -> None:
    if not isinstance(point, tuple) or len(point) != 3:
        raise ValueError(f"{field_name} must be an immutable three-dimensional point")
    for coordinate in point:
        _require_finite(coordinate, field_name)


def _require_horizontal_ring(ring: object, field_name: str) -> None:
    if not isinstance(ring, tuple) or len(ring) < 4:
        raise ValueError(f"{field_name} must be an immutable closed ring")
    for point in ring:
        _require_point(point, field_name)
    if ring[0] != ring[-1]:
        raise ValueError(f"{field_name} must be closed")
    elevation = ring[0][2]
    if any(point[2] != elevation for point in ring):
        raise ValueError(f"{field_name} must be horizontal")


def _point_dict(point: Point3) -> list[float]:
    return [point[0], point[1], point[2]]


@dataclass(frozen=True, slots=True)
class RenderSourceModel:
    """Identity of the authoritative revision from which an IR was projected."""

    schema_version: str
    model_id: str
    revision: int
    root_building_id: str

    def __post_init__(self) -> None:
        _require_string(self.schema_version, "schema_version")
        _require_string(self.model_id, "model_id")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("revision must be a non-negative integer")
        _require_string(self.root_building_id, "root_building_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "revision": self.revision,
            "root_building_id": self.root_building_id,
        }


@dataclass(frozen=True, slots=True)
class RenderCoordinateSystem:
    """Model-native local Cartesian frame; Three.js must not reinterpret it as Y-up."""

    origin: Point3

    def __post_init__(self) -> None:
        _require_point(self.origin, "origin")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "local_cartesian",
            "handedness": "right",
            "up_axis": "Z",
            "origin": _point_dict(self.origin),
        }


@dataclass(frozen=True, slots=True)
class RenderBounds:
    minimum: Point3
    maximum: Point3

    def __post_init__(self) -> None:
        _require_point(self.minimum, "bounds minimum")
        _require_point(self.maximum, "bounds maximum")
        if any(lower > upper for lower, upper in zip(self.minimum, self.maximum, strict=True)):
            raise ValueError("bounds minimum cannot exceed bounds maximum")

    def to_dict(self) -> dict[str, object]:
        return {"min": _point_dict(self.minimum), "max": _point_dict(self.maximum)}


@dataclass(frozen=True, slots=True)
class RenderFloor:
    entity_id: str
    name: str
    elevation: float
    height: float

    def __post_init__(self) -> None:
        _require_string(self.entity_id, "floor entity_id")
        _require_string(self.name, "floor name")
        _require_finite(self.elevation, "floor elevation")
        _require_positive(self.height, "floor height")

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "floor",
            "name": self.name,
            "elevation": self.elevation,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class PolygonSurfaceGeometry:
    exterior: tuple[Point3, ...]
    holes: tuple[tuple[Point3, ...], ...] = ()

    def __post_init__(self) -> None:
        _require_horizontal_ring(self.exterior, "polygon exterior")
        if not isinstance(self.holes, tuple):
            raise ValueError("polygon holes must be an immutable tuple")
        for hole in self.holes:
            _require_horizontal_ring(hole, "polygon hole")
            if hole[0][2] != self.exterior[0][2]:
                raise ValueError("polygon holes must share the exterior elevation")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "polygon_surface",
            "exterior": [_point_dict(point) for point in self.exterior],
            "holes": [[_point_dict(point) for point in ring] for ring in self.holes],
        }


@dataclass(frozen=True, slots=True)
class VerticalExtrusionGeometry:
    footprint: tuple[Point3, ...]
    height: float

    def __post_init__(self) -> None:
        _require_horizontal_ring(self.footprint, "extrusion footprint")
        _require_positive(self.height, "extrusion height")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "vertical_extrusion",
            "footprint": [_point_dict(point) for point in self.footprint],
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class OpeningPanelGeometry:
    start: Point3
    end: Point3
    height: float
    thickness: float

    def __post_init__(self) -> None:
        _require_point(self.start, "opening start")
        _require_point(self.end, "opening end")
        if self.start[2] != self.end[2]:
            raise ValueError("opening panel endpoints must share an elevation")
        if self.start == self.end:
            raise ValueError("opening panel must have a non-zero width")
        _require_positive(self.height, "opening height")
        _require_positive(self.thickness, "opening thickness")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "opening_panel",
            "start": _point_dict(self.start),
            "end": _point_dict(self.end),
            "height": self.height,
            "thickness": self.thickness,
        }


@dataclass(frozen=True, slots=True)
class RoomRenderObject:
    entity_id: str
    floor_id: str
    name: str
    geometry: PolygonSurfaceGeometry

    def __post_init__(self) -> None:
        _require_string(self.entity_id, "room entity_id")
        _require_string(self.floor_id, "room floor_id")
        _require_string(self.name, "room name")
        if not isinstance(self.geometry, PolygonSurfaceGeometry):
            raise ValueError("room geometry must be a polygon surface")

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "room",
            "floor_id": self.floor_id,
            "name": self.name,
            "geometry": self.geometry.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class WallRenderObject:
    entity_id: str
    floor_id: str
    name: str
    geometry: VerticalExtrusionGeometry

    def __post_init__(self) -> None:
        _require_string(self.entity_id, "wall entity_id")
        _require_string(self.floor_id, "wall floor_id")
        _require_string(self.name, "wall name")
        if not isinstance(self.geometry, VerticalExtrusionGeometry):
            raise ValueError("wall geometry must be a vertical extrusion")

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "wall",
            "floor_id": self.floor_id,
            "name": self.name,
            "geometry": self.geometry.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OpeningRenderObject:
    entity_id: str
    entity_type: Literal["door", "window"]
    floor_id: str
    name: str
    host_wall_id: str
    geometry: OpeningPanelGeometry

    def __post_init__(self) -> None:
        _require_string(self.entity_id, "opening entity_id")
        if self.entity_type not in {"door", "window"}:
            raise ValueError("opening entity_type must be door or window")
        _require_string(self.floor_id, "opening floor_id")
        _require_string(self.name, "opening name")
        _require_string(self.host_wall_id, "opening host_wall_id")
        if not isinstance(self.geometry, OpeningPanelGeometry):
            raise ValueError("opening geometry must be an opening panel")

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "floor_id": self.floor_id,
            "name": self.name,
            "host_wall_id": self.host_wall_id,
            "geometry": self.geometry.to_dict(),
        }


type RenderObject = RoomRenderObject | WallRenderObject | OpeningRenderObject


@dataclass(frozen=True, slots=True)
class RenderIR:
    """One complete, immutable visualization projection of a validated revision."""

    source_model: RenderSourceModel
    coordinate_system: RenderCoordinateSystem
    bounds: RenderBounds
    floors: tuple[RenderFloor, ...]
    objects: tuple[RenderObject, ...]
    render_ir_version: str = RENDER_IR_VERSION

    def __post_init__(self) -> None:
        if self.render_ir_version != RENDER_IR_VERSION:
            raise ValueError(f"render_ir_version must be {RENDER_IR_VERSION!r}")
        if not isinstance(self.source_model, RenderSourceModel):
            raise ValueError("source_model must be a RenderSourceModel")
        if not isinstance(self.coordinate_system, RenderCoordinateSystem):
            raise ValueError("coordinate_system must be a RenderCoordinateSystem")
        if not isinstance(self.bounds, RenderBounds):
            raise ValueError("bounds must be RenderBounds")
        if not isinstance(self.floors, tuple) or not self.floors:
            raise ValueError("floors must be a non-empty immutable tuple")
        if not all(isinstance(floor, RenderFloor) for floor in self.floors):
            raise ValueError("floors may contain only RenderFloor values")
        if not isinstance(self.objects, tuple) or not self.objects:
            raise ValueError("objects must be a non-empty immutable tuple")
        if not all(
            isinstance(item, (RoomRenderObject, WallRenderObject, OpeningRenderObject))
            for item in self.objects
        ):
            raise ValueError("objects contain an unsupported render value")

        floor_ids = tuple(floor.entity_id for floor in self.floors)
        if len(floor_ids) != len(set(floor_ids)):
            raise ValueError("floor entity IDs must be unique")
        object_ids = tuple(item.entity_id for item in self.objects)
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("render object entity IDs must be unique")
        if any(item.floor_id not in floor_ids for item in self.objects):
            raise ValueError("every render object must reference an included floor")

        walls = {
            item.entity_id: item for item in self.objects if isinstance(item, WallRenderObject)
        }
        for item in self.objects:
            if isinstance(item, OpeningRenderObject):
                host = walls.get(item.host_wall_id)
                if host is None or host.floor_id != item.floor_id:
                    raise ValueError("every opening must reference an included host wall")

    def to_dict(self) -> dict[str, object]:
        """Return a fresh standard-JSON tree without sharing mutable source containers."""

        return {
            "render_ir_version": self.render_ir_version,
            "source_model": self.source_model.to_dict(),
            "units": {"length": "m", "angle": "degree"},
            "coordinate_system": self.coordinate_system.to_dict(),
            "bounds": self.bounds.to_dict(),
            "floors": [floor.to_dict() for floor in self.floors],
            "objects": [item.to_dict() for item in self.objects],
        }
