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
from ai_parametric_architect.benchmark.models import (
    BenchmarkBudget,
    BenchmarkExecutionMode,
    BenchmarkSystemDescriptor,
)
from ai_parametric_architect.benchmark.runner import BenchmarkRunner, BenchmarkSystem
from ai_parametric_architect.domain import (
    GeometryPrecisionPolicy,
    ModelComplexityPolicy,
    StrictJsonTreeGuard,
    TrustedAuditIdentity,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.evaluation.planning_metrics import (
    MAX_PLANNING_EVALUATION_RUNS,
    PlanningMetricContext,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.infrastructure import (
    OPENAI_PROVIDER_NAME,
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
    SystemClock,
    SystemMonotonicClock,
)
from ai_parametric_architect.llm import PROMPT_VERSION, LLMRequirementParser
from ai_parametric_architect.planning import (
    CP_SAT_STRATEGY,
    RULE_BASED_SPATIAL_STRATEGY,
    AgentPlanningPipeline,
    ConstraintFloorPlanPlanner,
    PlanningRules,
    RuleBasedPlanner,
    RuleBasedRequirementParser,
    RuleBasedSpatialFloorPlanPlanner,
    RuleBasedSpatialPolicy,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy
from ai_parametric_architect.ports import RevisionRepository
from ai_parametric_architect.reasoning import RuleBasedConstraintSolver
from ai_parametric_architect.renderer import SvgRenderer, WorldModelRenderIRProjector
from ai_parametric_architect.repositories import InMemoryRevisionRepository
from ai_parametric_architect.validation import ModelValidator

PLANNING_BENCHMARK_SYSTEM_VERSION = "1.0.0"
PLANNING_BENCHMARK_CONTEXT_ID = "planning-benchmark-v1"


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


def create_planning_benchmark_runner(
    *,
    rules: PlanningRules | None = None,
    budget: BenchmarkBudget | None = None,
) -> BenchmarkRunner:
    """Compose detached metrics and an injected monotonic clock for P3 benchmarks."""

    selected_rules = PlanningRules() if rules is None else rules
    selected_budget = BenchmarkBudget() if budget is None else budget
    if selected_budget.max_trials > MAX_PLANNING_EVALUATION_RUNS:
        raise ValueError("Benchmark max_trials exceeds the planning metric implementation budget.")
    metric_context = PlanningMetricContext.from_threshold_source(
        context_id=PLANNING_BENCHMARK_CONTEXT_ID,
        source=selected_rules,
        precision=GeometryPrecisionPolicy(
            linear_tolerance=1e-9,
            decimal_places=9,
        ),
        max_runs=selected_budget.max_trials,
    )
    return BenchmarkRunner(
        metric_context=metric_context,
        clock=SystemMonotonicClock(),
        budget=selected_budget,
    )


def create_rule_spatial_benchmark_system(
    *,
    policy: RuleBasedSpatialPolicy | None = None,
) -> BenchmarkSystem:
    """Compose the independent deterministic v2 rule baseline."""

    selected_policy = RuleBasedSpatialPolicy() if policy is None else policy
    intent_agent = create_requirement_agent()
    floor_plan_agent = ArchitecturePlannerAgent(RuleBasedSpatialFloorPlanPlanner(selected_policy))
    return BenchmarkSystem(
        descriptor=BenchmarkSystemDescriptor(
            system_id="rule-spatial-v2",
            system_version=PLANNING_BENCHMARK_SYSTEM_VERSION,
            intent_agent_name=intent_agent.name,
            intent_agent_version=intent_agent.version,
            floor_plan_agent_name=floor_plan_agent.name,
            floor_plan_agent_version=floor_plan_agent.version,
            planner_strategy=RULE_BASED_SPATIAL_STRATEGY,
            rules_version=selected_policy.version,
            random_seed=0,
            execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
        ),
        intent_agent=intent_agent,
        floor_plan_agent=floor_plan_agent,
    )


def create_cp_sat_benchmark_system(
    *,
    rules: PlanningRules | None = None,
) -> BenchmarkSystem:
    """Compose the offline deterministic parser plus detached CP-SAT planner."""

    selected_rules = PlanningRules() if rules is None else rules
    intent_agent = create_requirement_agent()
    floor_plan_agent = ArchitecturePlannerAgent(ConstraintFloorPlanPlanner(rules=selected_rules))
    return BenchmarkSystem(
        descriptor=BenchmarkSystemDescriptor(
            system_id="cp-sat-v2",
            system_version=PLANNING_BENCHMARK_SYSTEM_VERSION,
            intent_agent_name=intent_agent.name,
            intent_agent_version=intent_agent.version,
            floor_plan_agent_name=floor_plan_agent.name,
            floor_plan_agent_version=floor_plan_agent.version,
            planner_strategy=CP_SAT_STRATEGY,
            rules_version=selected_rules.version,
            random_seed=selected_rules.random_seed,
            execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
        ),
        intent_agent=intent_agent,
        floor_plan_agent=floor_plan_agent,
    )


def create_openai_cp_sat_benchmark_system(
    config: OpenAIProviderConfig,
    *,
    rules: PlanningRules | None = None,
) -> BenchmarkSystem:
    """Explicitly opt a real OpenAI intent adapter into the detached CP-SAT benchmark."""

    selected_rules = PlanningRules() if rules is None else rules
    intent_agent = create_openai_requirement_agent(config)
    floor_plan_agent = ArchitecturePlannerAgent(ConstraintFloorPlanPlanner(rules=selected_rules))
    return BenchmarkSystem(
        descriptor=BenchmarkSystemDescriptor(
            system_id="openai-cp-sat-v2",
            system_version=PLANNING_BENCHMARK_SYSTEM_VERSION,
            intent_agent_name=intent_agent.name,
            intent_agent_version=intent_agent.version,
            floor_plan_agent_name=floor_plan_agent.name,
            floor_plan_agent_version=floor_plan_agent.version,
            planner_strategy=CP_SAT_STRATEGY,
            rules_version=selected_rules.version,
            random_seed=selected_rules.random_seed,
            execution_mode=BenchmarkExecutionMode.REAL_NONDETERMINISTIC,
            provider=OPENAI_PROVIDER_NAME,
            model=config.model,
            prompt_version=PROMPT_VERSION,
        ),
        intent_agent=intent_agent,
        floor_plan_agent=floor_plan_agent,
    )
