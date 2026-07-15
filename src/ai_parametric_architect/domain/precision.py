"""Central geometry precision and deterministic number-formatting policy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ai_parametric_architect.domain.model import ModelDocument, Point2
from ai_parametric_architect.domain.numbers import finite_float

_MAX_DECIMAL_PLACES = 12
MIN_LINEAR_TOLERANCE = 1e-12
MAX_LINEAR_TOLERANCE = 1e-2


@dataclass(frozen=True, slots=True)
class GeometryPrecisionPolicy:
    """Own every tolerance decision used by geometry, validation, and rendering."""

    linear_tolerance: float
    decimal_places: int

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.linear_tolerance)
            or not MIN_LINEAR_TOLERANCE <= self.linear_tolerance <= MAX_LINEAR_TOLERANCE
        ):
            raise ValueError(
                "linear_tolerance must be finite and between "
                f"{MIN_LINEAR_TOLERANCE} and {MAX_LINEAR_TOLERANCE} metres"
            )
        if not 0 <= self.decimal_places <= _MAX_DECIMAL_PLACES:
            raise ValueError(f"decimal_places must be between 0 and {_MAX_DECIMAL_PLACES}")

    @classmethod
    def from_model(cls, model: ModelDocument) -> GeometryPrecisionPolicy:
        """Build a policy from a structurally validated model document."""

        settings = model["geometry_settings"]
        tolerance = finite_float(settings["linear_tolerance"])
        if tolerance is None:
            raise ValueError("linear_tolerance must be a finite number")
        places = max(0, min(_MAX_DECIMAL_PLACES, math.ceil(-math.log10(tolerance))))
        return cls(linear_tolerance=tolerance, decimal_places=places)

    @property
    def area_tolerance(self) -> float:
        return self.linear_tolerance * self.linear_tolerance

    def points_equal(self, first: Point2, second: Point2) -> bool:
        return math.dist(first, second) <= self.linear_tolerance

    def is_zero_length(self, value: float) -> bool:
        return abs(value) <= self.linear_tolerance

    def is_zero_area(self, value: float) -> bool:
        return abs(value) <= self.area_tolerance

    def format_number(self, value: float) -> str:
        """Format SVG numbers deterministically, including a canonical zero."""

        if not math.isfinite(value):
            raise ValueError("Formatted geometry values must be finite")
        normalized = 0.0 if abs(value) <= self.linear_tolerance / 2 else value
        return f"{normalized:.{self.decimal_places}f}"
