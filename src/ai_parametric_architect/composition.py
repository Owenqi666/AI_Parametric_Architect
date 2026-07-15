"""The single dependency-composition point for production adapters."""

from __future__ import annotations

from ai_parametric_architect.agents import (
    ArchitecturePlannerAgent,
    ConstraintReasoningAgent,
    PatchGeneratorAgent,
    RequirementAgent,
)
from ai_parametric_architect.application import (
    AgentAuthorizationGateway,
    ArchitectService,
    ArchitecturePlanningService,
    EditingService,
)
from ai_parametric_architect.domain import (
    ModelComplexityPolicy,
    StrictJsonTreeGuard,
    TrustedAuditIdentity,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.infrastructure import (
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
    SystemClock,
)
from ai_parametric_architect.llm import LLMRequirementParser
from ai_parametric_architect.planning import (
    AgentPlanningPipeline,
    ConstraintFloorPlanPlanner,
    RuleBasedPlanner,
    RuleBasedRequirementParser,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy
from ai_parametric_architect.ports import RevisionRepository
from ai_parametric_architect.reasoning import RuleBasedConstraintSolver
from ai_parametric_architect.renderer import SvgRenderer, WorldModelRenderIRProjector
from ai_parametric_architect.repositories import InMemoryRevisionRepository
from ai_parametric_architect.validation import ModelValidator


def create_service() -> ArchitectService:
    geometry = ShapelyGeometryEngine()
    json_guard = StrictJsonTreeGuard()
    complexity_policy = ModelComplexityPolicy()
    validator = ModelValidator(
        geometry,
        json_guard=json_guard,
        complexity_policy=complexity_policy,
    )
    renderer = SvgRenderer(geometry)
    return ArchitectService(
        validator,
        renderer,
        render_ir_projector=WorldModelRenderIRProjector(geometry),
    )


def create_editing_service(
    repository: RevisionRepository | None = None,
) -> EditingService:
    geometry = ShapelyGeometryEngine()
    json_guard = StrictJsonTreeGuard()
    complexity_policy = ModelComplexityPolicy()
    validator = ModelValidator(
        geometry,
        json_guard=json_guard,
        complexity_policy=complexity_policy,
    )
    revision_repository = InMemoryRevisionRepository() if repository is None else repository
    return EditingService(
        validator=validator,
        repository=revision_repository,
        patch_engine=JsonPatchEngine(
            json_guard=json_guard,
            complexity_policy=complexity_policy,
        ),
        clock=SystemClock(),
        json_guard=json_guard,
        complexity_policy=complexity_policy,
    )


def create_planning_service(
    editing_service: EditingService,
    *,
    audit_identity: TrustedAuditIdentity,
) -> ArchitecturePlanningService:
    """Compose the deterministic parser/planner around an initialized editing service."""

    authorization_gateway = AgentAuthorizationGateway(
        editing_service=editing_service,
        policy=ArchitecturePlanningAuthorizationPolicy(),
        audit_identity=audit_identity,
    )
    return ArchitecturePlanningService(
        parser=create_requirement_agent(),
        planner=AgentPlanningPipeline(
            create_architecture_planner_agent(),
            create_patch_generator_agent(),
        ),
        authorization_gateway=authorization_gateway,
    )


def create_requirement_agent() -> RequirementAgent:
    """Compose Task 2 with the deterministic parser; no LLM adapter is connected."""

    return RequirementAgent(RuleBasedRequirementParser())


def create_openai_requirement_agent(config: OpenAIProviderConfig) -> RequirementAgent:
    """Explicitly opt into network-backed requirement parsing; no write ports are injected."""

    provider = OpenAIResponsesProvider(config)
    return RequirementAgent(LLMRequirementParser(provider))


def create_architecture_planner_agent() -> ArchitecturePlannerAgent:
    """Compose Task 7.1 with deterministic CP-SAT and no world-model access."""

    return ArchitecturePlannerAgent(ConstraintFloorPlanPlanner())


def create_constraint_reasoning_agent() -> ConstraintReasoningAgent:
    """Compose Task 4 as symbolic planning only; no patch service is injected."""

    return ConstraintReasoningAgent(RuleBasedConstraintSolver())


def create_patch_generator_agent() -> PatchGeneratorAgent:
    """Compose Task 5 as proposal generation; application services retain commit authority."""

    return PatchGeneratorAgent(RuleBasedPlanner())
