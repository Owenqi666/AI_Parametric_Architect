from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from ai_parametric_architect.domain import GeometryPrecisionPolicy
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine


@pytest.fixture
def engine() -> ShapelyGeometryEngine:
    return ShapelyGeometryEngine()


@pytest.fixture
def precision() -> GeometryPrecisionPolicy:
    return GeometryPrecisionPolicy(linear_tolerance=0.000001, decimal_places=6)


def room(exterior: list[list[float]]) -> dict[str, Any]:
    return {"geometry": {"type": "Polygon2D", "exterior": exterior, "holes": []}}


def wall(alignment: str = "center") -> dict[str, Any]:
    return {
        "axis": {"type": "Segment2D", "start": [0.0, 0.0], "end": [4.0, 0.0]},
        "thickness": 0.2,
        "alignment": alignment,
    }


def test_room_analysis_reports_area_and_validity(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    model_room = room([[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]])

    analysis = engine.analyze_room(model_room, precision)

    assert analysis.has_finite_coordinates
    assert analysis.rings_closed
    assert analysis.is_valid
    assert analysis.area == pytest.approx(12.0)


def test_room_analysis_detects_self_intersection(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    bow_tie = room([[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]])

    analysis = engine.analyze_room(bow_tie, precision)

    assert not analysis.is_valid
    assert analysis.validity_reason is not None
    assert "Self-intersection" in analysis.validity_reason


def test_room_analysis_detects_unclosed_and_non_finite_rings(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    unclosed = room([[0, 0], [2, 0], [2, 2], [0, 2]])
    non_finite = room([[0, 0], [math.inf, 0], [2, 2], [0, 0]])

    assert not engine.analyze_room(unclosed, precision).rings_closed
    assert not engine.analyze_room(non_finite, precision).has_finite_coordinates


def test_segment_analysis_is_neutral_and_handles_non_finite(
    engine: ShapelyGeometryEngine,
) -> None:
    finite = {"start": [0.0, 0.0], "end": [3.0, 4.0]}
    non_finite = {"start": [0.0, 0.0], "end": [math.nan, 4.0]}

    assert engine.analyze_segment(finite).length == pytest.approx(5.0)
    assert not engine.analyze_segment(non_finite).has_finite_coordinates


def test_room_overlap_returns_intersection_area(engine: ShapelyGeometryEngine) -> None:
    first = room([[0, 0], [3, 0], [3, 2], [0, 2], [0, 0]])
    second = room([[2, 0], [4, 0], [4, 2], [2, 2], [2, 0]])

    assert engine.room_overlap_area(first, second) == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("alignment", "minimum_y", "maximum_y"),
    [("center", -0.1, 0.1), ("left", 0.0, 0.2), ("right", -0.2, 0.0)],
)
def test_wall_footprint_respects_alignment(
    engine: ShapelyGeometryEngine,
    precision: GeometryPrecisionPolicy,
    alignment: str,
    minimum_y: float,
    maximum_y: float,
) -> None:
    footprint = engine.wall_footprint(wall(alignment), precision)
    y_values = [point[1] for point in footprint.exterior]

    assert min(y_values) == pytest.approx(minimum_y)
    assert max(y_values) == pytest.approx(maximum_y)
    assert footprint.exterior[0] == footprint.exterior[-1]


def test_opening_projection_uses_oriented_wall_axis(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    projection = engine.opening_projection(wall(), 2.0, 1.0, precision)

    assert projection.start == pytest.approx((1.5, 0.0))
    assert projection.end == pytest.approx((2.5, 0.0))


def test_stair_footprint_is_centered_on_run(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    stair = {
        "run": {"start": [0.0, 0.0], "end": [0.0, 3.0]},
        "width": 1.0,
    }

    footprint = engine.stair_footprint(stair, precision)
    x_values = [point[0] for point in footprint.exterior]

    assert min(x_values) == pytest.approx(-0.5)
    assert max(x_values) == pytest.approx(0.5)


def test_geometry_engine_does_not_mutate_json(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    model_wall = wall()
    before = copy.deepcopy(model_wall)

    engine.wall_footprint(model_wall, precision)
    engine.opening_projection(model_wall, 2.0, 1.0, precision)

    assert model_wall == before


def test_footprint_rejects_degenerate_segment(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    model_wall = wall()
    model_wall["axis"]["end"] = [0.0, 0.0]

    with pytest.raises(ValueError, match="zero-length"):
        engine.wall_footprint(model_wall, precision)


def test_wall_footprint_rejects_invalid_thickness_and_alignment(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    zero_thickness = wall()
    zero_thickness["thickness"] = 0.0
    with pytest.raises(ValueError, match="thickness"):
        engine.wall_footprint(zero_thickness, precision)

    unsupported_alignment = wall()
    unsupported_alignment["alignment"] = "diagonal"
    with pytest.raises(ValueError, match="alignment"):
        engine.wall_footprint(unsupported_alignment, precision)


def test_opening_projection_rejects_degenerate_wall_and_invalid_width(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    degenerate = wall()
    degenerate["axis"]["end"] = [0.0, 0.0]
    with pytest.raises(ValueError, match="zero-length"):
        engine.opening_projection(degenerate, 0.0, 0.5, precision)

    with pytest.raises(ValueError, match="width"):
        engine.opening_projection(wall(), 1.0, 0.0, precision)


def test_stair_footprint_rejects_invalid_width(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    stair = {
        "run": {"start": [0.0, 0.0], "end": [0.0, 3.0]},
        "width": 0.0,
    }

    with pytest.raises(ValueError, match="width"):
        engine.stair_footprint(stair, precision)


def test_out_of_range_and_overflowing_geometry_is_not_reported_as_finite(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    out_of_range = {"start": [0.0, 0.0], "end": [10**400, 0.0]}
    overflowing_length = {"start": [-1e308, 0.0], "end": [1e308, 0.0]}

    assert not engine.analyze_segment(out_of_range).has_finite_coordinates
    assert not engine.analyze_segment(overflowing_length).has_finite_coordinates


def test_polygon_with_overflowing_derived_area_is_invalid(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    extent = 1e200
    huge_room = room(
        [
            [-extent, -extent],
            [extent, -extent],
            [extent, extent],
            [-extent, extent],
            [-extent, -extent],
        ]
    )

    analysis = engine.analyze_room(huge_room, precision)

    assert not analysis.is_valid
    assert analysis.validity_reason == "Non-finite derived polygon bounds"


def test_dimensions_at_or_below_tolerance_are_rejected_by_projection(
    engine: ShapelyGeometryEngine, precision: GeometryPrecisionPolicy
) -> None:
    thin_wall = wall()
    thin_wall["thickness"] = precision.linear_tolerance
    with pytest.raises(ValueError, match="thickness"):
        engine.wall_footprint(thin_wall, precision)

    with pytest.raises(ValueError, match="width"):
        engine.opening_projection(wall(), 1.0, precision.linear_tolerance, precision)
