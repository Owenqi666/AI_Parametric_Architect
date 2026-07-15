from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    PlanningSolverError,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.planning.models import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanProposal,
    FloorPlanRoom,
)
from ai_parametric_architect.planning.solver import (
    CP_SAT_STRATEGY,
    ConstraintFloorPlanPlanner,
    CpSatFloorPlanSolver,
    GridBoundary,
    OptimizationWeights,
    PlanningProblem,
    PlanningRules,
)


def _intent(
    *,
    area: float = 60.0,
    rooms: tuple[str, ...] = ("living", "kitchen", "bedroom", "bathroom"),
    orientation: str | None = None,
    constraints: tuple[SpatialConstraint, ...] = (),
) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=area,
        rooms=rooms,
        orientation=orientation,
        spatial_constraints=constraints,
    )


def _rect(room: FloorPlanRoom) -> tuple[float, float, float, float]:
    assert room.x is not None
    assert room.y is not None
    assert room.width is not None
    assert room.height is not None
    return room.x, room.y, room.width, room.height


def _room(proposal: FloorPlanProposal, room_type: str) -> FloorPlanRoom:
    return next(room for room in proposal.rooms if room.room_type == room_type)


def _overlap(left: FloorPlanRoom, right: FloorPlanRoom) -> bool:
    left_x, left_y, left_width, left_height = _rect(left)
    right_x, right_y, right_width, right_height = _rect(right)
    return (
        left_x < right_x + right_width
        and right_x < left_x + left_width
        and left_y < right_y + right_height
        and right_y < left_y + left_height
    )


def _adjacency_contact(left: FloorPlanRoom, right: FloorPlanRoom) -> float:
    left_x, left_y, left_width, left_height = _rect(left)
    right_x, right_y, right_width, right_height = _rect(right)
    if left_x + left_width == right_x or right_x + right_width == left_x:
        return max(
            0.0,
            min(left_y + left_height, right_y + right_height) - max(left_y, right_y),
        )
    if left_y + left_height == right_y or right_y + right_height == left_y:
        return max(
            0.0,
            min(left_x + left_width, right_x + right_width) - max(left_x, right_x),
        )
    return 0.0


def _is_separated(left: FloorPlanRoom, right: FloorPlanRoom, gap: float) -> bool:
    left_x, left_y, left_width, left_height = _rect(left)
    right_x, right_y, right_width, right_height = _rect(right)
    return (
        left_x + left_width + gap <= right_x
        or right_x + right_width + gap <= left_x
        or left_y + left_height + gap <= right_y
        or right_y + right_height + gap <= left_y
    )


def _canonical_bytes(proposal: FloorPlanProposal) -> bytes:
    return json.dumps(
        proposal.to_dict(),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_solver_returns_a_strict_v2_detached_proposal() -> None:
    intent = _intent(orientation="south")

    proposal = ConstraintFloorPlanPlanner().plan(intent)

    assert proposal.intent is intent
    assert proposal.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
    assert proposal.strategy == CP_SAT_STRATEGY
    assert proposal.boundary is not None
    assert all(room.is_placed for room in proposal.rooms)
    assert [room.plan_id for room in proposal.rooms] == [
        "plan_room_001",
        "plan_room_002",
        "plan_room_003",
        "plan_room_004",
    ]
    assert FloorPlanProposal.from_dict(proposal.to_dict()) == proposal


def test_solver_output_obeys_minimum_area_boundary_grid_and_no_overlap() -> None:
    rules = PlanningRules()
    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(_intent())
    assert proposal.boundary is not None

    actual_total = 0.0
    for index, room in enumerate(proposal.rooms):
        x, y, width, height = _rect(room)
        area = width * height
        actual_total += area
        assert area >= rules.minimum_area_for(room.room_type)
        assert 0.0 <= x <= proposal.boundary.width - width
        assert 0.0 <= y <= proposal.boundary.height - height
        assert all(math.isfinite(value) for value in (x, y, width, height, area))
        assert all(
            (value * rules.grid.units_per_metre).is_integer() for value in (x, y, width, height)
        )
        for other in proposal.rooms[index + 1 :]:
            assert not _overlap(room, other)
    assert actual_total <= proposal.intent.area


def test_required_adjacency_has_the_configured_shared_edge_contact() -> None:
    rules = PlanningRules(minimum_adjacency_contact=1.5)
    intent = _intent(
        area=40.0,
        rooms=("living", "kitchen"),
        constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="living",
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert _adjacency_contact(_room(proposal, "kitchen"), _room(proposal, "living")) >= 1.5
    assert proposal.spatial_constraints[0].required is True


def test_required_separation_has_the_configured_clearance() -> None:
    rules = PlanningRules(separation_gap=1.0)
    intent = _intent(
        area=40.0,
        rooms=("bedroom", "bathroom"),
        constraints=(
            SpatialConstraint(
                source_room_type="bathroom",
                relation=SpatialRelation.SEPARATED_FROM,
                target_room_type="bedroom",
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert _is_separated(_room(proposal, "bathroom"), _room(proposal, "bedroom"), gap=1.0)


@pytest.mark.parametrize(
    "relation",
    [
        SpatialRelation.NORTH_OF,
        SpatialRelation.SOUTH_OF,
        SpatialRelation.EAST_OF,
        SpatialRelation.WEST_OF,
    ],
)
def test_required_cardinal_relation_is_enforced(relation: SpatialRelation) -> None:
    intent = _intent(
        area=40.0,
        rooms=("bedroom", "bathroom"),
        constraints=(
            SpatialConstraint(
                source_room_type="bedroom",
                relation=relation,
                target_room_type="bathroom",
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner().plan(intent)
    source_x, source_y, source_width, source_height = _rect(_room(proposal, "bedroom"))
    target_x, target_y, target_width, target_height = _rect(_room(proposal, "bathroom"))

    if relation is SpatialRelation.NORTH_OF:
        assert source_y >= target_y + target_height
    elif relation is SpatialRelation.SOUTH_OF:
        assert source_y + source_height <= target_y
    elif relation is SpatialRelation.EAST_OF:
        assert source_x >= target_x + target_width
    else:
        assert source_x + source_width <= target_x


def test_required_near_relation_bounds_manhattan_center_distance() -> None:
    rules = PlanningRules(near_distance=3.0)
    intent = _intent(
        area=40.0,
        rooms=("bedroom", "bathroom"),
        constraints=(
            SpatialConstraint(
                source_room_type="bedroom",
                relation=SpatialRelation.NEAR,
                target_room_type="bathroom",
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)
    source_x, source_y, source_width, source_height = _rect(_room(proposal, "bedroom"))
    target_x, target_y, target_width, target_height = _rect(_room(proposal, "bathroom"))
    distance = abs(source_x + source_width / 2 - target_x - target_width / 2) + abs(
        source_y + source_height / 2 - target_y - target_height / 2
    )

    assert distance <= rules.near_distance


def test_room_orientation_matches_its_boundary_exposure() -> None:
    proposal = ConstraintFloorPlanPlanner().plan(_intent())
    assert proposal.boundary is not None

    for room in proposal.rooms:
        x, y, width, height = _rect(room)
        exposures = {
            "north": y + height == proposal.boundary.height,
            "east": x + width == proposal.boundary.width,
            "south": y == 0.0,
            "west": x == 0.0,
            "interior": (
                x > 0.0
                and y > 0.0
                and x + width < proposal.boundary.width
                and y + height < proposal.boundary.height
            ),
        }
        assert room.orientation is not None
        assert exposures[room.orientation]


def test_orientation_soft_objective_selects_a_feasible_preferred_exposure() -> None:
    rules = PlanningRules(
        boundary_width=5.0,
        boundary_height=4.0,
        optimization=OptimizationWeights(
            utilization=0,
            target_area=0,
            compactness=0,
            circulation=0,
            orientation=1,
            optional_constraint=0,
        ),
    )
    intent = _intent(
        area=20.0,
        rooms=("living",),
        orientation="north",
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert proposal.rooms[0].orientation == "north"


def test_feasible_optional_adjacency_is_selected_by_soft_objective() -> None:
    rules = PlanningRules(
        optimization=OptimizationWeights(
            utilization=0,
            target_area=0,
            compactness=0,
            circulation=0,
            orientation=0,
            optional_constraint=1,
        )
    )
    intent = _intent(
        area=40.0,
        rooms=("living", "kitchen"),
        constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="living",
                required=False,
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert _adjacency_contact(_room(proposal, "kitchen"), _room(proposal, "living")) >= 1.0
    assert proposal.spatial_constraints[0].required is False


def test_impossible_optional_constraint_does_not_make_problem_infeasible() -> None:
    rules = PlanningRules(boundary_width=4.0, boundary_height=4.0)
    intent = _intent(
        area=16.0,
        rooms=("study", "office"),
        constraints=(
            SpatialConstraint(
                source_room_type="study",
                relation=SpatialRelation.SEPARATED_FROM,
                target_room_type="office",
                required=False,
            ),
        ),
    )

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert proposal.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
    assert not _is_separated(_room(proposal, "study"), _room(proposal, "office"), gap=1.0)


def test_infeasible_hard_constraints_raise_stable_structured_solver_error() -> None:
    rules = PlanningRules(boundary_width=4.0, boundary_height=4.0)
    intent = _intent(
        area=16.0,
        rooms=("study", "office"),
        constraints=(
            SpatialConstraint(
                source_room_type="study",
                relation=SpatialRelation.SEPARATED_FROM,
                target_room_type="office",
            ),
        ),
    )

    with pytest.raises(PlanningSolverError) as captured:
        ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert captured.value.to_dict() == {
        "code": "PLANNING_SOLVER_FAILED",
        "path": "/problem",
        "message": "CP-SAT could not produce a deterministic optimal proposal.",
        "details": {"reason": "INFEASIBLE", "status": "INFEASIBLE"},
    }


def test_solver_rejects_a_forged_noncanonical_problem_before_model_construction() -> None:
    problem = PlanningProblem.from_intent(_intent())
    forged = replace(
        problem,
        boundary=GridBoundary(problem.boundary.width + 1, problem.boundary.height),
    )

    with pytest.raises(PlanningSolverError) as captured:
        CpSatFloorPlanSolver().solve(forged)

    assert captured.value.details == {"reason": "NON_CANONICAL_PROBLEM"}


def test_repeat_runs_are_canonical_byte_deterministic() -> None:
    intent = _intent(
        area=40.0,
        rooms=("living", "kitchen"),
        orientation="south",
        constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="living",
            ),
        ),
    )
    planner = ConstraintFloorPlanPlanner()

    results = tuple(_canonical_bytes(planner.plan(intent)) for _ in range(4))

    assert len(set(results)) == 1


def test_solver_does_not_mutate_design_intent_or_rules() -> None:
    intent = _intent(orientation="south")
    rules = PlanningRules()
    before = intent.to_dict()

    proposal = ConstraintFloorPlanPlanner(rules=rules).plan(intent)

    assert proposal.intent is intent
    assert intent.to_dict() == before
    assert rules == PlanningRules()
