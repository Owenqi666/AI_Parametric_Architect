"""Provider-neutral, immutable architecture requirement values."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Final

from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError

MAX_INTENT_ROOMS: Final = 64
MAX_SPATIAL_CONSTRAINTS: Final = 128
_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_ORIENTATIONS = frozenset({"east", "north", "south", "west"})


class SpatialRelation(StrEnum):
    ADJACENT_TO = "adjacent_to"
    NEAR = "near"
    SEPARATED_FROM = "separated_from"
    NORTH_OF = "north_of"
    SOUTH_OF = "south_of"
    EAST_OF = "east_of"
    WEST_OF = "west_of"


@dataclass(frozen=True, slots=True, init=False)
class RoomRequirement:
    room_type: str
    count: int

    def __init__(self, room_type: str, count: int = 1) -> None:
        _require_token(room_type, "room_type")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 1
            or count > MAX_INTENT_ROOMS
        ):
            raise InvalidDesignIntentError(
                f"Room requirement count must be between 1 and {MAX_INTENT_ROOMS}.",
                path="/count",
                details={"maximum": MAX_INTENT_ROOMS},
            )
        object.__setattr__(self, "room_type", room_type)
        object.__setattr__(self, "count", count)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RoomRequirement:
        if set(value) != {"room_type", "count"}:
            raise InvalidDesignIntentError("Room requirement has missing or unexpected fields.")
        room_type = value.get("room_type")
        count = value.get("count")
        if not isinstance(room_type, str):
            raise InvalidDesignIntentError("room_type must be a string.", path="/room_type")
        if not isinstance(count, int) or isinstance(count, bool):
            raise InvalidDesignIntentError("count must be an integer.", path="/count")
        return cls(room_type, count)

    def to_dict(self) -> dict[str, object]:
        return {"room_type": self.room_type, "count": self.count}


@dataclass(frozen=True, slots=True, init=False)
class SpatialConstraint:
    source_room_type: str
    relation: SpatialRelation
    target_room_type: str
    required: bool

    def __init__(
        self,
        *,
        source_room_type: str,
        relation: SpatialRelation | str,
        target_room_type: str,
        required: bool = True,
    ) -> None:
        _require_token(source_room_type, "source_room_type")
        _require_token(target_room_type, "target_room_type")
        try:
            relation_value = SpatialRelation(relation)
        except (TypeError, ValueError) as error:
            raise InvalidDesignIntentError(
                "Spatial relation is not supported by DesignIntent v1.",
                path="/relation",
            ) from error
        if source_room_type == target_room_type:
            raise InvalidDesignIntentError(
                "A spatial constraint must reference two different room types.",
                path="/target_room_type",
            )
        if not isinstance(required, bool):
            raise InvalidDesignIntentError("required must be a boolean.", path="/required")

        object.__setattr__(self, "source_room_type", source_room_type)
        object.__setattr__(self, "relation", relation_value)
        object.__setattr__(self, "target_room_type", target_room_type)
        object.__setattr__(self, "required", required)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpatialConstraint:
        expected = {"source_room_type", "relation", "target_room_type", "required"}
        if set(value) != expected:
            raise InvalidDesignIntentError("Spatial constraint has missing or unexpected fields.")
        source = value.get("source_room_type")
        relation = value.get("relation")
        target = value.get("target_room_type")
        required = value.get("required")
        if not isinstance(source, str):
            raise InvalidDesignIntentError(
                "source_room_type must be a string.", path="/source_room_type"
            )
        if not isinstance(relation, str):
            raise InvalidDesignIntentError("relation must be a string.", path="/relation")
        if not isinstance(target, str):
            raise InvalidDesignIntentError(
                "target_room_type must be a string.", path="/target_room_type"
            )
        if not isinstance(required, bool):
            raise InvalidDesignIntentError("required must be a boolean.", path="/required")
        return cls(
            source_room_type=source,
            relation=relation,
            target_room_type=target,
            required=required,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_room_type": self.source_room_type,
            "relation": self.relation.value,
            "target_room_type": self.target_room_type,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True, init=False)
class DesignIntent:
    building_type: str
    area: float
    rooms: tuple[str, ...]
    orientation: str | None
    spatial_constraints: tuple[SpatialConstraint, ...]

    def __init__(
        self,
        *,
        building_type: str,
        area: int | float,
        rooms: Sequence[str] | None = None,
        room_requirements: Sequence[RoomRequirement] | None = None,
        orientation: str | None = None,
        spatial_constraints: Sequence[SpatialConstraint] = (),
    ) -> None:
        _require_token(building_type, "building_type")
        numeric_area = _as_float(area)
        if numeric_area is None or not isfinite(numeric_area) or numeric_area <= 0:
            raise InvalidDesignIntentError(
                "Design area must be a positive finite number.",
                path="/area",
            )
        room_values = _rooms_from_inputs(rooms, room_requirements)
        if orientation is not None and orientation not in _ORIENTATIONS:
            raise InvalidDesignIntentError(
                "Orientation must be north, south, east, west, or null.",
                path="/orientation",
            )
        constraint_values = _constraints(spatial_constraints, room_values)

        object.__setattr__(self, "building_type", building_type)
        object.__setattr__(self, "area", numeric_area)
        object.__setattr__(self, "rooms", room_values)
        object.__setattr__(self, "orientation", orientation)
        object.__setattr__(self, "spatial_constraints", constraint_values)

    @property
    def room_requirements(self) -> tuple[RoomRequirement, ...]:
        counts = Counter(self.rooms)
        return tuple(RoomRequirement(room_type, count) for room_type, count in counts.items())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> DesignIntent:
        allowed_fields = {
            "area",
            "building_type",
            "orientation",
            "room_requirements",
            "rooms",
            "spatial_constraints",
        }
        required_fields = {"area", "building_type"}
        has_rooms = "rooms" in value
        has_requirements = "room_requirements" in value
        if (
            not required_fields.issubset(value)
            or not set(value).issubset(allowed_fields)
            or has_rooms == has_requirements
        ):
            raise InvalidDesignIntentError("Design intent has missing or unexpected fields.")
        building_type = value.get("building_type")
        area = value.get("area")
        rooms = value.get("rooms")
        room_requirements_value = value.get("room_requirements")
        orientation = value.get("orientation")
        constraints_value = value.get("spatial_constraints", ())
        if not isinstance(building_type, str):
            raise InvalidDesignIntentError(
                "building_type must be a string.",
                path="/building_type",
            )
        if not isinstance(area, (int, float)) or isinstance(area, bool):
            raise InvalidDesignIntentError("area must be a number.", path="/area")
        room_requirements: tuple[RoomRequirement, ...] | None = None
        if has_rooms and (not isinstance(rooms, Sequence) or isinstance(rooms, (str, bytes))):
            raise InvalidDesignIntentError("rooms must be an array.", path="/rooms")
        if has_requirements:
            if not isinstance(room_requirements_value, Sequence) or isinstance(
                room_requirements_value, (str, bytes)
            ):
                raise InvalidDesignIntentError(
                    "room_requirements must be an array.", path="/room_requirements"
                )
            parsed_requirements: list[RoomRequirement] = []
            for index, requirement in enumerate(room_requirements_value):
                if not isinstance(requirement, Mapping):
                    raise InvalidDesignIntentError(
                        "Each room requirement must be an object.",
                        path=f"/room_requirements/{index}",
                    )
                try:
                    parsed_requirements.append(RoomRequirement.from_dict(requirement))
                except InvalidDesignIntentError as error:
                    raise _nested_error(error, f"/room_requirements/{index}") from error
            room_requirements = tuple(parsed_requirements)
        if orientation is not None and not isinstance(orientation, str):
            raise InvalidDesignIntentError(
                "orientation must be a string or null.",
                path="/orientation",
            )
        if not isinstance(constraints_value, Sequence) or isinstance(
            constraints_value, (str, bytes)
        ):
            raise InvalidDesignIntentError(
                "spatial_constraints must be an array.", path="/spatial_constraints"
            )
        parsed_constraints: list[SpatialConstraint] = []
        for index, constraint in enumerate(constraints_value):
            if not isinstance(constraint, Mapping):
                raise InvalidDesignIntentError(
                    "Each spatial constraint must be an object.",
                    path=f"/spatial_constraints/{index}",
                )
            try:
                parsed_constraints.append(SpatialConstraint.from_dict(constraint))
            except InvalidDesignIntentError as error:
                raise _nested_error(error, f"/spatial_constraints/{index}") from error
        return cls(
            building_type=building_type,
            area=area,
            rooms=rooms if has_rooms else None,
            room_requirements=room_requirements,
            orientation=orientation,
            spatial_constraints=parsed_constraints,
        )

    def to_dict(self) -> dict[str, object]:
        area: int | float = int(self.area) if self.area.is_integer() else self.area
        result: dict[str, object] = {
            "building_type": self.building_type,
            "area": area,
            "rooms": list(self.rooms),
            "orientation": self.orientation,
        }
        if self.spatial_constraints:
            result["spatial_constraints"] = [
                constraint.to_dict() for constraint in self.spatial_constraints
            ]
        return result

    def to_compact_dict(self) -> dict[str, object]:
        value = self.to_dict()
        value.pop("rooms")
        value["room_requirements"] = [
            requirement.to_dict() for requirement in self.room_requirements
        ]
        return value


def _require_token(value: object, field_path: str) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip().lower()
        or _TOKEN_PATTERN.fullmatch(value) is None
    ):
        raise InvalidDesignIntentError(
            "Design intent values must use canonical lowercase tokens.",
            path=f"/{field_path}",
        )


def _as_float(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return float(value)
    except OverflowError:
        return None


def _rooms_from_inputs(
    rooms: Sequence[str] | None,
    room_requirements: Sequence[RoomRequirement] | None,
) -> tuple[str, ...]:
    if (rooms is None) == (room_requirements is None):
        raise InvalidDesignIntentError(
            "Provide exactly one of rooms or room_requirements.",
            path="/rooms",
        )
    if room_requirements is not None:
        error_path = "/room_requirements"
        if isinstance(room_requirements, (str, bytes)) or not isinstance(
            room_requirements, Sequence
        ):
            raise InvalidDesignIntentError(
                "room_requirements must be an array.", path="/room_requirements"
            )
        requirements = tuple(room_requirements)
        if not requirements or not all(
            isinstance(requirement, RoomRequirement) for requirement in requirements
        ):
            raise InvalidDesignIntentError(
                "room_requirements must contain RoomRequirement values.",
                path="/room_requirements",
            )
        room_types = tuple(requirement.room_type for requirement in requirements)
        if len(room_types) != len(set(room_types)):
            raise InvalidDesignIntentError(
                "Compact room requirements must use unique room types.",
                path="/room_requirements",
            )
        values = tuple(
            room_type
            for requirement in requirements
            for room_type in (requirement.room_type,) * requirement.count
        )
    else:
        error_path = "/rooms"
        if isinstance(rooms, (str, bytes)) or not isinstance(rooms, Sequence):
            raise InvalidDesignIntentError(
                "Design rooms must be an array of canonical room types.",
                path="/rooms",
            )
        values = tuple(rooms)
        for index, room_type in enumerate(values):
            _require_token(room_type, f"rooms/{index}")
    if not values:
        raise InvalidDesignIntentError(
            "Design intent must request at least one room.", path=error_path
        )
    if len(values) > MAX_INTENT_ROOMS:
        raise InvalidDesignIntentError(
            f"Design intent cannot request more than {MAX_INTENT_ROOMS} rooms.",
            path=error_path,
            details={"maximum": MAX_INTENT_ROOMS},
        )
    return values


def _constraints(
    values: Sequence[SpatialConstraint],
    rooms: tuple[str, ...],
) -> tuple[SpatialConstraint, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidDesignIntentError(
            "spatial_constraints must be an array.", path="/spatial_constraints"
        )
    constraints = tuple(values)
    if len(constraints) > MAX_SPATIAL_CONSTRAINTS:
        raise InvalidDesignIntentError(
            f"Design intent cannot contain more than {MAX_SPATIAL_CONSTRAINTS} constraints.",
            path="/spatial_constraints",
            details={"maximum": MAX_SPATIAL_CONSTRAINTS},
        )
    if not all(isinstance(constraint, SpatialConstraint) for constraint in constraints):
        raise InvalidDesignIntentError(
            "spatial_constraints must contain SpatialConstraint values.",
            path="/spatial_constraints",
        )
    if len(constraints) != len(set(constraints)):
        raise InvalidDesignIntentError(
            "Spatial constraints must be unique.", path="/spatial_constraints"
        )
    room_types = set(rooms)
    for index, constraint in enumerate(constraints):
        missing = tuple(
            room_type
            for room_type in (constraint.source_room_type, constraint.target_room_type)
            if room_type not in room_types
        )
        if missing:
            raise InvalidDesignIntentError(
                "Spatial constraints may only reference requested room types.",
                path=f"/spatial_constraints/{index}",
                details={"missing_room_types": list(missing)},
            )
    return tuple(
        sorted(
            constraints,
            key=lambda constraint: (
                constraint.source_room_type,
                constraint.relation.value,
                constraint.target_room_type,
                not constraint.required,
            ),
        )
    )


def _nested_error(error: InvalidDesignIntentError, prefix: str) -> InvalidDesignIntentError:
    return InvalidDesignIntentError(
        str(error),
        path=f"{prefix}{error.path}",
        details=error.details,
    )
