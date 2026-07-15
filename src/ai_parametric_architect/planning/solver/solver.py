"""Deterministic OR-Tools CP-SAT floor-plan solver and planner adapter."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ai_parametric_architect.domain import DesignIntent, PlanningContextError, PlanningSolverError
from ai_parametric_architect.planning.models import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanBoundary,
    FloorPlanConstraint,
    FloorPlanProposal,
    FloorPlanRoom,
)
from ai_parametric_architect.planning.solver.constraints import apply_constraints
from ai_parametric_architect.planning.solver.models import (
    CP_SAT_STRATEGY,
    PlanningProblem,
    PlanningRules,
    SolvedRoom,
    SolverSolution,
)
from ai_parametric_architect.planning.solver.optimizer import add_objective
from ai_parametric_architect.planning.solver.variables import (
    ORIENTATION_ORDER,
    create_room_variables,
)


@dataclass(frozen=True, slots=True)
class CpSatFloorPlanSolver:
    """Solve one detached planning problem without accessing world state."""

    def solve(self, problem: PlanningProblem) -> SolverSolution:
        if not isinstance(problem, PlanningProblem):
            raise PlanningSolverError(
                "CP-SAT solver input must be a PlanningProblem.",
                path="/problem",
                details={"reason": "INVALID_PROBLEM_TYPE"},
            )
        try:
            canonical_problem = PlanningProblem.from_intent(problem.intent, problem.rules)
        except PlanningContextError as error:
            raise PlanningSolverError(
                "CP-SAT solver input is not a canonical planning problem.",
                path="/problem",
                details={"reason": "INVALID_PROBLEM"},
            ) from error
        if problem != canonical_problem:
            raise PlanningSolverError(
                "CP-SAT solver input is not a canonical planning problem.",
                path="/problem",
                details={"reason": "NON_CANONICAL_PROBLEM"},
            )
        problem = canonical_problem
        model = cp_model.CpModel()
        variables = create_room_variables(model, problem)
        constraint_artifacts = apply_constraints(model, problem, variables)
        add_objective(model, problem, variables, constraint_artifacts)
        validation_error = model.validate()
        if validation_error:
            raise PlanningSolverError(
                "CP-SAT planning model is invalid.",
                path="/problem",
                details={"reason": "MODEL_INVALID", "solver_message": validation_error},
            )

        solver = cp_model.CpSolver()
        _configure_solver(solver, problem.rules)
        status = solver.solve(model)
        if status != cp_model.OPTIMAL:
            reason = {
                cp_model.INFEASIBLE: "INFEASIBLE",
                cp_model.MODEL_INVALID: "MODEL_INVALID",
                cp_model.FEASIBLE: "OPTIMALITY_NOT_PROVEN",
                cp_model.UNKNOWN: "SOLVER_BUDGET_EXHAUSTED",
            }.get(status, "UNSUPPORTED_SOLVER_STATUS")
            raise PlanningSolverError(
                "CP-SAT could not produce a deterministic optimal proposal.",
                path="/problem",
                details={
                    "reason": reason,
                    "status": solver.status_name(status),
                },
            )

        solved_rooms = tuple(
            SolvedRoom(
                specification=room.specification,
                x=solver.value(room.x),
                y=solver.value(room.y),
                width=solver.value(room.width),
                height=solver.value(room.height),
                orientation=next(
                    orientation
                    for orientation, literal in zip(
                        ORIENTATION_ORDER, room.orientation_literals, strict=True
                    )
                    if solver.boolean_value(literal)
                ),
            )
            for room in variables
        )
        objective_value = _exact_objective_value(solver.objective_value, "objective")
        best_bound = _exact_objective_value(solver.best_objective_bound, "best_bound")
        return SolverSolution(
            rooms=solved_rooms,
            objective_value=objective_value,
            best_objective_bound=best_bound,
        )


@dataclass(frozen=True, slots=True)
class ConstraintFloorPlanPlanner:
    """Implement the existing FloorPlanPlanner port with CP-SAT."""

    rules: PlanningRules = field(default_factory=PlanningRules)
    solver: CpSatFloorPlanSolver = field(default_factory=CpSatFloorPlanSolver, repr=False)

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        problem = PlanningProblem.from_intent(intent, self.rules)
        solution = self.solver.solve(problem)
        grid = problem.rules.grid
        rooms = tuple(
            FloorPlanRoom(
                plan_id=solved.specification.plan_id,
                room_type=solved.specification.room_type,
                target_area=solved.specification.target_area,
                x=grid.length_from_units(solved.x),
                y=grid.length_from_units(solved.y),
                width=grid.length_from_units(solved.width),
                height=grid.length_from_units(solved.height),
                orientation=solved.orientation,
            )
            for solved in solution.rooms
        )
        constraints = tuple(
            FloorPlanConstraint(
                source_plan_id=problem.rooms[bound.source_index].plan_id,
                relation=bound.constraint.relation,
                target_plan_id=problem.rooms[bound.target_index].plan_id,
                required=bound.constraint.required,
            )
            for bound in problem.bound_constraints
        )
        return FloorPlanProposal(
            intent=intent,
            rooms=rooms,
            spatial_constraints=constraints,
            orientation=intent.orientation,
            strategy=CP_SAT_STRATEGY,
            schema_version=SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
            boundary=FloorPlanBoundary(
                width=grid.length_from_units(problem.boundary.width),
                height=grid.length_from_units(problem.boundary.height),
            ),
        )


def _configure_solver(solver: cp_model.CpSolver, rules: PlanningRules) -> None:
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = rules.random_seed
    solver.parameters.permute_variable_randomly = False
    solver.parameters.permute_presolve_constraint_order = False
    solver.parameters.max_deterministic_time = rules.max_deterministic_time


def _exact_objective_value(value: float, field_name: str) -> int:
    if not math.isfinite(value) or not value.is_integer():
        raise PlanningSolverError(
            "CP-SAT returned a non-finite or non-integral objective.",
            path="/problem",
            details={"reason": "INVALID_SOLVER_RESULT", "field": field_name},
        )
    return int(value)


__all__ = ["ConstraintFloorPlanPlanner", "CpSatFloorPlanSolver"]
