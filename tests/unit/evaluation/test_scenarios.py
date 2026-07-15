from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import DesignIntent, SpatialConstraint
from ai_parametric_architect.evaluation.scenarios import InvalidScenarioError, Scenario


def _intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=80,
        rooms=("living", "bedroom"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="living",
                relation="adjacent_to",
                target_room_type="bedroom",
            ),
        ),
    )


def test_scenario_is_immutable_and_round_trips_json_shape() -> None:
    intent = _intent()
    scenario = Scenario(
        input_requirement="Design an 80 m2 south-facing house.",
        expected_intent=intent,
        expected_constraints=intent.spatial_constraints,
    )

    restored = Scenario.from_dict(scenario.to_dict())

    assert restored == scenario
    assert restored.to_dict() == {
        "input_requirement": "Design an 80 m2 south-facing house.",
        "expected_intent": intent.to_dict(),
        "expected_constraints": [constraint.to_dict() for constraint in intent.spatial_constraints],
    }
    with pytest.raises(FrozenInstanceError):
        scenario.input_requirement = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "path"),
    [
        ({"input_requirement": " "}, "/input_requirement"),
        ({"expected_intent": cast(Any, object())}, "/expected_intent"),
        ({"expected_constraints": cast(Any, [])}, "/expected_constraints"),
        (
            {
                "expected_constraints": (
                    SpatialConstraint(
                        source_room_type="bedroom",
                        relation="near",
                        target_room_type="living",
                    ),
                )
            },
            "/expected_constraints",
        ),
    ],
)
def test_scenario_rejects_invalid_or_inconsistent_values(
    kwargs: dict[str, object],
    path: str,
) -> None:
    intent = _intent()
    values: dict[str, object] = {
        "input_requirement": "Design a house.",
        "expected_intent": intent,
        "expected_constraints": intent.spatial_constraints,
    }
    values.update(kwargs)

    with pytest.raises(InvalidScenarioError) as captured:
        Scenario(**cast(Any, values))

    assert captured.value.path == path


@pytest.mark.parametrize(
    ("value", "path"),
    [
        ([], "/"),
        ({}, ""),
        (
            {
                "input_requirement": 1,
                "expected_intent": {},
                "expected_constraints": [],
            },
            "/input_requirement",
        ),
        (
            {
                "input_requirement": "x",
                "expected_intent": [],
                "expected_constraints": [],
            },
            "/expected_intent",
        ),
        (
            {
                "input_requirement": "x",
                "expected_intent": _intent().to_dict(),
                "expected_constraints": "bad",
            },
            "/expected_constraints",
        ),
        (
            {
                "input_requirement": "x",
                "expected_intent": {"building_type": "house"},
                "expected_constraints": [],
            },
            "/expected_intent",
        ),
        (
            {
                "input_requirement": "x",
                "expected_intent": _intent().to_dict(),
                "expected_constraints": [1],
            },
            "/expected_constraints/0",
        ),
        (
            {
                "input_requirement": "x",
                "expected_intent": _intent().to_dict(),
                "expected_constraints": [
                    {
                        "source_room_type": "living",
                        "relation": "unsupported",
                        "target_room_type": "bedroom",
                        "required": True,
                    }
                ],
            },
            "/expected_constraints/0/relation",
        ),
    ],
)
def test_from_dict_reports_stable_paths(value: object, path: str) -> None:
    with pytest.raises(InvalidScenarioError) as captured:
        Scenario.from_dict(cast(Any, value))

    assert captured.value.path == path


@pytest.mark.parametrize(
    ("mutation", "path"),
    [
        (lambda value: value.update(expected_constraints=()), "/expected_constraints"),
        (
            lambda value: value["expected_intent"].update(area=float("nan")),
            "/expected_intent/area",
        ),
        (
            lambda value: value["expected_intent"].update(provider_object=object()),
            "/expected_intent/provider_object",
        ),
    ],
)
def test_evaluation_scenario_json_boundary_rejects_non_json_values(
    mutation: Any,
    path: str,
) -> None:
    value = Scenario(
        input_requirement="Design an 80 m2 south-facing house.",
        expected_intent=_intent(),
        expected_constraints=_intent().spatial_constraints,
    ).to_dict()
    mutation(value)

    with pytest.raises(InvalidScenarioError) as captured:
        Scenario.from_dict(cast(Any, value))

    assert captured.value.path == path
