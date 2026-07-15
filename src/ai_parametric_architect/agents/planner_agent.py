"""Architecture planning agent with an injected deterministic planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ai_parametric_architect.agents.requirement_agent import AgentContractError
from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.ports.planning import FloorPlanPlanner

ARCHITECTURE_PLANNER_AGENT_NAME: Final = "architecture-planner-agent"
ARCHITECTURE_PLANNER_AGENT_VERSION: Final = "2.0.0"


@dataclass(frozen=True, slots=True)
class ArchitecturePlannerAgent:
    """Convert one immutable DesignIntent into a detached spatial proposal."""

    _planner: FloorPlanPlanner[FloorPlanProposal] = field(repr=False)

    @property
    def name(self) -> str:
        return ARCHITECTURE_PLANNER_AGENT_NAME

    @property
    def version(self) -> str:
        return ARCHITECTURE_PLANNER_AGENT_VERSION

    def run(self, value: DesignIntent) -> FloorPlanProposal:
        if not isinstance(value, DesignIntent):
            raise AgentContractError(
                "Architecture planner input is not a DesignIntent.",
                path="/input",
                details={
                    "agent": self.name,
                    "actual_type": type(value).__name__,
                    "expected_type": "DesignIntent",
                },
            )

        result = self._planner.plan(value)
        if not isinstance(result, FloorPlanProposal):
            raise AgentContractError(
                "Architecture planner returned a value that is not a FloorPlanProposal.",
                path="/output",
                details={
                    "agent": self.name,
                    "actual_type": type(result).__name__,
                    "expected_type": "FloorPlanProposal",
                },
            )
        if result.intent != value:
            raise AgentContractError(
                "Architecture planner output does not retain the input DesignIntent.",
                path="/output/intent",
                details={
                    "agent": self.name,
                    "reason": "INTENT_MISMATCH",
                },
            )
        return result

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        """Alias the agent boundary for safe pipeline composition."""

        return self.run(intent)
