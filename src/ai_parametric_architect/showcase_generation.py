"""Trusted offline composition for checked-in showcase artifacts."""

from __future__ import annotations

from pathlib import Path

from ai_parametric_architect.agents import ArchitecturePlannerAgent, RequirementAgent
from ai_parametric_architect.benchmark import (
    BenchmarkBudget,
    BenchmarkReport,
    load_benchmark_annotations,
    load_benchmark_dataset,
)
from ai_parametric_architect.composition import (
    create_cp_sat_benchmark_system,
    create_planning_benchmark_runner,
    create_rule_spatial_benchmark_system,
)
from ai_parametric_architect.domain import (
    DesignIntent,
    GeometryPrecisionPolicy,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.evaluation.planning_metrics import (
    PlanningMetricContext,
    PlanningMetricsEvaluator,
)
from ai_parametric_architect.llm import (
    LLMRequirementParser,
    MockLLMProvider,
    design_intent_prompt,
)
from ai_parametric_architect.planning import (
    CP_SAT_STRATEGY,
    RULE_BASED_SPATIAL_STRATEGY,
    ConstraintFloorPlanPlanner,
    OptimizationWeights,
    PlanningRules,
    RuleBasedSpatialFloorPlanPlanner,
)
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.showcase import (
    PlanningShowcaseArtifact,
    ShowcaseCase,
    ShowcaseExecution,
    ShowcaseScenarioEvidence,
    ShowcaseSystemEvidence,
    build_planning_showcase,
    canonical_proposal_digest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREVIEW_OUTPUT = (
    PROJECT_ROOT / "frontend/public/examples/planning-showcase.preview-1.0.0.json"
)
DEFAULT_BENCHMARK_OUTPUT = (
    PROJECT_ROOT / "frontend/public/examples/planning-core.benchmark-report-1.0.0.json"
)
BENCHMARK_DATASET = PROJECT_ROOT / "benchmarks/datasets/planning-core-1.0.0.json"
BENCHMARK_ANNOTATIONS = PROJECT_ROOT / "benchmarks/annotations/planning-core-reference-1.0.0.json"
BENCHMARK_TRIALS = 2

FAMILY_HOUSE_REQUIREMENT = (
    "Design a 120 sqm south-facing family house with three bedrooms, a living room "
    "and a kitchen. Keep the kitchen adjacent to the living room."
)
COMPACT_APARTMENT_REQUIREMENT = (
    "Design a compact 72 sqm apartment with one bedroom, one bathroom, a living room "
    "and a kitchen. Keep circulation efficient."
)
CONSTRAINT_CONFLICT_REQUIREMENT = (
    "Design a 40 sqm house with one bedroom and one bathroom. Require the bedroom "
    "to be both north and south of the bathroom."
)
RECORDED_MOCK_INTENT_PARSER_NAME = "recorded-mock-llm-requirement-parser"

# Preserve the standard hard constraints while making the five-room replay fast enough
# to prove optimality deterministically. Showcase metric evidence still scores circulation.
SHOWCASE_OPTIMIZATION = OptimizationWeights(
    utilization=40,
    target_area=12,
    compactness=0,
    circulation=0,
    orientation=20,
    optional_constraint=30,
)

SHOWCASE_CASES = (
    ShowcaseCase(
        scenario_id="family-house",
        title="South-facing family house",
        input_requirement=FAMILY_HOUSE_REQUIREMENT,
    ),
    ShowcaseCase(
        scenario_id="compact-apartment",
        title="Compact apartment",
        input_requirement=COMPACT_APARTMENT_REQUIREMENT,
    ),
    ShowcaseCase(
        scenario_id="constraint-conflict",
        title="Conflicting spatial constraints",
        input_requirement=CONSTRAINT_CONFLICT_REQUIREMENT,
    ),
)

SHOWCASE_INTENTS = (
    DesignIntent(
        building_type="house",
        area=120,
        rooms=("bedroom", "bedroom", "bedroom", "living", "kitchen"),
        orientation="south",
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="kitchen",
                relation=SpatialRelation.ADJACENT_TO,
                target_room_type="living",
            ),
        ),
    ),
    DesignIntent(
        building_type="apartment",
        area=72,
        rooms=("bedroom", "bathroom", "living", "kitchen"),
    ),
    DesignIntent(
        building_type="house",
        area=40,
        rooms=("bedroom", "bathroom"),
        spatial_constraints=(
            SpatialConstraint(
                source_room_type="bedroom",
                relation=SpatialRelation.NORTH_OF,
                target_room_type="bathroom",
            ),
            SpatialConstraint(
                source_room_type="bedroom",
                relation=SpatialRelation.SOUTH_OF,
                target_room_type="bathroom",
            ),
        ),
    ),
)


def build_preview_artifact() -> PlanningShowcaseArtifact:
    """Replay recorded typed Mock LLM outputs through detached planning only."""

    rules = PlanningRules(optimization=SHOWCASE_OPTIMIZATION)
    provider = MockLLMProvider(SHOWCASE_INTENTS)
    intent_agent = RequirementAgent(LLMRequirementParser(provider))
    floor_plan_agent = ArchitecturePlannerAgent(ConstraintFloorPlanPlanner(rules=rules))
    rule_spatial_agent = ArchitecturePlannerAgent(RuleBasedSpatialFloorPlanPlanner())
    metric_context = PlanningMetricContext.from_threshold_source(
        context_id="planning-showcase-v1",
        source=rules,
        precision=GeometryPrecisionPolicy(
            linear_tolerance=1e-9,
            decimal_places=9,
        ),
        max_runs=1,
    )
    evaluator = PlanningMetricsEvaluator(metric_context)
    execution = ShowcaseExecution(
        intent_agent_name=RECORDED_MOCK_INTENT_PARSER_NAME,
        intent_agent_version=intent_agent.version,
        floor_plan_agent_name=floor_plan_agent.name,
        floor_plan_agent_version=floor_plan_agent.version,
        planner_strategy=CP_SAT_STRATEGY,
        rules_version=rules.version,
        random_seed=rules.random_seed,
    )
    artifact = build_planning_showcase(
        cases=SHOWCASE_CASES,
        execution=execution,
        intent_agent=intent_agent,
        floor_plan_agent=floor_plan_agent,
        evidence_factory=lambda case, intent, proposal: _scenario_evidence(
            case=case,
            intent=intent,
            proposal=proposal,
            metric_context=metric_context,
            evaluator=evaluator,
            rule_spatial_agent=rule_spatial_agent,
        ),
    )
    expected_prompts = tuple(
        design_intent_prompt(case.input_requirement) for case in SHOWCASE_CASES
    )
    if provider.remaining_responses != 0 or provider.requests != expected_prompts:
        raise RuntimeError("Recorded showcase prompts and typed responses did not align.")
    return artifact


def _scenario_evidence(
    *,
    case: ShowcaseCase,
    intent: DesignIntent,
    proposal: FloorPlanProposal,
    metric_context: PlanningMetricContext,
    evaluator: PlanningMetricsEvaluator,
    rule_spatial_agent: ArchitecturePlannerAgent,
) -> ShowcaseScenarioEvidence:
    systems: list[ShowcaseSystemEvidence] = []
    if case.scenario_id == "compact-apartment":
        baseline = rule_spatial_agent.run(intent)
        systems.append(
            ShowcaseSystemEvidence(
                system_id="rule-spatial-v2",
                strategy=RULE_BASED_SPATIAL_STRATEGY,
                proposal_digest=canonical_proposal_digest(baseline),
                report=evaluator.evaluate((baseline,)),
            )
        )
    systems.append(
        ShowcaseSystemEvidence(
            system_id="cp-sat-v2",
            strategy=CP_SAT_STRATEGY,
            proposal_digest=canonical_proposal_digest(proposal),
            report=evaluator.evaluate((proposal,)),
        )
    )
    return ShowcaseScenarioEvidence(
        metric_context=metric_context,
        systems=tuple(systems),
    )


def build_benchmark_report() -> BenchmarkReport:
    """Run the existing two-system benchmark with truthful monotonic timings."""

    dataset = load_benchmark_dataset(BENCHMARK_DATASET)
    annotations = load_benchmark_annotations(BENCHMARK_ANNOTATIONS, dataset=dataset)
    rules = PlanningRules()
    budget = BenchmarkBudget(
        max_cases=16,
        max_systems=2,
        max_trials=BENCHMARK_TRIALS,
        max_attempts=64,
    )
    runner = create_planning_benchmark_runner(rules=rules, budget=budget)
    return runner.run(
        dataset,
        annotations,
        (
            create_rule_spatial_benchmark_system(),
            create_cp_sat_benchmark_system(rules=rules),
        ),
        trials=BENCHMARK_TRIALS,
    )


__all__ = [
    "BENCHMARK_ANNOTATIONS",
    "BENCHMARK_DATASET",
    "BENCHMARK_TRIALS",
    "COMPACT_APARTMENT_REQUIREMENT",
    "CONSTRAINT_CONFLICT_REQUIREMENT",
    "DEFAULT_BENCHMARK_OUTPUT",
    "DEFAULT_PREVIEW_OUTPUT",
    "FAMILY_HOUSE_REQUIREMENT",
    "PROJECT_ROOT",
    "RECORDED_MOCK_INTENT_PARSER_NAME",
    "SHOWCASE_CASES",
    "SHOWCASE_INTENTS",
    "SHOWCASE_OPTIMIZATION",
    "build_benchmark_report",
    "build_preview_artifact",
]
