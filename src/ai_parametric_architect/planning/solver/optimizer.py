"""Bounded integer soft objectives for deterministic plan selection."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from ai_parametric_architect.domain import PlanningContextError
from ai_parametric_architect.planning.solver.constraints import ConstraintArtifacts
from ai_parametric_architect.planning.solver.models import PlanningProblem
from ai_parametric_architect.planning.solver.variables import (
    ORIENTATION_ORDER,
    RoomDecisionVariables,
)

_MAX_SAFE_OBJECTIVE = (1 << 53) - 1


@dataclass(frozen=True, slots=True)
class OptimizationArtifacts:
    primary_upper_bound: int
    tie_break_upper_bound: int
    objective_upper_bound: int


def add_objective(
    model: cp_model.CpModel,
    problem: PlanningProblem,
    rooms: tuple[RoomDecisionVariables, ...],
    constraints: ConstraintArtifacts,
) -> OptimizationArtifacts:
    weights = problem.rules.optimization
    total_area = sum(room.area for room in rooms)
    unused_area = model.new_int_var(0, problem.maximum_room_area_units, "objective_unused_area")
    model.add(unused_area == problem.maximum_room_area_units - total_area)

    min_x = model.new_int_var(0, problem.boundary.width, "objective_min_x")
    min_y = model.new_int_var(0, problem.boundary.height, "objective_min_y")
    max_x = model.new_int_var(0, problem.boundary.width, "objective_max_x")
    max_y = model.new_int_var(0, problem.boundary.height, "objective_max_y")
    model.add_min_equality(min_x, [room.x for room in rooms])
    model.add_min_equality(min_y, [room.y for room in rooms])
    model.add_max_equality(max_x, [room.end_x for room in rooms])
    model.add_max_equality(max_y, [room.end_y for room in rooms])
    compactness = (max_x - min_x) + (max_y - min_y)

    circulation_terms: list[cp_model.IntVar] = []
    for left_index, left in enumerate(rooms):
        for right_index in range(left_index + 1, len(rooms)):
            right = rooms[right_index]
            dx = model.new_int_var(
                0,
                problem.boundary.width * 2,
                f"objective_circulation_{left_index}_{right_index}_dx",
            )
            dy = model.new_int_var(
                0,
                problem.boundary.height * 2,
                f"objective_circulation_{left_index}_{right_index}_dy",
            )
            model.add_abs_equality(dx, left.center_x2 - right.center_x2)
            model.add_abs_equality(dy, left.center_y2 - right.center_y2)
            circulation_terms.extend((dx, dy))

    orientation_penalties: list[cp_model.LinearExpr] = []
    if problem.intent.orientation is not None:
        for room in rooms:
            preferred = room.orientation_literal(problem.intent.orientation)
            orientation_penalties.append(1 - preferred)
    optional_penalties = [1 - literal for literal in constraints.optional_satisfaction_literals]
    target_deviation = sum(room.target_area_deviation for room in rooms)
    circulation = sum(circulation_terms)
    orientation = sum(orientation_penalties)
    optional = sum(optional_penalties)
    primary = (
        weights.utilization * unused_area
        + weights.target_area * target_deviation
        + weights.compactness * compactness
        + weights.circulation * circulation
        + weights.orientation * orientation
        + weights.optional_constraint * optional
    )

    primary_upper_bound = (
        weights.utilization * problem.maximum_room_area_units
        + weights.target_area * problem.maximum_room_area_units * len(rooms)
        + weights.compactness * (problem.boundary.width + problem.boundary.height)
        + weights.circulation
        * len(rooms)
        * (len(rooms) - 1)
        * (problem.boundary.width + problem.boundary.height)
        + weights.orientation * len(rooms)
        + weights.optional_constraint * len(constraints.optional_satisfaction_literals)
    )

    position_scale = problem.boundary.height + 1
    orientation_scale = len(ORIENTATION_ORDER)
    tie_terms: list[cp_model.LinearExpr] = []
    tie_upper_bound = 0
    for index, room in enumerate(rooms, start=1):
        orientation_code = sum(
            code * literal for code, literal in enumerate(room.orientation_literals)
        )
        room_tie = (
            (room.x * position_scale + room.y) * orientation_scale
            + orientation_code
            + room.width
            + room.height
        )
        tie_terms.append(index * room_tie)
        tie_upper_bound += index * (
            (problem.boundary.width * position_scale + problem.boundary.height) * orientation_scale
            + len(ORIENTATION_ORDER)
            + problem.boundary.width
            + problem.boundary.height
        )
    objective_upper_bound = primary_upper_bound * (tie_upper_bound + 1) + tie_upper_bound
    if objective_upper_bound > _MAX_SAFE_OBJECTIVE:
        raise PlanningContextError(
            "Planning objective exceeds the safe CP-SAT integer range.",
            path="/rules/optimization",
            details={"objective_upper_bound": objective_upper_bound},
        )
    model.minimize(primary * (tie_upper_bound + 1) + sum(tie_terms))
    return OptimizationArtifacts(
        primary_upper_bound=primary_upper_bound,
        tie_break_upper_bound=tie_upper_bound,
        objective_upper_bound=objective_upper_bound,
    )


__all__ = ["OptimizationArtifacts", "add_objective"]
