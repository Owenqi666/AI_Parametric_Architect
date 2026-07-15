"""Requirement-understanding agent with an injected parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import PlanningError

if TYPE_CHECKING:
    from ai_parametric_architect.ports.planning import RequirementParser

REQUIREMENT_AGENT_NAME: Final = "requirement-agent"
REQUIREMENT_AGENT_VERSION: Final = "1.0.0"


class AgentContractError(PlanningError):
    """Raised when an injected agent dependency violates its typed contract."""

    code = "AGENT_CONTRACT_VIOLATION"


@dataclass(frozen=True, slots=True)
class RequirementAgent:
    """Convert natural-language requirements into an immutable DesignIntent."""

    _parser: RequirementParser = field(repr=False)

    @property
    def name(self) -> str:
        return REQUIREMENT_AGENT_NAME

    @property
    def version(self) -> str:
        return REQUIREMENT_AGENT_VERSION

    def run(self, value: str) -> DesignIntent:
        result = self._parser.parse(value)
        if not isinstance(result, DesignIntent):
            raise AgentContractError(
                "Requirement parser returned a value that is not a DesignIntent.",
                path="/output",
                details={
                    "agent": self.name,
                    "actual_type": type(result).__name__,
                    "expected_type": "DesignIntent",
                },
            )
        return result

    def parse(self, requirement: str) -> DesignIntent:
        """Implement the RequirementParser port for safe agent composition."""

        return self.run(requirement)
