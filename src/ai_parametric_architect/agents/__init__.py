"""Provider-neutral agent interfaces and deterministic implementations."""

from ai_parametric_architect.agents.base import Agent
from ai_parametric_architect.agents.patch_agent import (
    PATCH_GENERATOR_AGENT_NAME,
    PATCH_GENERATOR_AGENT_VERSION,
    PatchGenerationRequest,
    PatchGeneratorAgent,
)
from ai_parametric_architect.agents.planner_agent import (
    ARCHITECTURE_PLANNER_AGENT_NAME,
    ARCHITECTURE_PLANNER_AGENT_VERSION,
    ArchitecturePlannerAgent,
)
from ai_parametric_architect.agents.reasoning_agent import (
    CONSTRAINT_REASONING_AGENT_NAME,
    CONSTRAINT_REASONING_AGENT_VERSION,
    ConstraintReasoningAgent,
)
from ai_parametric_architect.agents.requirement_agent import (
    REQUIREMENT_AGENT_NAME,
    REQUIREMENT_AGENT_VERSION,
    AgentContractError,
    RequirementAgent,
)

__all__ = [
    "ARCHITECTURE_PLANNER_AGENT_NAME",
    "ARCHITECTURE_PLANNER_AGENT_VERSION",
    "CONSTRAINT_REASONING_AGENT_NAME",
    "CONSTRAINT_REASONING_AGENT_VERSION",
    "PATCH_GENERATOR_AGENT_NAME",
    "PATCH_GENERATOR_AGENT_VERSION",
    "REQUIREMENT_AGENT_NAME",
    "REQUIREMENT_AGENT_VERSION",
    "Agent",
    "AgentContractError",
    "ArchitecturePlannerAgent",
    "ConstraintReasoningAgent",
    "PatchGenerationRequest",
    "PatchGeneratorAgent",
    "RequirementAgent",
]
