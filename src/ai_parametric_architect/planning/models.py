"""Immutable floor-plan proposal values.

Version 1 is the original semantic-only proposal contract. Version 2 adds a
proposal-local rectangular boundary and complete room placements. Neither
version is persisted world state.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from ai_parametric_architect.domain.design_intent import (
    DesignIntent,
    SpatialRelation,
)
from ai_parametric_architect.domain.planning_errors import (
    InvalidDesignIntentError,
    PlanningContextError,
)

FLOOR_PLAN_SCHEMA_VERSION: Final = "1.0.0"
SOLVED_FLOOR_PLAN_SCHEMA_VERSION: Final = "2.0.0"
SUPPORTED_FLOOR_PLAN_SCHEMA_VERSIONS: Final = frozenset(
    {FLOOR_PLAN_SCHEMA_VERSION, SOLVED_FLOOR_PLAN_SCHEMA_VERSION}
)
ROOM_ORIENTATIONS: Final = frozenset({"east", "interior", "north", "south", "west"})
_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True, init=False)
class FloorPlanBoundary:
    """Proposal-local rectangular planning boundary measured in metres."""

    width: float
    height: float

    def __init__(self, *, width: int | float, height: int | float) -> None:
        width_value = _positive_finite_float(width, "/width", "Boundary width")
        height_value = _positive_finite_float(height, "/height", "Boundary height")
        if not math.isfinite(width_value * height_value):
            raise PlanningContextError("Floor-plan boundary area must be finite.", path="/width")
        object.__setattr__(self, "width", width_value)
        object.__setattr__(self, "height", height_value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FloorPlanBoundary:
        if set(value) != {"width", "height"}:
            raise PlanningContextError("Floor-plan boundary has missing or unexpected fields.")
        width = value.get("width")
        height = value.get("height")
        if not _is_number(width):
            raise PlanningContextError("width must be a number.", path="/width")
        if not _is_number(height):
            raise PlanningContextError("height must be a number.", path="/height")
        return cls(
            width=cast(int | float, width),
            height=cast(int | float, height),
        )

    def to_dict(self) -> dict[str, int | float]:
        return {"width": _compact_number(self.width), "height": _compact_number(self.height)}


@dataclass(frozen=True, slots=True, init=False)
class FloorPlanRoom:
    plan_id: str
    room_type: str
    target_area: float
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    orientation: str | None

    def __init__(
        self,
        *,
        plan_id: str,
        room_type: str,
        target_area: int | float,
        x: int | float | None = None,
        y: int | float | None = None,
        width: int | float | None = None,
        height: int | float | None = None,
        orientation: str | None = None,
    ) -> None:
        _require_token(plan_id, "/plan_id")
        _require_token(room_type, "/room_type")
        area = _positive_finite_float(target_area, "/target_area", "Floor-plan target area")
        placement = (x, y, width, height, orientation)
        is_unplaced = all(value is None for value in placement)
        if not is_unplaced and any(value is None for value in placement):
            raise PlanningContextError(
                "Room placement fields must be supplied together.", path="/x"
            )

        x_value: float | None = None
        y_value: float | None = None
        width_value: float | None = None
        height_value: float | None = None
        if not is_unplaced:
            x_value = _non_negative_finite_float(x, "/x", "Room x coordinate")
            y_value = _non_negative_finite_float(y, "/y", "Room y coordinate")
            width_value = _positive_finite_float(width, "/width", "Room width")
            height_value = _positive_finite_float(height, "/height", "Room height")
            if not math.isfinite(width_value * height_value):
                raise PlanningContextError("Room placement area must be finite.", path="/width")
            if orientation not in ROOM_ORIENTATIONS:
                raise PlanningContextError(
                    "Room orientation must be north, south, east, west, or interior.",
                    path="/orientation",
                )

        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "room_type", room_type)
        object.__setattr__(self, "target_area", area)
        object.__setattr__(self, "x", x_value)
        object.__setattr__(self, "y", y_value)
        object.__setattr__(self, "width", width_value)
        object.__setattr__(self, "height", height_value)
        object.__setattr__(self, "orientation", orientation)

    @property
    def is_placed(self) -> bool:
        return self.x is not None

    @property
    def actual_area(self) -> float | None:
        if self.width is None or self.height is None:
            return None
        return self.width * self.height

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        schema_version: str = FLOOR_PLAN_SCHEMA_VERSION,
    ) -> FloorPlanRoom:
        v1_fields = {"plan_id", "room_type", "target_area"}
        v2_fields = {*v1_fields, "x", "y", "width", "height", "orientation"}
        expected = v2_fields if schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION else v1_fields
        if schema_version not in SUPPORTED_FLOOR_PLAN_SCHEMA_VERSIONS or set(value) != expected:
            raise PlanningContextError("Floor-plan room has missing or unexpected fields.")
        plan_id = value.get("plan_id")
        room_type = value.get("room_type")
        target_area = value.get("target_area")
        if not isinstance(plan_id, str):
            raise PlanningContextError("plan_id must be a string.", path="/plan_id")
        if not isinstance(room_type, str):
            raise PlanningContextError("room_type must be a string.", path="/room_type")
        if not _is_number(target_area):
            raise PlanningContextError("target_area must be a number.", path="/target_area")
        if schema_version == FLOOR_PLAN_SCHEMA_VERSION:
            return cls(
                plan_id=plan_id,
                room_type=room_type,
                target_area=cast(int | float, target_area),
            )

        numeric_fields: dict[str, int | float] = {}
        for field_name in ("x", "y", "width", "height"):
            field_value = value.get(field_name)
            if not _is_number(field_value):
                raise PlanningContextError(f"{field_name} must be a number.", path=f"/{field_name}")
            numeric_fields[field_name] = cast(int | float, field_value)
        orientation = value.get("orientation")
        if not isinstance(orientation, str):
            raise PlanningContextError("orientation must be a string.", path="/orientation")
        return cls(
            plan_id=plan_id,
            room_type=room_type,
            target_area=cast(int | float, target_area),
            x=numeric_fields["x"],
            y=numeric_fields["y"],
            width=numeric_fields["width"],
            height=numeric_fields["height"],
            orientation=orientation,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "plan_id": self.plan_id,
            "room_type": self.room_type,
            "target_area": _compact_number(self.target_area),
        }
        if self.is_placed:
            assert self.x is not None
            assert self.y is not None
            assert self.width is not None
            assert self.height is not None
            assert self.orientation is not None
            result.update(
                {
                    "x": _compact_number(self.x),
                    "y": _compact_number(self.y),
                    "width": _compact_number(self.width),
                    "height": _compact_number(self.height),
                    "orientation": self.orientation,
                }
            )
        return result


@dataclass(frozen=True, slots=True, init=False)
class FloorPlanConstraint:
    source_plan_id: str
    relation: SpatialRelation
    target_plan_id: str
    required: bool

    def __init__(
        self,
        *,
        source_plan_id: str,
        relation: SpatialRelation | str,
        target_plan_id: str,
        required: bool,
    ) -> None:
        _require_token(source_plan_id, "/source_plan_id")
        _require_token(target_plan_id, "/target_plan_id")
        try:
            relation_value = SpatialRelation(relation)
        except (TypeError, ValueError) as error:
            raise PlanningContextError(
                "Floor-plan spatial relation is unsupported.", path="/relation"
            ) from error
        if source_plan_id == target_plan_id:
            raise PlanningContextError(
                "Floor-plan constraints must reference different rooms.",
                path="/target_plan_id",
            )
        if not isinstance(required, bool):
            raise PlanningContextError("required must be a boolean.", path="/required")
        object.__setattr__(self, "source_plan_id", source_plan_id)
        object.__setattr__(self, "relation", relation_value)
        object.__setattr__(self, "target_plan_id", target_plan_id)
        object.__setattr__(self, "required", required)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FloorPlanConstraint:
        expected = {"source_plan_id", "relation", "target_plan_id", "required"}
        if set(value) != expected:
            raise PlanningContextError("Floor-plan constraint has missing or unexpected fields.")
        source = value.get("source_plan_id")
        relation = value.get("relation")
        target = value.get("target_plan_id")
        required = value.get("required")
        if not isinstance(source, str):
            raise PlanningContextError("source_plan_id must be a string.", path="/source_plan_id")
        if not isinstance(relation, str):
            raise PlanningContextError("relation must be a string.", path="/relation")
        if not isinstance(target, str):
            raise PlanningContextError("target_plan_id must be a string.", path="/target_plan_id")
        if not isinstance(required, bool):
            raise PlanningContextError("required must be a boolean.", path="/required")
        return cls(
            source_plan_id=source,
            relation=relation,
            target_plan_id=target,
            required=required,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_plan_id": self.source_plan_id,
            "relation": self.relation.value,
            "target_plan_id": self.target_plan_id,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True, init=False)
class FloorPlanProposal:
    intent: DesignIntent
    rooms: tuple[FloorPlanRoom, ...]
    spatial_constraints: tuple[FloorPlanConstraint, ...]
    orientation: str | None
    strategy: str
    schema_version: str
    boundary: FloorPlanBoundary | None

    def __init__(
        self,
        *,
        intent: DesignIntent,
        rooms: tuple[FloorPlanRoom, ...],
        spatial_constraints: tuple[FloorPlanConstraint, ...],
        orientation: str | None,
        strategy: str,
        schema_version: str = FLOOR_PLAN_SCHEMA_VERSION,
        boundary: FloorPlanBoundary | None = None,
    ) -> None:
        if schema_version not in SUPPORTED_FLOOR_PLAN_SCHEMA_VERSIONS:
            raise PlanningContextError(
                "Unsupported floor-plan proposal schema version.", path="/schema_version"
            )
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Floor-plan proposal intent must be a DesignIntent.", path="/intent"
            )
        _require_token(strategy, "/strategy")
        if (
            not isinstance(rooms, tuple)
            or not rooms
            or not all(isinstance(room, FloorPlanRoom) for room in rooms)
        ):
            raise PlanningContextError(
                "Floor-plan rooms must be a non-empty immutable tuple.", path="/rooms"
            )
        plan_ids = tuple(room.plan_id for room in rooms)
        if len(plan_ids) != len(set(plan_ids)):
            raise PlanningContextError("Floor-plan room IDs must be unique.", path="/rooms")
        if tuple(room.room_type for room in rooms) != intent.rooms:
            raise PlanningContextError(
                "Floor-plan rooms must realize the intent room sequence.", path="/rooms"
            )
        try:
            allocated_area = math.fsum(room.target_area for room in rooms)
        except OverflowError as error:
            raise PlanningContextError(
                "Floor-plan target areas overflow their intent area.", path="/rooms"
            ) from error
        if allocated_area != intent.area:
            raise PlanningContextError(
                "Floor-plan target areas must sum exactly to the intent area.",
                path="/rooms",
                details={"allocated_area": allocated_area, "intent_area": intent.area},
            )
        if orientation != intent.orientation:
            raise PlanningContextError(
                "Floor-plan orientation must equal the design intent orientation.",
                path="/orientation",
            )
        if not isinstance(spatial_constraints, tuple) or not all(
            isinstance(constraint, FloorPlanConstraint) for constraint in spatial_constraints
        ):
            raise PlanningContextError(
                "Floor-plan constraints must be an immutable tuple.",
                path="/spatial_constraints",
            )
        if len(spatial_constraints) != len(set(spatial_constraints)):
            raise PlanningContextError(
                "Floor-plan constraints must be unique.", path="/spatial_constraints"
            )
        if len(spatial_constraints) != len(intent.spatial_constraints):
            raise PlanningContextError(
                "Every intent spatial constraint must have one plan allocation.",
                path="/spatial_constraints",
            )
        _validate_constraint_bindings(rooms, spatial_constraints, intent)
        _validate_schema_geometry(schema_version, rooms, boundary, intent.area)

        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "rooms", rooms)
        object.__setattr__(self, "spatial_constraints", spatial_constraints)
        object.__setattr__(self, "orientation", orientation)
        object.__setattr__(self, "strategy", strategy)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "boundary", boundary)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FloorPlanProposal:
        schema_version = value.get("schema_version")
        if not isinstance(schema_version, str):
            raise PlanningContextError("schema_version must be a string.", path="/schema_version")
        if schema_version not in SUPPORTED_FLOOR_PLAN_SCHEMA_VERSIONS:
            raise PlanningContextError(
                "Unsupported floor-plan proposal schema version.", path="/schema_version"
            )
        expected = {
            "schema_version",
            "strategy",
            "intent",
            "orientation",
            "rooms",
            "spatial_constraints",
        }
        if schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION:
            expected.add("boundary")
        if set(value) != expected:
            raise PlanningContextError("Floor-plan proposal has missing or unexpected fields.")
        intent_value = value.get("intent")
        if not isinstance(intent_value, Mapping):
            raise PlanningContextError("intent must be an object.", path="/intent")
        try:
            intent = DesignIntent.from_dict(intent_value)
        except InvalidDesignIntentError as error:
            raise _nested_design_error(error, "/intent") from error
        rooms = _parse_rooms(value.get("rooms"), schema_version)
        constraints = _parse_constraints(value.get("spatial_constraints"))
        orientation = value.get("orientation")
        strategy = value.get("strategy")
        if orientation is not None and not isinstance(orientation, str):
            raise PlanningContextError("orientation must be a string or null.", path="/orientation")
        if not isinstance(strategy, str):
            raise PlanningContextError("strategy must be a string.", path="/strategy")
        boundary: FloorPlanBoundary | None = None
        if schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION:
            boundary_value = value.get("boundary")
            if not isinstance(boundary_value, Mapping):
                raise PlanningContextError("boundary must be an object.", path="/boundary")
            try:
                boundary = FloorPlanBoundary.from_dict(boundary_value)
            except PlanningContextError as error:
                raise _nested_context_error(error, "/boundary") from error
        return cls(
            schema_version=schema_version,
            strategy=strategy,
            intent=intent,
            orientation=orientation,
            rooms=rooms,
            spatial_constraints=constraints,
            boundary=boundary,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "strategy": self.strategy,
            "intent": self.intent.to_dict(),
            "orientation": self.orientation,
            "rooms": [room.to_dict() for room in self.rooms],
            "spatial_constraints": [
                constraint.to_dict() for constraint in self.spatial_constraints
            ],
        }
        if self.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION:
            assert self.boundary is not None
            result["boundary"] = self.boundary.to_dict()
        return result


def _validate_constraint_bindings(
    rooms: tuple[FloorPlanRoom, ...],
    spatial_constraints: tuple[FloorPlanConstraint, ...],
    intent: DesignIntent,
) -> None:
    rooms_by_id = {room.plan_id: room for room in rooms}
    for index, (planned, requested) in enumerate(
        zip(spatial_constraints, intent.spatial_constraints, strict=True)
    ):
        source = rooms_by_id.get(planned.source_plan_id)
        target = rooms_by_id.get(planned.target_plan_id)
        if source is None or target is None:
            missing = [
                plan_id
                for plan_id, room in (
                    (planned.source_plan_id, source),
                    (planned.target_plan_id, target),
                )
                if room is None
            ]
            raise PlanningContextError(
                "Floor-plan constraint references an unknown plan room.",
                path=f"/spatial_constraints/{index}",
                details={"missing_plan_ids": missing},
            )
        if (
            source.room_type != requested.source_room_type
            or target.room_type != requested.target_room_type
            or planned.relation != requested.relation
            or planned.required != requested.required
        ):
            raise PlanningContextError(
                "Floor-plan constraint does not realize its intent constraint.",
                path=f"/spatial_constraints/{index}",
            )


def _validate_schema_geometry(
    schema_version: str,
    rooms: tuple[FloorPlanRoom, ...],
    boundary: FloorPlanBoundary | None,
    intent_area: float,
) -> None:
    if schema_version == FLOOR_PLAN_SCHEMA_VERSION:
        if boundary is not None or any(room.is_placed for room in rooms):
            raise PlanningContextError(
                "Floor-plan proposal v1 cannot contain spatial placement.", path="/rooms"
            )
        return
    if not isinstance(boundary, FloorPlanBoundary):
        raise PlanningContextError("Floor-plan proposal v2 requires a boundary.", path="/boundary")
    if not all(room.is_placed for room in rooms):
        raise PlanningContextError(
            "Floor-plan proposal v2 requires complete room placements.", path="/rooms"
        )

    actual_areas: list[float] = []
    for index, room in enumerate(rooms):
        assert room.x is not None
        assert room.y is not None
        assert room.width is not None
        assert room.height is not None
        assert room.orientation is not None
        if room.x + room.width > boundary.width or room.y + room.height > boundary.height:
            raise PlanningContextError(
                "Placed room must remain inside the proposal boundary.",
                path=f"/rooms/{index}",
            )
        _validate_room_orientation(room, boundary, index)
        assert room.actual_area is not None
        actual_areas.append(room.actual_area)
    try:
        actual_area_total = math.fsum(actual_areas)
    except OverflowError as error:
        raise PlanningContextError(
            "Placed room area must be finite and cannot exceed the intent area.",
            path="/rooms",
        ) from error
    if not math.isfinite(actual_area_total) or actual_area_total > intent_area:
        raise PlanningContextError(
            "Placed room area must be finite and cannot exceed the intent area.", path="/rooms"
        )
    for left_index, left in enumerate(rooms):
        for right_index in range(left_index + 1, len(rooms)):
            if _rooms_overlap(left, rooms[right_index]):
                raise PlanningContextError(
                    "Placed rooms must not overlap.",
                    path=f"/rooms/{right_index}",
                    details={"other_plan_id": left.plan_id},
                )


def _validate_room_orientation(
    room: FloorPlanRoom, boundary: FloorPlanBoundary, index: int
) -> None:
    assert room.x is not None
    assert room.y is not None
    assert room.width is not None
    assert room.height is not None
    assert room.orientation is not None
    exposure = {
        "north": room.y + room.height == boundary.height,
        "south": room.y == 0,
        "east": room.x + room.width == boundary.width,
        "west": room.x == 0,
        "interior": (
            room.x > 0
            and room.y > 0
            and room.x + room.width < boundary.width
            and room.y + room.height < boundary.height
        ),
    }
    if not exposure[room.orientation]:
        raise PlanningContextError(
            "Room orientation must match its proposal-boundary exposure.",
            path=f"/rooms/{index}/orientation",
        )


def _rooms_overlap(left: FloorPlanRoom, right: FloorPlanRoom) -> bool:
    assert left.x is not None and left.y is not None
    assert left.width is not None and left.height is not None
    assert right.x is not None and right.y is not None
    assert right.width is not None and right.height is not None
    return (
        left.x < right.x + right.width
        and right.x < left.x + left.width
        and left.y < right.y + right.height
        and right.y < left.y + left.height
    )


def _parse_rooms(value: object, schema_version: str) -> tuple[FloorPlanRoom, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PlanningContextError("rooms must be an array.", path="/rooms")
    parsed: list[FloorPlanRoom] = []
    for index, room in enumerate(value):
        if not isinstance(room, Mapping):
            raise PlanningContextError(
                "Each floor-plan room must be an object.", path=f"/rooms/{index}"
            )
        try:
            parsed.append(FloorPlanRoom.from_dict(room, schema_version=schema_version))
        except PlanningContextError as error:
            raise _nested_context_error(error, f"/rooms/{index}") from error
    return tuple(parsed)


def _parse_constraints(value: object) -> tuple[FloorPlanConstraint, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PlanningContextError(
            "spatial_constraints must be an array.", path="/spatial_constraints"
        )
    parsed: list[FloorPlanConstraint] = []
    for index, constraint in enumerate(value):
        if not isinstance(constraint, Mapping):
            raise PlanningContextError(
                "Each floor-plan constraint must be an object.",
                path=f"/spatial_constraints/{index}",
            )
        try:
            parsed.append(FloorPlanConstraint.from_dict(constraint))
        except PlanningContextError as error:
            raise _nested_context_error(error, f"/spatial_constraints/{index}") from error
    return tuple(parsed)


def _require_token(value: object, path: str) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip().lower()
        or _TOKEN_PATTERN.fullmatch(value) is None
    ):
        raise PlanningContextError(
            "Floor-plan identifiers must use canonical lowercase tokens.", path=path
        )


def _positive_finite_float(value: object, path: str, label: str) -> float:
    converted = _finite_float(value, path, label)
    if converted <= 0:
        raise PlanningContextError(f"{label} must be positive and finite.", path=path)
    return converted


def _non_negative_finite_float(value: object, path: str, label: str) -> float:
    converted = _finite_float(value, path, label)
    if converted < 0:
        raise PlanningContextError(f"{label} must be non-negative and finite.", path=path)
    return converted


def _finite_float(value: object, path: str, label: str) -> float:
    if not _is_number(value):
        raise PlanningContextError(f"{label} must be a number.", path=path)
    try:
        converted = float(cast(int | float, value))
    except OverflowError as error:
        raise PlanningContextError(f"{label} must be finite.", path=path) from error
    if not math.isfinite(converted):
        raise PlanningContextError(f"{label} must be finite.", path=path)
    return converted


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _nested_context_error(error: PlanningContextError, prefix: str) -> PlanningContextError:
    return PlanningContextError(str(error), path=f"{prefix}{error.path}", details=error.details)


def _nested_design_error(error: InvalidDesignIntentError, prefix: str) -> PlanningContextError:
    return PlanningContextError(str(error), path=f"{prefix}{error.path}", details=error.details)
