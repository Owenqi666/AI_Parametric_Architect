from __future__ import annotations

import copy
from typing import Any

import pytest

from ai_parametric_architect.application import ModelValidationError
from ai_parametric_architect.composition import create_service


def test_valid_document_runs_from_json_to_deterministic_svg(
    valid_simple_house: dict[str, Any],
) -> None:
    service = create_service()

    report = service.validate(valid_simple_house)
    first = service.render_svg(valid_simple_house).encode("utf-8")
    second = service.render_svg(valid_simple_house).encode("utf-8")

    assert report.valid
    assert first == second
    assert b'data-model-id="mdl_simple_house"' in first


@pytest.mark.parametrize(
    ("fixture_name", "required_code"),
    [
        ("invalid_overlap", "ROOM_OVERLAP"),
        ("invalid_opening", "OPENING_OUT_OF_WALL_BOUNDS"),
    ],
)
def test_error_issue_refuses_rendering(
    request: pytest.FixtureRequest, fixture_name: str, required_code: str
) -> None:
    model = request.getfixturevalue(fixture_name)
    service = create_service()

    with pytest.raises(ModelValidationError) as captured:
        service.render_svg(model)

    assert required_code in {issue.code for issue in captured.value.report.issues}


def test_full_pipeline_is_read_only(valid_simple_house: dict[str, Any]) -> None:
    service = create_service()
    before = copy.deepcopy(valid_simple_house)

    service.validate(valid_simple_house)
    service.render_svg(valid_simple_house)

    assert valid_simple_house == before


def test_valid_stair_runs_through_validation_and_svg(
    valid_simple_house: dict[str, Any],
) -> None:
    valid_simple_house["entities"]["floors"]["flr_upper"] = {
        "id": "flr_upper",
        "entity_type": "floor",
        "name": "Upper Floor",
        "building_id": "bld_simple_house",
        "elevation": 3.0,
        "height": 2.8,
    }
    valid_simple_house["entities"]["stairs"]["str_main"] = {
        "id": "str_main",
        "entity_type": "stair",
        "name": "Main Stair",
        "from_floor_id": "flr_ground",
        "to_floor_id": "flr_upper",
        "run": {"type": "Segment2D", "start": [2.0, 1.0], "end": [2.0, 4.0]},
        "width": 1.0,
        "step_count": 16,
    }
    service = create_service()

    report = service.validate(valid_simple_house)
    svg = service.render_svg(valid_simple_house)

    assert report.valid
    assert 'data-entity-id="str_main"' in svg
