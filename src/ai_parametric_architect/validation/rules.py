"""Deterministic L1 and L2 validation rules."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any, cast

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    Entity,
    GeometryPrecisionPolicy,
    InvalidDesignIntentError,
    ModelDocument,
    PlanningRecord,
    Severity,
    ValidationIssue,
)
from ai_parametric_architect.domain.numbers import finite_float
from ai_parametric_architect.ports import GeometryEngine
from ai_parametric_architect.validation.base import ValidationLevel
from ai_parametric_architect.validation.pointers import entity_pointer, json_pointer

_REGISTRY_NAMES = ("buildings", "floors", "rooms", "walls", "doors", "windows", "stairs")


def _registries(model: ModelDocument) -> Mapping[str, Mapping[str, Entity]]:
    return cast(Mapping[str, Mapping[str, Entity]], model["entities"])


def _error(
    code: str,
    message: str,
    path: str,
    entity_ids: tuple[str, ...] = (),
    details: Mapping[str, object] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=Severity.ERROR,
        message=message,
        path=path,
        entity_ids=entity_ids,
        details={} if details is None else details,
    )


class RegistryIntegrityRule:
    level = ValidationLevel.SPATIAL_RELATIONSHIPS
    name = "registry_integrity"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        del geometry, precision
        registries = _registries(model)
        issues: list[ValidationIssue] = []
        first_occurrence: dict[str, str] = {}

        for registry_name in _REGISTRY_NAMES:
            for key, entity in sorted(registries[registry_name].items()):
                entity_id = str(entity["id"])
                path = entity_pointer(registry_name, key, "id")
                if key != entity_id:
                    issues.append(
                        _error(
                            "KEY_ID_MISMATCH",
                            f"Registry key {key!r} does not equal entity id {entity_id!r}.",
                            path,
                            (key, entity_id),
                        )
                    )

                previous_path = first_occurrence.get(entity_id)
                if previous_path is None:
                    first_occurrence[entity_id] = path
                else:
                    issues.append(
                        _error(
                            "DUPLICATE_ENTITY_ID",
                            f"Entity id {entity_id!r} is used more than once.",
                            path,
                            (entity_id,),
                            {"first_path": previous_path},
                        )
                    )

        root_id = str(model["root_building_id"])
        if root_id not in registries["buildings"]:
            issues.append(
                _error(
                    "ROOT_BUILDING_NOT_FOUND",
                    f"Root building {root_id!r} does not exist.",
                    "/root_building_id",
                    (root_id,),
                )
            )
        elif not any(floor["building_id"] == root_id for floor in registries["floors"].values()):
            issues.append(
                _error(
                    "BUILDING_HAS_NO_FLOORS",
                    f"Root building {root_id!r} has no floor.",
                    "/entities/floors",
                    (root_id,),
                )
            )

        return tuple(issues)


class ReferenceIntegrityRule:
    level = ValidationLevel.SPATIAL_RELATIONSHIPS
    name = "reference_integrity"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        del geometry
        registries = _registries(model)
        buildings = registries["buildings"]
        floors = registries["floors"]
        walls = registries["walls"]
        issues: list[ValidationIssue] = []

        for floor_id, floor in sorted(floors.items()):
            building_id = str(floor["building_id"])
            if building_id not in buildings:
                issues.append(
                    _error(
                        "FLOOR_BUILDING_NOT_FOUND",
                        f"Floor {floor_id!r} references missing building {building_id!r}.",
                        entity_pointer("floors", floor_id, "building_id"),
                        (floor_id, building_id),
                    )
                )

        child_references = (
            ("rooms", "ROOM_FLOOR_NOT_FOUND"),
            ("walls", "WALL_FLOOR_NOT_FOUND"),
        )
        for registry_name, code in child_references:
            for entity_id, entity in sorted(registries[registry_name].items()):
                floor_id = str(entity["floor_id"])
                if floor_id not in floors:
                    issues.append(
                        _error(
                            code,
                            f"{entity['entity_type'].title()} {entity_id!r} "
                            f"references missing floor {floor_id!r}.",
                            entity_pointer(registry_name, entity_id, "floor_id"),
                            (entity_id, floor_id),
                        )
                    )

        for registry_name in ("doors", "windows"):
            for opening_id, opening in sorted(registries[registry_name].items()):
                wall_id = str(opening["host_wall_id"])
                if wall_id not in walls:
                    issues.append(
                        _error(
                            "OPENING_HOST_NOT_FOUND",
                            f"Opening {opening_id!r} references missing wall {wall_id!r}.",
                            entity_pointer(registry_name, opening_id, "host_wall_id"),
                            (opening_id, wall_id),
                        )
                    )

        for stair_id, stair in sorted(registries["stairs"].items()):
            from_id = str(stair["from_floor_id"])
            to_id = str(stair["to_floor_id"])
            missing_ids = tuple(floor_id for floor_id in (from_id, to_id) if floor_id not in floors)
            if missing_ids:
                issues.append(
                    _error(
                        "STAIR_FLOOR_NOT_FOUND",
                        f"Stair {stair_id!r} references missing floor(s): "
                        f"{', '.join(missing_ids)}.",
                        entity_pointer("stairs", stair_id),
                        (stair_id, *missing_ids),
                    )
                )
                continue

            from_floor = floors[from_id]
            to_floor = floors[to_id]
            if from_floor["building_id"] != to_floor["building_id"]:
                issues.append(
                    _error(
                        "STAIR_BUILDING_MISMATCH",
                        f"Stair {stair_id!r} connects floors in different buildings.",
                        entity_pointer("stairs", stair_id),
                        (stair_id, from_id, to_id),
                    )
                )
            from_elevation = finite_float(from_floor["elevation"])
            to_elevation = finite_float(to_floor["elevation"])
            elevation_delta = (
                None
                if from_elevation is None or to_elevation is None
                else to_elevation - from_elevation
            )
            if elevation_delta is not None and not math.isfinite(elevation_delta):
                issues.append(
                    _error(
                        "NON_FINITE_DERIVED_GEOMETRY",
                        f"Stair {stair_id!r} has a non-finite elevation difference.",
                        entity_pointer("stairs", stair_id),
                        (stair_id, from_id, to_id),
                        {"quantity": "elevation_difference"},
                    )
                )
            elif elevation_delta is not None and elevation_delta <= precision.linear_tolerance:
                issues.append(
                    _error(
                        "STAIR_ELEVATION_INVALID",
                        f"Stair {stair_id!r} must connect to a higher floor.",
                        entity_pointer("stairs", stair_id, "to_floor_id"),
                        (stair_id, from_id, to_id),
                    )
                )

        return tuple(issues)


class PlanningRecordRule:
    """Keep the owned planning trace aligned with authoritative room semantics."""

    level = ValidationLevel.BUILDING_RULES
    name = "planning_record_integrity"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        del geometry, precision
        extensions = cast(Mapping[str, Any], model.get("extensions", {}))
        if PLANNING_EXTENSION_KEY not in extensions:
            return ()

        extension_path = json_pointer(("extensions", PLANNING_EXTENSION_KEY))
        payload = extensions[PLANNING_EXTENSION_KEY]
        if not isinstance(payload, Mapping):
            return (
                _error(
                    "PLANNING_RECORD_INVALID",
                    "The architecture planning record must be a versioned JSON object.",
                    extension_path,
                    details={"reason": "NOT_AN_OBJECT"},
                ),
            )

        try:
            record = PlanningRecord.from_dict(payload)
        except InvalidDesignIntentError as error:
            return (
                _error(
                    "PLANNING_RECORD_INVALID",
                    f"The architecture planning record is invalid: {error}",
                    f"{extension_path}{error.path}",
                    details={"reason": error.code},
                ),
            )

        rooms = _registries(model)["rooms"]
        issues: list[ValidationIssue] = []
        for assignment in record.assignments:
            room = rooms.get(assignment.room_id)
            if room is None:
                issues.append(
                    _error(
                        "PLANNING_ASSIGNMENT_ROOM_NOT_FOUND",
                        f"Planning assignment references missing room {assignment.room_id!r}.",
                        extension_path,
                        (assignment.room_id,),
                    )
                )
                continue
            actual_usage = room.get("usage")
            actual_name = room.get("name")
            if actual_usage != assignment.usage or actual_name != assignment.name:
                issues.append(
                    _error(
                        "PLANNING_ASSIGNMENT_MISMATCH",
                        f"Room {assignment.room_id!r} does not match its planning assignment.",
                        entity_pointer("rooms", assignment.room_id),
                        (assignment.room_id,),
                        {
                            "expected_name": assignment.name,
                            "expected_usage": assignment.usage,
                            "actual_name": actual_name,
                            "actual_usage": actual_usage,
                        },
                    )
                )
        return tuple(issues)


def _non_finite_fields(entity: Entity, fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(field for field in fields if finite_float(entity[field]) is None)


class BasicGeometryRule:
    level = ValidationLevel.BASIC_GEOMETRY
    name = "basic_geometry"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        registries = _registries(model)
        issues: list[ValidationIssue] = []

        coordinate_system = cast(Mapping[str, object], model["coordinate_system"])
        origin = cast(Sequence[int | float], coordinate_system["origin"])
        if not all(finite_float(value) is not None for value in origin):
            issues.append(
                _error(
                    "NON_FINITE_COORDINATES",
                    "Coordinate-system origin contains a non-finite coordinate.",
                    "/coordinate_system/origin",
                )
            )

        for room_id, room in sorted(registries["rooms"].items()):
            room_analysis = geometry.analyze_room(room, precision)
            path = entity_pointer("rooms", room_id, "geometry")
            if not room_analysis.has_finite_coordinates:
                issues.append(
                    _error(
                        "NON_FINITE_COORDINATES",
                        f"Room {room_id!r} contains a non-finite coordinate.",
                        path,
                        (room_id,),
                    )
                )
                continue
            if not math.isfinite(room_analysis.area):
                issues.append(
                    _error(
                        "NON_FINITE_DERIVED_GEOMETRY",
                        f"Room {room_id!r} has a non-finite derived area.",
                        path,
                        (room_id,),
                        {"quantity": "area"},
                    )
                )
                continue
            if not room_analysis.rings_closed:
                issues.append(
                    _error(
                        "POLYGON_NOT_CLOSED",
                        f"Room {room_id!r} has an unclosed polygon ring.",
                        path,
                        (room_id,),
                    )
                )
            if not room_analysis.is_valid:
                reason = room_analysis.validity_reason or "Unknown polygon validity error"
                code = (
                    "ROOM_SELF_INTERSECTION"
                    if "self-intersection" in reason.lower()
                    else "ROOM_INVALID_POLYGON"
                )
                issues.append(
                    _error(
                        code,
                        f"Room {room_id!r} has an invalid polygon: {reason}.",
                        path,
                        (room_id,),
                        {"reason": reason},
                    )
                )
            if precision.is_zero_area(room_analysis.area):
                issues.append(
                    _error(
                        "ROOM_ZERO_AREA",
                        f"Room {room_id!r} has zero area within model precision.",
                        path,
                        (room_id,),
                        {"area": room_analysis.area},
                    )
                )

        for wall_id, wall in sorted(registries["walls"].items()):
            axis = cast(Entity, wall["axis"])
            wall_analysis = geometry.analyze_segment(axis)
            path = entity_pointer("walls", wall_id, "axis")
            if not wall_analysis.has_finite_coordinates:
                issues.append(
                    _error(
                        "NON_FINITE_COORDINATES",
                        f"Wall {wall_id!r} contains a non-finite coordinate.",
                        path,
                        (wall_id,),
                    )
                )
            elif not math.isfinite(wall_analysis.length):
                issues.append(
                    _error(
                        "NON_FINITE_DERIVED_GEOMETRY",
                        f"Wall {wall_id!r} has a non-finite derived length.",
                        path,
                        (wall_id,),
                        {"quantity": "length"},
                    )
                )
            elif precision.is_zero_length(wall_analysis.length):
                issues.append(
                    _error(
                        "WALL_ZERO_LENGTH",
                        f"Wall {wall_id!r} has zero length within model precision.",
                        path,
                        (wall_id,),
                        {"length": wall_analysis.length},
                    )
                )
            non_finite = _non_finite_fields(wall, ("thickness", "height", "base_offset"))
            if non_finite:
                issues.append(
                    _error(
                        "NON_FINITE_GEOMETRY_VALUE",
                        f"Wall {wall_id!r} has non-finite geometry values.",
                        entity_pointer("walls", wall_id),
                        (wall_id,),
                        {"fields": non_finite},
                    )
                )

        for stair_id, stair in sorted(registries["stairs"].items()):
            run = cast(Entity, stair["run"])
            stair_analysis = geometry.analyze_segment(run)
            path = entity_pointer("stairs", stair_id, "run")
            if not stair_analysis.has_finite_coordinates:
                issues.append(
                    _error(
                        "NON_FINITE_COORDINATES",
                        f"Stair {stair_id!r} contains a non-finite coordinate.",
                        path,
                        (stair_id,),
                    )
                )
            elif not math.isfinite(stair_analysis.length):
                issues.append(
                    _error(
                        "NON_FINITE_DERIVED_GEOMETRY",
                        f"Stair {stair_id!r} has a non-finite derived run length.",
                        path,
                        (stair_id,),
                        {"quantity": "length"},
                    )
                )
            elif precision.is_zero_length(stair_analysis.length):
                issues.append(
                    _error(
                        "STAIR_ZERO_RUN",
                        f"Stair {stair_id!r} has a zero-length run.",
                        path,
                        (stair_id,),
                    )
                )

        numeric_groups = (
            ("floors", ("elevation", "height")),
            ("doors", ("center_offset", "width", "height", "bottom_offset")),
            ("windows", ("center_offset", "width", "height", "bottom_offset")),
            ("stairs", ("width",)),
        )
        for registry_name, fields in numeric_groups:
            for entity_id, entity in sorted(registries[registry_name].items()):
                non_finite = _non_finite_fields(entity, fields)
                if non_finite:
                    issues.append(
                        _error(
                            "NON_FINITE_GEOMETRY_VALUE",
                            f"Entity {entity_id!r} has non-finite geometry values.",
                            entity_pointer(registry_name, entity_id),
                            (entity_id,),
                            {"fields": list(non_finite)},
                        )
                    )

        dimension_groups = (
            ("floors", ("height",)),
            ("walls", ("thickness", "height")),
            ("doors", ("width", "height")),
            ("windows", ("width", "height")),
            ("stairs", ("width",)),
        )
        for registry_name, fields in dimension_groups:
            for entity_id, entity in sorted(registries[registry_name].items()):
                below_tolerance = tuple(
                    field
                    for field in fields
                    if (value := finite_float(entity[field])) is not None
                    and precision.is_zero_length(value)
                )
                if below_tolerance:
                    issues.append(
                        _error(
                            "GEOMETRY_DIMENSION_BELOW_TOLERANCE",
                            f"Entity {entity_id!r} has dimensions at or below model tolerance.",
                            entity_pointer(registry_name, entity_id),
                            (entity_id,),
                            {"fields": list(below_tolerance)},
                        )
                    )

        return tuple(issues)


class RoomOverlapRule:
    level = ValidationLevel.SPATIAL_RELATIONSHIPS
    name = "room_overlap"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        rooms = _registries(model)["rooms"]
        by_floor: defaultdict[str, list[tuple[str, Entity]]] = defaultdict(list)
        for room_id, room in sorted(rooms.items()):
            analysis = geometry.analyze_room(room, precision)
            if (
                analysis.has_finite_coordinates
                and analysis.rings_closed
                and analysis.is_valid
                and not precision.is_zero_area(analysis.area)
            ):
                by_floor[str(room["floor_id"])].append((room_id, room))

        issues: list[ValidationIssue] = []
        for floor_id in sorted(by_floor):
            for (first_id, first), (second_id, second) in combinations(by_floor[floor_id], 2):
                overlap_area = geometry.room_overlap_area(first, second)
                if not math.isfinite(overlap_area):
                    issues.append(
                        _error(
                            "NON_FINITE_DERIVED_GEOMETRY",
                            f"Rooms {first_id!r} and {second_id!r} have a non-finite overlap.",
                            "/entities/rooms",
                            (first_id, second_id),
                            {"quantity": "overlap_area"},
                        )
                    )
                    continue
                if overlap_area > precision.area_tolerance:
                    issues.append(
                        _error(
                            "ROOM_OVERLAP",
                            f"Rooms {first_id!r} and {second_id!r} overlap.",
                            "/entities/rooms",
                            (first_id, second_id),
                            {"floor_id": floor_id, "overlap_area": overlap_area},
                        )
                    )
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class _OpeningPlacement:
    registry_name: str
    entity_id: str
    wall_id: str
    horizontal_start: float
    horizontal_end: float
    vertical_start: float
    vertical_end: float


class OpeningRule:
    level = ValidationLevel.SPATIAL_RELATIONSHIPS
    name = "opening_placement"

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]:
        registries = _registries(model)
        walls = registries["walls"]
        issues: list[ValidationIssue] = []
        by_wall: defaultdict[str, list[_OpeningPlacement]] = defaultdict(list)

        for registry_name in ("doors", "windows"):
            for opening_id, opening in sorted(registries[registry_name].items()):
                wall_id = str(opening["host_wall_id"])
                wall = walls.get(wall_id)
                if wall is None:
                    continue

                converted_values = tuple(
                    finite_float(opening[field])
                    for field in ("center_offset", "width", "bottom_offset", "height")
                )
                wall_height = finite_float(wall["height"])
                if wall_height is None or any(value is None for value in converted_values):
                    continue

                center, width, bottom, height = cast(
                    tuple[float, float, float, float], converted_values
                )
                axis = cast(Entity, wall["axis"])
                wall_analysis = geometry.analyze_segment(axis)
                if not wall_analysis.has_finite_coordinates or precision.is_zero_length(
                    wall_analysis.length
                ):
                    continue

                horizontal_start = center - width / 2
                horizontal_end = center + width / 2
                vertical_start = bottom
                vertical_end = bottom + height
                if not all(
                    math.isfinite(value)
                    for value in (
                        horizontal_start,
                        horizontal_end,
                        vertical_start,
                        vertical_end,
                    )
                ):
                    issues.append(
                        _error(
                            "NON_FINITE_DERIVED_GEOMETRY",
                            f"Opening {opening_id!r} has a non-finite derived placement.",
                            entity_pointer(registry_name, opening_id),
                            (opening_id, wall_id),
                            {"quantity": "opening_placement"},
                        )
                    )
                    continue

                placement = _OpeningPlacement(
                    registry_name=registry_name,
                    entity_id=opening_id,
                    wall_id=wall_id,
                    horizontal_start=horizontal_start,
                    horizontal_end=horizontal_end,
                    vertical_start=vertical_start,
                    vertical_end=vertical_end,
                )
                by_wall[wall_id].append(placement)

                tolerance = precision.linear_tolerance
                outside_horizontal = (
                    placement.horizontal_start < -tolerance
                    or placement.horizontal_end > wall_analysis.length + tolerance
                )
                outside_vertical = (
                    placement.vertical_start < -tolerance
                    or placement.vertical_end > wall_height + tolerance
                )
                if outside_horizontal or outside_vertical:
                    issues.append(
                        _error(
                            "OPENING_OUT_OF_WALL_BOUNDS",
                            f"Opening {opening_id!r} lies outside host wall {wall_id!r}.",
                            entity_pointer(registry_name, opening_id),
                            (opening_id, wall_id),
                            {
                                "horizontal_interval": [
                                    placement.horizontal_start,
                                    placement.horizontal_end,
                                ],
                                "wall_length": wall_analysis.length,
                                "vertical_interval": [
                                    placement.vertical_start,
                                    placement.vertical_end,
                                ],
                                "wall_height": wall_height,
                            },
                        )
                    )

        for wall_id in sorted(by_wall):
            placements = sorted(by_wall[wall_id], key=lambda item: item.entity_id)
            for first, second in combinations(placements, 2):
                horizontal_overlap = min(first.horizontal_end, second.horizontal_end) - max(
                    first.horizontal_start, second.horizontal_start
                )
                vertical_overlap = min(first.vertical_end, second.vertical_end) - max(
                    first.vertical_start, second.vertical_start
                )
                if (
                    horizontal_overlap > precision.linear_tolerance
                    and vertical_overlap > precision.linear_tolerance
                ):
                    issues.append(
                        _error(
                            "OPENING_OVERLAP",
                            f"Openings {first.entity_id!r} and {second.entity_id!r} overlap.",
                            entity_pointer(first.registry_name, first.entity_id),
                            (first.entity_id, second.entity_id),
                            {
                                "host_wall_id": wall_id,
                                "horizontal_overlap": horizontal_overlap,
                                "vertical_overlap": vertical_overlap,
                            },
                        )
                    )

        return tuple(issues)


DEFAULT_RULES = (
    BasicGeometryRule(),
    RegistryIntegrityRule(),
    ReferenceIntegrityRule(),
    RoomOverlapRule(),
    OpeningRule(),
    PlanningRecordRule(),
)
