from __future__ import annotations

from typing import Any

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningContextError,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.planning.solver import (
    GridBoundary,
    OptimizationWeights,
    PlanningGridPolicy,
    PlanningProblem,
    PlanningRules,
)


def _intent(
    *,
    area: float = 60.0,
    rooms: tuple[str, ...] = ("living", "kitchen", "bedroom", "bathroom"),
    constraints: tuple[SpatialConstraint, ...] = (),
) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=area,
        rooms=rooms,
        spatial_constraints=constraints,
    )


def test_grid_policy_is_the_single_exact_length_and_conservative_area_scale() -> None:
    grid = PlanningGridPolicy(units_per_metre=2)

    assert grid.area_units_per_square_metre == 4
    assert grid.exact_length_units(0.5, path="/length") == 1
    assert grid.exact_length_units(2.5, path="/length") == 5
    assert grid.minimum_area_units(1.1, path="/area") == 5
    assert grid.maximum_area_units(1.1, path="/area") == 4
    assert grid.length_from_units(5) == 2.5


def test_grid_policy_rejects_lengths_that_cannot_be_represented_exactly() -> None:
    grid = PlanningGridPolicy(units_per_metre=2)

    with pytest.raises(PlanningContextError) as captured:
        grid.exact_length_units(1.25, path="/custom/length")

    assert captured.value.code == "PLANNING_CONTEXT_INVALID"
    assert captured.value.path == "/custom/length"
    assert captured.value.details == {"units_per_metre": 2}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_grid_policy_rejects_non_finite_values(value: float) -> None:
    grid = PlanningGridPolicy()

    with pytest.raises(PlanningContextError) as captured:
        grid.minimum_area_units(value, path="/area")

    assert captured.value.path == "/area"


def test_grid_policy_rejects_boolean_and_out_of_budget_scales() -> None:
    with pytest.raises(PlanningContextError, match="integer from 1 to 100"):
        PlanningGridPolicy(units_per_metre=True)
    with pytest.raises(PlanningContextError, match="integer from 1 to 100"):
        PlanningGridPolicy(units_per_metre=101)


def test_planning_rules_require_complete_grid_aligned_explicit_boundary() -> None:
    with pytest.raises(PlanningContextError) as partial:
        PlanningRules(boundary_width=8.0)
    with pytest.raises(PlanningContextError) as off_grid:
        PlanningRules(boundary_width=8.25, boundary_height=6.0)

    assert partial.value.path == "/rules/boundary_width"
    assert off_grid.value.path == "/rules/boundary_width"


def test_planning_rules_reject_unsafe_budgets_and_duplicate_minimums() -> None:
    with pytest.raises(PlanningContextError) as room_budget:
        PlanningRules(max_rooms=65)
    with pytest.raises(PlanningContextError) as duplicate:
        PlanningRules(minimum_room_areas=(("living", 18.0), ("living", 20.0)))

    assert room_budget.value.path == "/rules"
    assert duplicate.value.path == "/rules/minimum_room_areas/1"


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"target_utilization_denominator": 10_001}, "/rules/target_utilization_denominator"),
        ({"boundary_aspect_numerator": 10_001}, "/rules/boundary_aspect_numerator"),
        ({"max_deterministic_time": 60.5}, "/rules/max_deterministic_time"),
        ({"max_area": 1_000_001.0}, "/rules/max_area"),
        ({"max_coordinate": 10_000.5}, "/rules/max_coordinate"),
        ({"separation_gap": 0.25}, "/rules/separation_gap"),
        ({"minimum_room_areas": (("Living", 18.0),)}, "/rules/minimum_room_areas/0"),
    ],
)
def test_planning_rules_reject_unbounded_or_noncanonical_values(
    overrides: dict[str, Any], path: str
) -> None:
    with pytest.raises(PlanningContextError) as captured:
        PlanningRules(**overrides)

    assert captured.value.path == path


def test_optimization_policy_rejects_an_objective_with_no_signal() -> None:
    with pytest.raises(PlanningContextError) as captured:
        OptimizationWeights(
            utilization=0,
            target_area=0,
            compactness=0,
            circulation=0,
            orientation=0,
            optional_constraint=0,
        )

    assert captured.value.path == "/rules/optimization"


def test_problem_derivation_is_stable_and_binds_first_room_of_each_type() -> None:
    intent = _intent(
        rooms=("living", "bedroom", "bedroom", "kitchen"),
        constraints=(
            SpatialConstraint(
                source_room_type="bedroom",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="kitchen",
            ),
        ),
    )

    problem = PlanningProblem.from_intent(intent)

    assert problem.intent is intent
    assert problem.rules == PlanningRules()
    assert problem.boundary == GridBoundary(width=19, height=15)
    assert problem.maximum_room_area_units == 240
    assert [room.plan_id for room in problem.rooms] == [
        "plan_room_001",
        "plan_room_002",
        "plan_room_003",
        "plan_room_004",
    ]
    assert [room.room_type for room in problem.rooms] == list(intent.rooms)
    assert problem.bound_constraints[0].source_index == 1
    assert problem.bound_constraints[0].target_index == 3


def test_problem_respects_explicit_boundary_and_grid_units() -> None:
    rules = PlanningRules(boundary_width=8.0, boundary_height=6.0)

    problem = PlanningProblem.from_intent(_intent(area=40.0, rooms=("living", "kitchen")), rules)

    assert problem.boundary == GridBoundary(width=16, height=12)
    assert problem.boundary.area == 192
    assert problem.maximum_room_area_units == 160


def test_problem_rejects_room_budget_before_solver_allocation() -> None:
    rules = PlanningRules(max_rooms=2)

    with pytest.raises(PlanningContextError) as captured:
        PlanningProblem.from_intent(
            _intent(area=40.0, rooms=("living", "kitchen", "bathroom")), rules
        )

    assert captured.value.path == "/intent/rooms"
    assert captured.value.details == {"maximum": 2, "actual": 3}


def test_problem_rejects_constraint_budget_before_solver_allocation() -> None:
    constraints = (
        SpatialConstraint(
            source_room_type="living",
            relation=SpatialRelation.ADJACENT_TO,
            target_room_type="kitchen",
        ),
        SpatialConstraint(
            source_room_type="bedroom",
            relation=SpatialRelation.NEAR,
            target_room_type="living",
        ),
    )
    rules = PlanningRules(max_constraints=1)

    with pytest.raises(PlanningContextError) as captured:
        PlanningProblem.from_intent(_intent(constraints=constraints), rules)

    assert captured.value.path == "/intent/spatial_constraints"
    assert captured.value.details == {"maximum": 1, "actual": 2}


def test_problem_rejects_area_budget_before_model_construction() -> None:
    rules = PlanningRules(max_area=59.0)

    with pytest.raises(PlanningContextError) as captured:
        PlanningProblem.from_intent(_intent(area=60.0), rules)

    assert captured.value.path == "/intent/area"
    assert captured.value.details == {"maximum": 59.0, "actual": 60.0}


def test_problem_rejects_minimum_room_area_infeasibility_structurally() -> None:
    intent = _intent(area=20.0, rooms=("living", "bedroom"))

    with pytest.raises(PlanningContextError) as captured:
        PlanningProblem.from_intent(intent)

    assert captured.value.path == "/intent/area"
    assert captured.value.details == {
        "reason": "MINIMUM_ROOM_AREA_INFEASIBLE",
        "available_area_units": 80,
        "required_area_units": 112,
    }


def test_problem_rejects_boundary_smaller_than_requested_area() -> None:
    rules = PlanningRules(boundary_width=4.0, boundary_height=4.0)

    with pytest.raises(PlanningContextError) as captured:
        PlanningProblem.from_intent(_intent(area=20.0, rooms=("living",)), rules)

    assert captured.value.path == "/rules/boundary_width"
    assert captured.value.details == {
        "boundary_area_units": 64,
        "intent_area_units": 80,
    }


def test_problem_derivation_does_not_mutate_intent_or_rules() -> None:
    intent = _intent()
    rules = PlanningRules()
    intent_before = intent.to_dict()

    problem = PlanningProblem.from_intent(intent, rules)

    assert problem.intent is intent
    assert problem.rules is rules
    assert intent.to_dict() == intent_before
    assert rules == PlanningRules()
