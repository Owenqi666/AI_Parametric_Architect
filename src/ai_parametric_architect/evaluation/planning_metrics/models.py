"""Immutable contracts for detached spatial-plan evaluation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai_parametric_architect.domain import GeometryPrecisionPolicy, PlanningError

PLANNING_METRICS_SCHEMA_VERSION = "1.0.0"
MAX_PLANNING_EVALUATION_RUNS = 64
SOLVED_LAYOUT_REQUIRED = "SOLVED_LAYOUT_REQUIRED"
REPEATED_PLANS_REQUIRED = "REPEATED_PLANS_REQUIRED"
_CONTEXT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]*$")
_ROOM_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class PlanningMetricError(PlanningError):
    """Raised when detached planning-metric inputs violate their contract."""

    code = "PLANNING_METRIC_INPUT_INVALID"


@runtime_checkable
class PlanningThresholdSource(Protocol):
    """Provider-neutral threshold view structurally implemented by planning rules."""

    @property
    def minimum_room_areas(self) -> tuple[tuple[str, float], ...]: ...

    @property
    def default_minimum_room_area(self) -> float: ...

    @property
    def minimum_adjacency_contact(self) -> float: ...

    @property
    def separation_gap(self) -> float: ...

    @property
    def near_distance(self) -> float: ...


@dataclass(frozen=True, slots=True)
class PlanningMetricContext:
    """Explicit rules that make planning scores reproducible and comparable."""

    context_id: str
    minimum_room_areas: tuple[tuple[str, float], ...]
    default_minimum_room_area: float
    minimum_adjacency_contact: float
    separation_gap: float
    near_distance: float
    precision: GeometryPrecisionPolicy
    max_runs: int = MAX_PLANNING_EVALUATION_RUNS

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context_id, str)
            or len(self.context_id) > 128
            or _CONTEXT_ID_PATTERN.fullmatch(self.context_id) is None
        ):
            raise PlanningMetricError(
                "Planning metric context_id must be a canonical identifier.",
                path="/metric_context/context_id",
            )
        if not isinstance(self.minimum_room_areas, tuple):
            raise PlanningMetricError(
                "Planning metric minimum areas must be an immutable tuple.",
                path="/metric_context/minimum_room_areas",
            )
        normalized_areas: list[tuple[str, float]] = []
        seen: set[str] = set()
        previous_room_type = ""
        for index, entry in enumerate(self.minimum_room_areas):
            if (
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or _ROOM_TYPE_PATTERN.fullmatch(entry[0]) is None
                or entry[0] in seen
                or entry[0] <= previous_room_type
            ):
                raise PlanningMetricError(
                    "Planning metric minimum areas must use sorted unique room types.",
                    path=f"/metric_context/minimum_room_areas/{index}",
                )
            normalized_areas.append(
                (
                    entry[0],
                    _positive_finite_float(
                        entry[1], f"/metric_context/minimum_room_areas/{index}/1"
                    ),
                )
            )
            seen.add(entry[0])
            previous_room_type = entry[0]
        for field_name in (
            "default_minimum_room_area",
            "minimum_adjacency_contact",
            "separation_gap",
            "near_distance",
        ):
            object.__setattr__(
                self,
                field_name,
                _positive_finite_float(getattr(self, field_name), f"/metric_context/{field_name}"),
            )
        object.__setattr__(self, "minimum_room_areas", tuple(normalized_areas))
        if not isinstance(self.precision, GeometryPrecisionPolicy):
            raise PlanningMetricError(
                "Planning metrics require a GeometryPrecisionPolicy.",
                path="/metric_context/precision",
            )
        if (
            not isinstance(self.max_runs, int)
            or isinstance(self.max_runs, bool)
            or not 1 <= self.max_runs <= MAX_PLANNING_EVALUATION_RUNS
        ):
            raise PlanningMetricError(
                f"Planning metric max_runs must be from 1 to {MAX_PLANNING_EVALUATION_RUNS}.",
                path="/metric_context/max_runs",
            )

    @classmethod
    def from_threshold_source(
        cls,
        *,
        context_id: str,
        source: PlanningThresholdSource,
        precision: GeometryPrecisionPolicy,
        max_runs: int = MAX_PLANNING_EVALUATION_RUNS,
    ) -> PlanningMetricContext:
        if not isinstance(source, PlanningThresholdSource):
            raise PlanningMetricError(
                "Planning metric threshold source violates the provider-neutral contract.",
                path="/metric_context/source",
            )
        return cls(
            context_id=context_id,
            minimum_room_areas=tuple(sorted(source.minimum_room_areas)),
            default_minimum_room_area=source.default_minimum_room_area,
            minimum_adjacency_contact=source.minimum_adjacency_contact,
            separation_gap=source.separation_gap,
            near_distance=source.near_distance,
            precision=precision,
            max_runs=max_runs,
        )

    def minimum_area_for(self, room_type: str) -> float:
        return dict(self.minimum_room_areas).get(room_type, self.default_minimum_room_area)

    def to_dict(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "minimum_room_areas": [
                {"room_type": room_type, "minimum_area": area}
                for room_type, area in self.minimum_room_areas
            ],
            "default_minimum_room_area": self.default_minimum_room_area,
            "minimum_adjacency_contact": self.minimum_adjacency_contact,
            "separation_gap": self.separation_gap,
            "near_distance": self.near_distance,
            "precision": {
                "linear_tolerance": self.precision.linear_tolerance,
                "decimal_places": self.precision.decimal_places,
            },
            "max_runs": self.max_runs,
        }


@dataclass(frozen=True, slots=True)
class NormalizedMetricResult:
    name: str
    value: float | None
    sample_count: int
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _CONTEXT_ID_PATTERN.fullmatch(self.name) is None:
            raise ValueError("Metric result name must be canonical.")
        if (
            not isinstance(self.sample_count, int)
            or isinstance(self.sample_count, bool)
            or self.sample_count < 0
        ):
            raise ValueError("Metric sample_count must be a non-negative integer.")
        if self.value is None:
            if self.sample_count != 0 or not isinstance(self.reason, str) or not self.reason:
                raise ValueError("A non-applicable metric requires a reason and zero samples.")
            return
        normalized = _finite_float(self.value)
        if (
            normalized is None
            or not 0.0 <= normalized <= 1.0
            or self.sample_count < 1
            or self.reason is not None
        ):
            raise ValueError("Applicable metric values must be finite values from zero to one.")
        object.__setattr__(self, "value", normalized)

    @property
    def applicable(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "applicable": self.applicable,
            "sample_count": self.sample_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PlanMetricObservation:
    run_index: int
    strategy: str
    constraint_satisfaction: float | None
    spatial_efficiency: float | None
    circulation: float | None
    satisfied_constraints: int
    total_constraints: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_index, int)
            or isinstance(self.run_index, bool)
            or self.run_index < 0
        ):
            raise ValueError("run_index must be a non-negative integer.")
        if not isinstance(self.strategy, str) or not self.strategy:
            raise ValueError("strategy must be a non-empty string.")
        for value in (
            self.constraint_satisfaction,
            self.spatial_efficiency,
            self.circulation,
        ):
            normalized = None if value is None else _finite_float(value)
            if value is not None and (normalized is None or not 0.0 <= normalized <= 1.0):
                raise ValueError("Planning metric observations must be finite and normalized.")
        if (
            not isinstance(self.satisfied_constraints, int)
            or isinstance(self.satisfied_constraints, bool)
            or not isinstance(self.total_constraints, int)
            or isinstance(self.total_constraints, bool)
            or not 0 <= self.satisfied_constraints <= self.total_constraints
        ):
            raise ValueError("Constraint observation counts are inconsistent.")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_index": self.run_index,
            "strategy": self.strategy,
            "constraint_satisfaction": self.constraint_satisfaction,
            "spatial_efficiency": self.spatial_efficiency,
            "circulation": self.circulation,
            "satisfied_constraints": self.satisfied_constraints,
            "total_constraints": self.total_constraints,
        }


@dataclass(frozen=True, slots=True)
class PlanningMetricsReport:
    metric_context: PlanningMetricContext
    observations: tuple[PlanMetricObservation, ...]
    constraint_satisfaction_score: NormalizedMetricResult
    spatial_efficiency_score: NormalizedMetricResult
    circulation_score: NormalizedMetricResult
    plan_stability_score: NormalizedMetricResult
    exact_match_pairs: int
    comparison_pairs: int
    schema_version: str = PLANNING_METRICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PLANNING_METRICS_SCHEMA_VERSION:
            raise ValueError("Unsupported planning metrics report schema version.")
        if not isinstance(self.metric_context, PlanningMetricContext):
            raise ValueError("Planning metrics report requires a metric context.")
        if (
            not isinstance(self.observations, tuple)
            or not self.observations
            or not all(isinstance(value, PlanMetricObservation) for value in self.observations)
            or tuple(value.run_index for value in self.observations)
            != tuple(range(len(self.observations)))
        ):
            raise ValueError("Planning metrics report requires observations.")
        metric_results = (
            self.constraint_satisfaction_score,
            self.spatial_efficiency_score,
            self.circulation_score,
            self.plan_stability_score,
        )
        if not all(isinstance(value, NormalizedMetricResult) for value in metric_results):
            raise ValueError("Planning metrics report requires normalized metric results.")
        if (
            not isinstance(self.comparison_pairs, int)
            or isinstance(self.comparison_pairs, bool)
            or not isinstance(self.exact_match_pairs, int)
            or isinstance(self.exact_match_pairs, bool)
            or not 0 <= self.exact_match_pairs <= self.comparison_pairs
        ):
            raise ValueError("Planning metrics comparison counts are inconsistent.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_context": self.metric_context.to_dict(),
            "run_count": len(self.observations),
            "metrics": {
                "constraint_satisfaction_score": self.constraint_satisfaction_score.to_dict(),
                "spatial_efficiency_score": self.spatial_efficiency_score.to_dict(),
                "circulation_score": self.circulation_score.to_dict(),
                "plan_stability_score": self.plan_stability_score.to_dict(),
            },
            "exact_match_pairs": self.exact_match_pairs,
            "comparison_pairs": self.comparison_pairs,
            "observations": [observation.to_dict() for observation in self.observations],
        }


def not_applicable(name: str, reason: str) -> NormalizedMetricResult:
    return NormalizedMetricResult(name=name, value=None, sample_count=0, reason=reason)


def aggregate(name: str, values: tuple[float, ...]) -> NormalizedMetricResult:
    if not values:
        raise ValueError("Applicable metric aggregation requires at least one value.")
    value = math.fsum(values) / len(values)
    return NormalizedMetricResult(name=name, value=value, sample_count=len(values))


def normalized_value(value: float, metric_name: str) -> float:
    if not math.isfinite(value):
        raise PlanningMetricError(
            "Planning metric produced a non-finite value.",
            path=f"/metrics/{metric_name}",
        )
    return min(1.0, max(0.0, value))


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _positive_finite_float(value: object, path: str) -> float:
    converted = _finite_float(value)
    if converted is None or converted <= 0.0:
        raise PlanningMetricError(
            "Planning metric thresholds must be positive finite numbers.", path=path
        )
    return converted
