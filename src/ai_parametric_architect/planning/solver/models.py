"""Provider-neutral inputs and outputs for discrete floor-plan solving."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Final

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningContextError,
    SpatialConstraint,
)
from ai_parametric_architect.planning.rules import allocate_equal_target_areas

CP_SAT_STRATEGY: Final = "cp-sat-rectilinear-v1"
DEFAULT_MINIMUM_ROOM_AREAS: Final = (
    ("bathroom", 4.0),
    ("bedroom", 10.0),
    ("dining", 10.0),
    ("kitchen", 8.0),
    ("living", 18.0),
    ("office", 8.0),
    ("study", 6.0),
)
_MAX_SAFE_INTEGER: Final = (1 << 62) - 1
_MAX_RULE_RATIO_COMPONENT: Final = 10_000
_MAX_MINIMUM_AREA_RULES: Final = 256
_MAX_PLANNING_AREA: Final = 1_000_000.0
_MAX_PLANNING_COORDINATE: Final = 10_000.0
_MAX_DETERMINISTIC_TIME: Final = 60.0
_ROOM_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class PlanningGridPolicy:
    """The single length/area scaling policy used by the solver boundary."""

    units_per_metre: int = 2

    def __post_init__(self) -> None:
        if (
            not isinstance(self.units_per_metre, int)
            or isinstance(self.units_per_metre, bool)
            or not 1 <= self.units_per_metre <= 100
        ):
            raise PlanningContextError(
                "Planning grid units_per_metre must be an integer from 1 to 100.",
                path="/rules/grid/units_per_metre",
            )

    @property
    def area_units_per_square_metre(self) -> int:
        return self.units_per_metre * self.units_per_metre

    def exact_length_units(self, value: int | float, *, path: str) -> int:
        scaled = _decimal(value, path) * self.units_per_metre
        integral = scaled.to_integral_value()
        if scaled != integral:
            raise PlanningContextError(
                "Planning length must be exactly representable on the configured grid.",
                path=path,
                details={"units_per_metre": self.units_per_metre},
            )
        return _safe_positive_int(integral, path)

    def minimum_area_units(self, value: int | float, *, path: str) -> int:
        scaled = _decimal(value, path) * self.area_units_per_square_metre
        return _safe_positive_int(scaled.to_integral_value(rounding=ROUND_CEILING), path)

    def maximum_area_units(self, value: int | float, *, path: str) -> int:
        scaled = _decimal(value, path) * self.area_units_per_square_metre
        return _safe_positive_int(scaled.to_integral_value(rounding=ROUND_FLOOR), path)

    def length_from_units(self, value: int) -> float:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > _MAX_SAFE_INTEGER
        ):
            raise PlanningContextError(
                "Planning grid output units must be a safe non-negative integer.",
                path="/solver/output",
            )
        return value / self.units_per_metre


@dataclass(frozen=True, slots=True)
class OptimizationWeights:
    utilization: int = 40
    target_area: int = 12
    compactness: int = 4
    circulation: int = 1
    orientation: int = 20
    optional_constraint: int = 30

    def __post_init__(self) -> None:
        for field_name in (
            "utilization",
            "target_area",
            "compactness",
            "circulation",
            "orientation",
            "optional_constraint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10_000:
                raise PlanningContextError(
                    "Optimization weights must be integers from 0 to 10000.",
                    path=f"/rules/optimization/{field_name}",
                )
        if not any(
            getattr(self, name)
            for name in (
                "utilization",
                "target_area",
                "compactness",
                "circulation",
                "orientation",
                "optional_constraint",
            )
        ):
            raise PlanningContextError(
                "At least one optimization weight must be positive.",
                path="/rules/optimization",
            )


@dataclass(frozen=True, slots=True)
class PlanningRules:
    """Versioned deterministic rules supplied to every planning problem."""

    version: str = "1.0.0"
    grid: PlanningGridPolicy = field(default_factory=PlanningGridPolicy)
    optimization: OptimizationWeights = field(default_factory=OptimizationWeights)
    minimum_room_areas: tuple[tuple[str, float], ...] = DEFAULT_MINIMUM_ROOM_AREAS
    default_minimum_room_area: float = 6.0
    minimum_room_width: float = 2.0
    minimum_room_height: float = 2.0
    minimum_adjacency_contact: float = 1.0
    separation_gap: float = 1.0
    near_distance: float = 8.0
    target_utilization_numerator: int = 9
    target_utilization_denominator: int = 10
    boundary_aspect_numerator: int = 4
    boundary_aspect_denominator: int = 3
    boundary_width: float | None = None
    boundary_height: float | None = None
    max_rooms: int = 16
    max_constraints: int = 64
    max_area: float = 2_500.0
    max_coordinate: float = 250.0
    max_deterministic_time: float = 5.0
    random_seed: int = 0

    def __post_init__(self) -> None:
        if self.version != "1.0.0":
            raise PlanningContextError("Unsupported planning rules version.", path="/rules/version")
        if not isinstance(self.grid, PlanningGridPolicy):
            raise PlanningContextError(
                "Planning rules require a PlanningGridPolicy.", path="/rules/grid"
            )
        if not isinstance(self.optimization, OptimizationWeights):
            raise PlanningContextError(
                "Planning rules require OptimizationWeights.", path="/rules/optimization"
            )
        if not isinstance(self.minimum_room_areas, tuple):
            raise PlanningContextError(
                "Minimum room-area rules must be an immutable tuple.",
                path="/rules/minimum_room_areas",
            )
        _positive_finite(self.default_minimum_room_area, "/rules/default_minimum_room_area")
        for name in (
            "minimum_room_width",
            "minimum_room_height",
            "minimum_adjacency_contact",
            "separation_gap",
            "near_distance",
            "max_area",
            "max_coordinate",
            "max_deterministic_time",
        ):
            _positive_finite(getattr(self, name), f"/rules/{name}")
        if self.max_area > _MAX_PLANNING_AREA:
            raise PlanningContextError(
                "Solver max_area exceeds the implementation safety limit.",
                path="/rules/max_area",
                details={"maximum": _MAX_PLANNING_AREA},
            )
        if self.default_minimum_room_area > self.max_area:
            raise PlanningContextError(
                "Default minimum room area exceeds max_area.",
                path="/rules/default_minimum_room_area",
                details={"max_area": self.max_area},
            )
        if self.max_coordinate > _MAX_PLANNING_COORDINATE:
            raise PlanningContextError(
                "Solver max_coordinate exceeds the implementation safety limit.",
                path="/rules/max_coordinate",
                details={"maximum": _MAX_PLANNING_COORDINATE},
            )
        if self.max_deterministic_time > _MAX_DETERMINISTIC_TIME:
            raise PlanningContextError(
                "Solver deterministic-time budget exceeds the implementation safety limit.",
                path="/rules/max_deterministic_time",
                details={"maximum": _MAX_DETERMINISTIC_TIME},
            )
        for name in (
            "minimum_room_width",
            "minimum_room_height",
            "minimum_adjacency_contact",
            "separation_gap",
            "near_distance",
            "max_coordinate",
        ):
            self.grid.exact_length_units(getattr(self, name), path=f"/rules/{name}")
            if getattr(self, name) > self.max_coordinate:
                raise PlanningContextError(
                    "Solver length rule exceeds max_coordinate.",
                    path=f"/rules/{name}",
                    details={"max_coordinate": self.max_coordinate},
                )
        for name in (
            "target_utilization_numerator",
            "target_utilization_denominator",
            "boundary_aspect_numerator",
            "boundary_aspect_denominator",
            "max_rooms",
            "max_constraints",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise PlanningContextError(
                    "Planning rule integer bounds must be positive integers.",
                    path=f"/rules/{name}",
                )
        for name in (
            "target_utilization_numerator",
            "target_utilization_denominator",
            "boundary_aspect_numerator",
            "boundary_aspect_denominator",
        ):
            if getattr(self, name) > _MAX_RULE_RATIO_COMPONENT:
                raise PlanningContextError(
                    "Planning rule ratio component exceeds the safety limit.",
                    path=f"/rules/{name}",
                    details={"maximum": _MAX_RULE_RATIO_COMPONENT},
                )
        if self.target_utilization_numerator >= self.target_utilization_denominator:
            raise PlanningContextError(
                "Target utilization must be strictly between zero and one.",
                path="/rules/target_utilization_numerator",
            )
        if self.max_rooms > 64 or self.max_constraints > 128:
            raise PlanningContextError(
                "Planning rule budgets exceed DesignIntent limits.", path="/rules"
            )
        if (
            not isinstance(self.random_seed, int)
            or isinstance(self.random_seed, bool)
            or not 0 <= self.random_seed <= 2_147_483_647
        ):
            raise PlanningContextError(
                "random_seed must be a non-negative 32-bit integer.",
                path="/rules/random_seed",
            )
        if (self.boundary_width is None) != (self.boundary_height is None):
            raise PlanningContextError(
                "Explicit boundary width and height must be supplied together.",
                path="/rules/boundary_width",
            )
        if self.boundary_width is not None and self.boundary_height is not None:
            self.grid.exact_length_units(self.boundary_width, path="/rules/boundary_width")
            self.grid.exact_length_units(self.boundary_height, path="/rules/boundary_height")
            if (
                self.boundary_width > self.max_coordinate
                or self.boundary_height > self.max_coordinate
            ):
                raise PlanningContextError(
                    "Explicit planning boundary exceeds max_coordinate.",
                    path="/rules/boundary_width",
                    details={"max_coordinate": self.max_coordinate},
                )
        if len(self.minimum_room_areas) > _MAX_MINIMUM_AREA_RULES:
            raise PlanningContextError(
                "Minimum room-area rules exceed the implementation budget.",
                path="/rules/minimum_room_areas",
                details={"maximum": _MAX_MINIMUM_AREA_RULES},
            )
        seen: set[str] = set()
        for index, entry in enumerate(self.minimum_room_areas):
            if (
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or _ROOM_TYPE_PATTERN.fullmatch(entry[0]) is None
                or entry[0] in seen
            ):
                raise PlanningContextError(
                    "Minimum room-area rules must use unique room-type entries.",
                    path=f"/rules/minimum_room_areas/{index}",
                )
            _positive_finite(entry[1], f"/rules/minimum_room_areas/{index}/1")
            if entry[1] > self.max_area:
                raise PlanningContextError(
                    "Minimum room area exceeds max_area.",
                    path=f"/rules/minimum_room_areas/{index}/1",
                    details={"max_area": self.max_area},
                )
            seen.add(entry[0])

    def minimum_area_for(self, room_type: str) -> float:
        return dict(self.minimum_room_areas).get(room_type, self.default_minimum_room_area)


@dataclass(frozen=True, slots=True)
class GridBoundary:
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class RoomSpecification:
    plan_id: str
    room_type: str
    target_area: float
    target_area_units: int
    minimum_area_units: int
    minimum_width_units: int
    minimum_height_units: int


@dataclass(frozen=True, slots=True)
class BoundSpatialConstraint:
    constraint: SpatialConstraint
    source_index: int
    target_index: int


@dataclass(frozen=True, slots=True)
class PlanningProblem:
    intent: DesignIntent
    spatial_constraints: tuple[SpatialConstraint, ...]
    rules: PlanningRules
    boundary: GridBoundary
    rooms: tuple[RoomSpecification, ...]
    bound_constraints: tuple[BoundSpatialConstraint, ...]
    maximum_room_area_units: int

    @classmethod
    def from_intent(
        cls, intent: DesignIntent, rules: PlanningRules | None = None
    ) -> PlanningProblem:
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Constraint planning requires a validated DesignIntent.",
                path="/intent",
                details={"reason": "INVALID_INTENT_TYPE"},
            )
        selected_rules = PlanningRules() if rules is None else rules
        if not isinstance(selected_rules, PlanningRules):
            raise PlanningContextError("Constraint planning requires PlanningRules.", path="/rules")
        if len(intent.rooms) > selected_rules.max_rooms:
            raise PlanningContextError(
                "Design intent exceeds the solver room budget.",
                path="/intent/rooms",
                details={"maximum": selected_rules.max_rooms, "actual": len(intent.rooms)},
            )
        if len(intent.spatial_constraints) > selected_rules.max_constraints:
            raise PlanningContextError(
                "Design intent exceeds the solver constraint budget.",
                path="/intent/spatial_constraints",
                details={
                    "maximum": selected_rules.max_constraints,
                    "actual": len(intent.spatial_constraints),
                },
            )
        if intent.area > selected_rules.max_area:
            raise PlanningContextError(
                "Design intent exceeds the solver area budget.",
                path="/intent/area",
                details={"maximum": selected_rules.max_area, "actual": intent.area},
            )

        maximum_area_units = selected_rules.grid.maximum_area_units(
            intent.area, path="/intent/area"
        )
        boundary = _derive_boundary(selected_rules, maximum_area_units)
        target_areas = allocate_equal_target_areas(intent.area, len(intent.rooms))
        minimum_width = selected_rules.grid.exact_length_units(
            selected_rules.minimum_room_width, path="/rules/minimum_room_width"
        )
        minimum_height = selected_rules.grid.exact_length_units(
            selected_rules.minimum_room_height, path="/rules/minimum_room_height"
        )
        rooms = tuple(
            RoomSpecification(
                plan_id=f"plan_room_{index:03d}",
                room_type=room_type,
                target_area=target_area,
                target_area_units=selected_rules.grid.maximum_area_units(
                    target_area, path=f"/intent/rooms/{index - 1}"
                ),
                minimum_area_units=selected_rules.grid.minimum_area_units(
                    selected_rules.minimum_area_for(room_type),
                    path=f"/rules/minimum_room_areas/{room_type}",
                ),
                minimum_width_units=minimum_width,
                minimum_height_units=minimum_height,
            )
            for index, (room_type, target_area) in enumerate(
                zip(intent.rooms, target_areas, strict=True), start=1
            )
        )
        minimum_total = sum(room.minimum_area_units for room in rooms)
        if minimum_total > maximum_area_units:
            raise PlanningContextError(
                "Minimum room areas exceed the design intent area.",
                path="/intent/area",
                details={
                    "reason": "MINIMUM_ROOM_AREA_INFEASIBLE",
                    "available_area_units": maximum_area_units,
                    "required_area_units": minimum_total,
                },
            )
        if any(
            room.minimum_width_units > boundary.width or room.minimum_height_units > boundary.height
            for room in rooms
        ):
            raise PlanningContextError(
                "A room minimum dimension exceeds the planning boundary.",
                path="/rules",
                details={"reason": "MINIMUM_ROOM_DIMENSION_INFEASIBLE"},
            )

        first_index_by_type: dict[str, int] = {}
        for index, room_type in enumerate(intent.rooms):
            first_index_by_type.setdefault(room_type, index)
        bound_constraints = tuple(
            BoundSpatialConstraint(
                constraint=constraint,
                source_index=first_index_by_type[constraint.source_room_type],
                target_index=first_index_by_type[constraint.target_room_type],
            )
            for constraint in intent.spatial_constraints
        )
        return cls(
            intent=intent,
            spatial_constraints=intent.spatial_constraints,
            rules=selected_rules,
            boundary=boundary,
            rooms=rooms,
            bound_constraints=bound_constraints,
            maximum_room_area_units=maximum_area_units,
        )


@dataclass(frozen=True, slots=True)
class SolvedRoom:
    specification: RoomSpecification
    x: int
    y: int
    width: int
    height: int
    orientation: str


@dataclass(frozen=True, slots=True)
class SolverSolution:
    rooms: tuple[SolvedRoom, ...]
    objective_value: int
    best_objective_bound: int


def _derive_boundary(rules: PlanningRules, maximum_area_units: int) -> GridBoundary:
    maximum_coordinate_units = rules.grid.exact_length_units(
        rules.max_coordinate, path="/rules/max_coordinate"
    )
    if rules.boundary_width is not None and rules.boundary_height is not None:
        width = rules.grid.exact_length_units(rules.boundary_width, path="/rules/boundary_width")
        height = rules.grid.exact_length_units(rules.boundary_height, path="/rules/boundary_height")
    else:
        required_boundary_area = _ceil_div(
            maximum_area_units * rules.target_utilization_denominator,
            rules.target_utilization_numerator,
        )
        aspect_scaled_area = _ceil_div(
            required_boundary_area * rules.boundary_aspect_numerator,
            rules.boundary_aspect_denominator,
        )
        width = math.isqrt(aspect_scaled_area)
        if width * width < aspect_scaled_area:
            width += 1
        height = _ceil_div(required_boundary_area, width)
    if width > maximum_coordinate_units or height > maximum_coordinate_units:
        raise PlanningContextError(
            "Derived planning boundary exceeds the coordinate budget.",
            path="/rules/max_coordinate",
            details={
                "maximum_units": maximum_coordinate_units,
                "width_units": width,
                "height_units": height,
            },
        )
    if width * height < maximum_area_units:
        raise PlanningContextError(
            "Planning boundary is smaller than the design intent area.",
            path="/rules/boundary_width",
            details={
                "boundary_area_units": width * height,
                "intent_area_units": maximum_area_units,
            },
        )
    _safe_objective_integer(width * height, "/rules")
    return GridBoundary(width=width, height=height)


def _decimal(value: object, path: str) -> Decimal:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PlanningContextError("Planning values must be numbers.", path=path)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise PlanningContextError("Planning values must be finite numbers.", path=path) from error
    if not result.is_finite() or result <= 0:
        raise PlanningContextError("Planning values must be positive and finite.", path=path)
    return result


def _positive_finite(value: object, path: str) -> None:
    _decimal(value, path)


def _safe_positive_int(value: Decimal, path: str) -> int:
    result = int(value)
    if result <= 0 or result > _MAX_SAFE_INTEGER:
        raise PlanningContextError("Scaled planning value is outside the safe range.", path=path)
    return result


def _safe_objective_integer(value: int, path: str) -> int:
    if abs(value) > _MAX_SAFE_INTEGER:
        raise PlanningContextError("Planning objective exceeds the safe integer range.", path=path)
    return value


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


__all__ = [
    "CP_SAT_STRATEGY",
    "BoundSpatialConstraint",
    "GridBoundary",
    "OptimizationWeights",
    "PlanningGridPolicy",
    "PlanningProblem",
    "PlanningRules",
    "RoomSpecification",
    "SolvedRoom",
    "SolverSolution",
]
