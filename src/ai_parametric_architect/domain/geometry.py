"""Neutral geometry results that may cross the geometry-engine boundary."""

from __future__ import annotations

from dataclasses import dataclass

from ai_parametric_architect.domain.model import Point2, Ring2


@dataclass(frozen=True, slots=True)
class SegmentAnalysis:
    """Deterministic facts about a two-dimensional segment."""

    has_finite_coordinates: bool
    length: float


@dataclass(frozen=True, slots=True)
class RoomAnalysis:
    """Deterministic facts about a room polygon."""

    has_finite_coordinates: bool
    rings_closed: bool
    is_valid: bool
    area: float
    validity_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SegmentProjection:
    """A serializable segment projection used by renderers."""

    start: Point2
    end: Point2


@dataclass(frozen=True, slots=True)
class PolygonProjection:
    """A serializable polygon projection used by renderers."""

    exterior: Ring2
    holes: tuple[Ring2, ...] = ()
