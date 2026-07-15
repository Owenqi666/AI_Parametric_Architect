"""Constraint-reasoning agent with an injected provider-neutral solver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ai_parametric_architect.agents.requirement_agent import AgentContractError
from ai_parametric_architect.domain.issues import ValidationIssue
from ai_parametric_architect.domain.planning_errors import PlanningContextError
from ai_parametric_architect.ports.reasoning import ConstraintSolver
from ai_parametric_architect.reasoning.constraints import (
    ConstraintResolutionPlan,
    validate_error_issue,
)

CONSTRAINT_REASONING_AGENT_NAME: Final = "constraint-reasoning-agent"
CONSTRAINT_REASONING_AGENT_VERSION: Final = "1.0.0"


@dataclass(frozen=True, slots=True)
class ConstraintReasoningAgent:
    """Convert one validation error into an immutable symbolic Plan IR."""

    _solver: ConstraintSolver[ConstraintResolutionPlan] = field(repr=False)

    @property
    def name(self) -> str:
        return CONSTRAINT_REASONING_AGENT_NAME

    @property
    def version(self) -> str:
        return CONSTRAINT_REASONING_AGENT_VERSION

    def run(self, value: ValidationIssue) -> ConstraintResolutionPlan:
        if not isinstance(value, ValidationIssue):
            raise AgentContractError(
                "Constraint reasoner input is not a ValidationIssue.",
                path="/input",
                details={
                    "agent": self.name,
                    "actual_type": type(value).__name__,
                    "expected_type": "ValidationIssue",
                },
            )
        try:
            validate_error_issue(value, path="/input")
        except PlanningContextError as error:
            details: dict[str, object] = {"agent": self.name, **error.details}
            reason = details.pop("reason", None)
            if reason == "NON_ERROR_ISSUE":
                details["actual_severity"] = details.pop("severity")
                details["expected_severity"] = "error"
            elif reason == "INVALID_SEVERITY_TYPE":
                details["expected_type"] = "Severity"
            raise AgentContractError(
                str(error),
                path=error.path,
                details=details,
            ) from error

        result = self._solver.solve(value)
        if not isinstance(result, ConstraintResolutionPlan):
            raise AgentContractError(
                "Constraint solver returned a value that is not a ConstraintResolutionPlan.",
                path="/output",
                details={
                    "agent": self.name,
                    "actual_type": type(result).__name__,
                    "expected_type": "ConstraintResolutionPlan",
                },
            )
        if (
            result.issue_code != value.code
            or result.issue_path != value.path
            or result.entity_ids != value.entity_ids
        ):
            raise AgentContractError(
                "Constraint solver output does not retain the input issue identity.",
                path="/output",
                details={"agent": self.name, "reason": "ISSUE_MISMATCH"},
            )
        return result

    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        """Implement the ConstraintSolver port for safe agent composition."""

        return self.run(issue)
