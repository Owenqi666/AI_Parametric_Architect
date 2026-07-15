"""Stable errors for deterministic architecture planning."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from ai_parametric_architect.domain.json_values import ensure_json_value


class PlanningError(RuntimeError):
    code = "PLANNING_ERROR"

    def __init__(
        self,
        message: str,
        *,
        path: str = "",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        copied_details = {} if details is None else dict(details)
        ensure_json_value(copied_details)
        self.path = path
        self.details = deepcopy(copied_details)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "path": self.path,
            "message": str(self),
            "details": deepcopy(self.details),
        }


class InvalidDesignIntentError(PlanningError):
    code = "INVALID_DESIGN_INTENT"


class RequirementParseError(PlanningError):
    code = "REQUIREMENT_PARSE_FAILED"


class PlanningContextError(PlanningError):
    code = "PLANNING_CONTEXT_INVALID"


class PlanningCapacityError(PlanningError):
    code = "PLANNING_CAPACITY_INSUFFICIENT"


class PlanningPolicyError(PlanningError):
    code = "PLANNING_POLICY_VIOLATION"


class PlannerContractError(PlanningError):
    code = "PLANNER_CONTRACT_VIOLATION"


class PlanningSolverError(PlanningError):
    code = "PLANNING_SOLVER_FAILED"
