"""Deterministic architecture intent parsing and proposal planning."""

from typing import TYPE_CHECKING

from ai_parametric_architect.planning.adapter_parser import LanguageModelRequirementParser
from ai_parametric_architect.planning.agent_pipeline import AgentPlanningPipeline
from ai_parametric_architect.planning.models import (
    FLOOR_PLAN_SCHEMA_VERSION,
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanBoundary,
    FloorPlanConstraint,
    FloorPlanProposal,
    FloorPlanRoom,
)
from ai_parametric_architect.planning.rule_parser import RuleBasedRequirementParser
from ai_parametric_architect.planning.rule_planner import (
    RULE_BASED_PLANNER_PROVENANCE,
    RULE_BASED_PLANNER_RATIONALE,
    RuleBasedPlanner,
)
from ai_parametric_architect.planning.rules import (
    EQUAL_AREA_STABLE_ORDER_STRATEGY,
    RuleBasedFloorPlanPlanner,
)

if TYPE_CHECKING:
    from ai_parametric_architect.planning.solver import (
        CP_SAT_STRATEGY,
        ConstraintFloorPlanPlanner,
        CpSatFloorPlanSolver,
        OptimizationWeights,
        PlanningGridPolicy,
        PlanningProblem,
        PlanningRules,
    )

_SOLVER_EXPORTS = frozenset(
    {
        "CP_SAT_STRATEGY",
        "ConstraintFloorPlanPlanner",
        "CpSatFloorPlanSolver",
        "OptimizationWeights",
        "PlanningGridPolicy",
        "PlanningProblem",
        "PlanningRules",
    }
)


def __getattr__(name: str) -> object:
    """Load the native solver only when a solver-specific public value is requested."""

    if name not in _SOLVER_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from ai_parametric_architect.planning import solver

    value = getattr(solver, name)
    globals()[name] = value
    return value


__all__ = [
    "CP_SAT_STRATEGY",
    "EQUAL_AREA_STABLE_ORDER_STRATEGY",
    "FLOOR_PLAN_SCHEMA_VERSION",
    "RULE_BASED_PLANNER_PROVENANCE",
    "RULE_BASED_PLANNER_RATIONALE",
    "SOLVED_FLOOR_PLAN_SCHEMA_VERSION",
    "AgentPlanningPipeline",
    "ConstraintFloorPlanPlanner",
    "CpSatFloorPlanSolver",
    "FloorPlanBoundary",
    "FloorPlanConstraint",
    "FloorPlanProposal",
    "FloorPlanRoom",
    "LanguageModelRequirementParser",
    "OptimizationWeights",
    "PlanningGridPolicy",
    "PlanningProblem",
    "PlanningRules",
    "RuleBasedFloorPlanPlanner",
    "RuleBasedPlanner",
    "RuleBasedRequirementParser",
]
