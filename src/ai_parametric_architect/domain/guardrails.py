"""Shared JSON-tree and bounded-complexity guards for model trust boundaries."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from ai_parametric_architect.domain.editing_errors import NonJsonValueError
from ai_parametric_architect.domain.issues import Severity, ValidationIssue
from ai_parametric_architect.domain.json_values import ensure_json_value
from ai_parametric_architect.domain.model import ModelDocument

DEFAULT_MAX_TOTAL_ENTITIES: Final = 2_048
DEFAULT_MAX_POLYGON_VERTICES: Final = 16_384
DEFAULT_MAX_COORDINATE_MAGNITUDE: Final = 1_000_000.0
DEFAULT_MAX_ROOM_AREA: Final = 10_000_000_000.0
DEFAULT_MAX_WALL_LENGTH: Final = 100_000.0
DEFAULT_MAX_PATCH_OPERATIONS: Final = 256


@dataclass(frozen=True, slots=True)
class StrictJsonTreeGuard:
    """Apply the one authoritative definition of a standard JSON tree."""

    def require(self, value: object) -> None:
        ensure_json_value(value)

    def issue(self, value: object) -> ValidationIssue | None:
        try:
            self.require(value)
        except NonJsonValueError as error:
            return ValidationIssue(
                code="JSON_TREE_INVALID",
                severity=Severity.ERROR,
                message=f"Model must be a strict standard JSON tree: {error}",
                path=error.path or "/",
                details=dict(error.details),
            )
        return None


class ModelComplexityError(ValueError):
    """A stable bounded-resource violation at a model or patch boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        path: str,
        details: Mapping[str, object],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = dict(details)

    def to_issue(self) -> ValidationIssue:
        return ValidationIssue(
            code=self.code,
            severity=Severity.ERROR,
            message=str(self),
            path=self.path,
            details=self.details,
        )


@dataclass(frozen=True, slots=True)
class ModelComplexityPolicy:
    """Bound work and floating-point projections for one local-Cartesian model."""

    max_total_entities: int = DEFAULT_MAX_TOTAL_ENTITIES
    max_polygon_vertices: int = DEFAULT_MAX_POLYGON_VERTICES
    max_coordinate_magnitude: float = DEFAULT_MAX_COORDINATE_MAGNITUDE
    max_room_area: float = DEFAULT_MAX_ROOM_AREA
    max_wall_length: float = DEFAULT_MAX_WALL_LENGTH
    max_patch_operations: int = DEFAULT_MAX_PATCH_OPERATIONS

    def __post_init__(self) -> None:
        _require_positive_integer(self.max_total_entities, "max_total_entities")
        _require_positive_integer(self.max_polygon_vertices, "max_polygon_vertices")
        _require_positive_number(self.max_coordinate_magnitude, "max_coordinate_magnitude")
        _require_positive_number(self.max_room_area, "max_room_area")
        _require_positive_number(self.max_wall_length, "max_wall_length")
        _require_positive_integer(self.max_patch_operations, "max_patch_operations")

    def require_patch_operations(self, count: int) -> None:
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("Patch operation count must be a non-negative integer.")
        if count > self.max_patch_operations:
            raise ModelComplexityError(
                "Patch proposal exceeds the configured operation budget.",
                code="PATCH_OPERATION_LIMIT_EXCEEDED",
                path="/operations",
                details={"actual": count, "maximum": self.max_patch_operations},
            )

    def require_model(self, model: ModelDocument) -> None:
        registries = _registries(model)
        total_entities = sum(len(registry) for registry in registries.values())
        if total_entities > self.max_total_entities:
            raise ModelComplexityError(
                "Model exceeds the configured total entity budget.",
                code="MODEL_ENTITY_LIMIT_EXCEEDED",
                path="/entities",
                details={"actual": total_entities, "maximum": self.max_total_entities},
            )

        rooms = registries.get("rooms", {})
        polygon_vertices = sum(len(ring) for room in rooms.values() for ring in _room_rings(room))
        if polygon_vertices > self.max_polygon_vertices:
            raise ModelComplexityError(
                "Model exceeds the configured polygon vertex budget.",
                code="MODEL_POLYGON_VERTEX_LIMIT_EXCEEDED",
                path="/entities/rooms",
                details={
                    "actual": polygon_vertices,
                    "maximum": self.max_polygon_vertices,
                },
            )

        self._require_coordinate_ranges(model, registries)
        self._require_room_areas(rooms)
        self._require_wall_lengths(registries.get("walls", {}))

    def _require_coordinate_ranges(
        self,
        model: ModelDocument,
        registries: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        coordinate_system = _mapping(model.get("coordinate_system"))
        if coordinate_system is not None:
            self._require_point(coordinate_system.get("origin"), "/coordinate_system/origin")

        for room_id, room in sorted(registries.get("rooms", {}).items()):
            for ring_name, ring_index, ring in _named_room_rings(room):
                suffix = ring_name if ring_index is None else f"{ring_name}/{ring_index}"
                for point_index, point in enumerate(ring):
                    self._require_point(
                        point,
                        f"/entities/rooms/{room_id}/geometry/{suffix}/{point_index}",
                    )

        for wall_id, wall in sorted(registries.get("walls", {}).items()):
            axis = _mapping(wall.get("axis"))
            if axis is not None:
                self._require_point(axis.get("start"), f"/entities/walls/{wall_id}/axis/start")
                self._require_point(axis.get("end"), f"/entities/walls/{wall_id}/axis/end")
            for field_name in ("thickness", "height", "base_offset"):
                self._require_scalar(
                    wall.get(field_name),
                    f"/entities/walls/{wall_id}/{field_name}",
                )

        scalar_groups = {
            "floors": ("elevation", "height"),
            "doors": ("center_offset", "width", "height", "bottom_offset"),
            "windows": ("center_offset", "width", "height", "bottom_offset"),
            "stairs": ("width",),
        }
        for registry_name, field_names in scalar_groups.items():
            for entity_id, entity in sorted(registries.get(registry_name, {}).items()):
                for field_name in field_names:
                    self._require_scalar(
                        entity.get(field_name),
                        f"/entities/{registry_name}/{entity_id}/{field_name}",
                    )

        for stair_id, stair in sorted(registries.get("stairs", {}).items()):
            run = _mapping(stair.get("run"))
            if run is not None:
                self._require_point(run.get("start"), f"/entities/stairs/{stair_id}/run/start")
                self._require_point(run.get("end"), f"/entities/stairs/{stair_id}/run/end")

    def _require_point(self, value: object, path: str) -> None:
        sequence = _sequence(value)
        if sequence is None:
            return
        for index, coordinate in enumerate(sequence):
            self._require_scalar(coordinate, f"{path}/{index}")

    def _require_scalar(self, value: object, path: str) -> None:
        numeric = _finite_number(value)
        if numeric is None:
            return
        if abs(numeric) > self.max_coordinate_magnitude:
            raise ModelComplexityError(
                "Geometry value exceeds the configured coordinate range.",
                code="MODEL_COORDINATE_RANGE_EXCEEDED",
                path=path,
                details={"maximum_magnitude": self.max_coordinate_magnitude},
            )

    def _require_room_areas(self, rooms: Mapping[str, Mapping[str, Any]]) -> None:
        for room_id, room in sorted(rooms.items()):
            rings = _room_rings(room)
            if not rings:
                continue
            area = abs(_signed_ring_area(rings[0]))
            if not math.isfinite(area):
                raise ModelComplexityError(
                    "Room has a non-finite derived area.",
                    code="MODEL_DERIVED_GEOMETRY_NON_FINITE",
                    path=f"/entities/rooms/{room_id}/geometry",
                    details={"quantity": "area"},
                )
            if area > self.max_room_area:
                raise ModelComplexityError(
                    "Room exceeds the configured area limit.",
                    code="MODEL_AREA_LIMIT_EXCEEDED",
                    path=f"/entities/rooms/{room_id}/geometry",
                    details={"actual": area, "maximum": self.max_room_area},
                )

    def _require_wall_lengths(self, walls: Mapping[str, Mapping[str, Any]]) -> None:
        for wall_id, wall in sorted(walls.items()):
            axis = _mapping(wall.get("axis"))
            if axis is None:
                continue
            start = _numeric_point(axis.get("start"))
            end = _numeric_point(axis.get("end"))
            if start is None or end is None:
                continue
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            if not math.isfinite(length):
                raise ModelComplexityError(
                    "Wall has a non-finite derived length.",
                    code="MODEL_DERIVED_GEOMETRY_NON_FINITE",
                    path=f"/entities/walls/{wall_id}/axis",
                    details={"quantity": "length"},
                )
            if length > self.max_wall_length:
                raise ModelComplexityError(
                    "Wall exceeds the configured length limit.",
                    code="MODEL_WALL_LENGTH_LIMIT_EXCEEDED",
                    path=f"/entities/walls/{wall_id}/axis",
                    details={"actual": length, "maximum": self.max_wall_length},
                )


def _require_positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer.")


def _require_positive_number(value: object, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive finite number.")
    try:
        numeric = float(value)
    except OverflowError as error:
        raise ValueError(f"{field_name} must be a positive finite number.") from error
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{field_name} must be a positive finite number.")


def _mapping(value: object) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return cast(Mapping[str, Any], value)


def _sequence(value: object) -> Sequence[object] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    return cast(Sequence[object], value)


def _registries(model: ModelDocument) -> dict[str, Mapping[str, Mapping[str, Any]]]:
    entities = _mapping(model.get("entities"))
    if entities is None:
        return {}
    registries: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    for registry_name, registry_value in entities.items():
        registry = _mapping(registry_value)
        if registry is None:
            continue
        values: dict[str, Mapping[str, Any]] = {}
        for entity_id, entity_value in registry.items():
            entity = _mapping(entity_value)
            if entity is not None:
                values[entity_id] = entity
        registries[registry_name] = values
    return registries


def _named_room_rings(
    room: Mapping[str, Any],
) -> tuple[tuple[str, int | None, Sequence[object]], ...]:
    geometry = _mapping(room.get("geometry"))
    if geometry is None:
        return ()
    result: list[tuple[str, int | None, Sequence[object]]] = []
    exterior = _sequence(geometry.get("exterior"))
    if exterior is not None:
        result.append(("exterior", None, exterior))
    holes = _sequence(geometry.get("holes"))
    if holes is not None:
        for index, hole_value in enumerate(holes):
            hole = _sequence(hole_value)
            if hole is not None:
                result.append(("holes", index, hole))
    return tuple(result)


def _room_rings(room: Mapping[str, Any]) -> tuple[Sequence[object], ...]:
    return tuple(ring for _name, _index, ring in _named_room_rings(room))


def _finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except OverflowError:
        return math.inf
    return numeric


def _numeric_point(value: object) -> tuple[float, float] | None:
    sequence = _sequence(value)
    if sequence is None or len(sequence) < 2:
        return None
    first = _finite_number(sequence[0])
    second = _finite_number(sequence[1])
    if first is None or second is None:
        return None
    return (first, second)


def _signed_ring_area(ring: Sequence[object]) -> float:
    points = tuple(point for value in ring if (point := _numeric_point(value)) is not None)
    if len(points) < 3:
        return 0.0
    try:
        return (
            math.fsum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(points, points[1:] + points[:1], strict=True)
            )
            / 2
        )
    except (OverflowError, ValueError):
        return math.inf
