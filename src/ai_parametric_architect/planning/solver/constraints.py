"""Hard and reified spatial constraints for the CP-SAT model."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from ai_parametric_architect.domain import SpatialRelation
from ai_parametric_architect.planning.solver.models import PlanningProblem
from ai_parametric_architect.planning.solver.variables import RoomDecisionVariables


@dataclass(frozen=True, slots=True)
class ConstraintArtifacts:
    optional_satisfaction_literals: tuple[cp_model.IntVar, ...]


def apply_constraints(
    model: cp_model.CpModel,
    problem: PlanningProblem,
    rooms: tuple[RoomDecisionVariables, ...],
) -> ConstraintArtifacts:
    """Apply all hard constraints and expose optional-relation satisfaction literals."""

    model.add_no_overlap_2d(
        [room.x_interval for room in rooms],
        [room.y_interval for room in rooms],
    )
    model.add(sum(room.area for room in rooms) <= problem.maximum_room_area_units)
    _add_stable_same_type_order(model, rooms, problem.boundary.height)

    optional_literals: list[cp_model.IntVar] = []
    for index, bound in enumerate(problem.bound_constraints):
        source = rooms[bound.source_index]
        target = rooms[bound.target_index]
        activation: cp_model.IntVar | None = None
        if not bound.constraint.required:
            activation = model.new_bool_var(f"optional_constraint_{index}_satisfied")
            optional_literals.append(activation)
        _apply_relation(
            model,
            problem,
            source,
            target,
            bound.constraint.relation,
            index,
            activation,
        )
    return ConstraintArtifacts(optional_satisfaction_literals=tuple(optional_literals))


def _apply_relation(
    model: cp_model.CpModel,
    problem: PlanningProblem,
    source: RoomDecisionVariables,
    target: RoomDecisionVariables,
    relation: SpatialRelation,
    constraint_index: int,
    activation: cp_model.IntVar | None,
) -> None:
    if relation is SpatialRelation.ADJACENT_TO:
        contact = problem.rules.grid.exact_length_units(
            problem.rules.minimum_adjacency_contact,
            path="/rules/minimum_adjacency_contact",
        )
        _add_adjacency(model, source, target, contact, constraint_index, activation)
        return
    if relation is SpatialRelation.SEPARATED_FROM:
        gap = problem.rules.grid.exact_length_units(
            problem.rules.separation_gap, path="/rules/separation_gap"
        )
        _add_separation(model, source, target, gap, constraint_index, activation)
        return
    if relation is SpatialRelation.NEAR:
        maximum_distance = (
            problem.rules.grid.exact_length_units(
                problem.rules.near_distance, path="/rules/near_distance"
            )
            * 2
        )
        delta_x = model.new_int_var(
            0, problem.boundary.width * 2, f"constraint_{constraint_index}_near_dx"
        )
        delta_y = model.new_int_var(
            0, problem.boundary.height * 2, f"constraint_{constraint_index}_near_dy"
        )
        model.add_abs_equality(delta_x, source.center_x2 - target.center_x2)
        model.add_abs_equality(delta_y, source.center_y2 - target.center_y2)
        _conditionally_add(model.add(delta_x + delta_y <= maximum_distance), activation)
        return
    relation_constraint = {
        SpatialRelation.NORTH_OF: source.y >= target.end_y,
        SpatialRelation.SOUTH_OF: source.end_y <= target.y,
        SpatialRelation.EAST_OF: source.x >= target.end_x,
        SpatialRelation.WEST_OF: source.end_x <= target.x,
    }[relation]
    _conditionally_add(model.add(relation_constraint), activation)


def _add_adjacency(
    model: cp_model.CpModel,
    source: RoomDecisionVariables,
    target: RoomDecisionVariables,
    contact: int,
    constraint_index: int,
    activation: cp_model.IntVar | None,
) -> None:
    directions = tuple(
        model.new_bool_var(f"constraint_{constraint_index}_adjacent_{name}")
        for name in ("left", "right", "above", "below")
    )
    relations = (
        (
            source.end_x == target.x,
            source.y + contact <= target.end_y,
            target.y + contact <= source.end_y,
        ),
        (
            target.end_x == source.x,
            source.y + contact <= target.end_y,
            target.y + contact <= source.end_y,
        ),
        (
            source.end_y == target.y,
            source.x + contact <= target.end_x,
            target.x + contact <= source.end_x,
        ),
        (
            target.end_y == source.y,
            source.x + contact <= target.end_x,
            target.x + contact <= source.end_x,
        ),
    )
    for literal, conditions in zip(directions, relations, strict=True):
        for condition in conditions:
            model.add(condition).only_enforce_if(literal)
        if activation is not None:
            model.add_implication(literal, activation)
    clause = model.add_bool_or(directions)
    _conditionally_add(clause, activation)


def _add_separation(
    model: cp_model.CpModel,
    source: RoomDecisionVariables,
    target: RoomDecisionVariables,
    gap: int,
    constraint_index: int,
    activation: cp_model.IntVar | None,
) -> None:
    directions = tuple(
        model.new_bool_var(f"constraint_{constraint_index}_separated_{name}")
        for name in ("left", "right", "above", "below")
    )
    conditions = (
        source.end_x + gap <= target.x,
        target.end_x + gap <= source.x,
        source.end_y + gap <= target.y,
        target.end_y + gap <= source.y,
    )
    for literal, condition in zip(directions, conditions, strict=True):
        model.add(condition).only_enforce_if(literal)
        if activation is not None:
            model.add_implication(literal, activation)
    clause = model.add_bool_or(directions)
    _conditionally_add(clause, activation)


def _conditionally_add(constraint: cp_model.Constraint, activation: cp_model.IntVar | None) -> None:
    if activation is not None:
        constraint.only_enforce_if(activation)


def _add_stable_same_type_order(
    model: cp_model.CpModel,
    rooms: tuple[RoomDecisionVariables, ...],
    boundary_height: int,
) -> None:
    previous_by_type: dict[str, RoomDecisionVariables] = {}
    position_scale = boundary_height + 1
    for room in rooms:
        previous = previous_by_type.get(room.specification.room_type)
        if previous is not None:
            model.add(previous.x * position_scale + previous.y < room.x * position_scale + room.y)
        previous_by_type[room.specification.room_type] = room


__all__ = ["ConstraintArtifacts", "apply_constraints"]
