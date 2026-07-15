from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from ai_parametric_architect.application import (
    AgentAuthorizationGateway,
    AgentPatchCommitRequest,
)
from ai_parametric_architect.benchmark.data import (
    BenchmarkAnnotationSet,
    BenchmarkCase,
    BenchmarkDataset,
    ReferenceAnnotation,
)
from ai_parametric_architect.benchmark.models import (
    BenchmarkExecutionMode,
    BenchmarkReport,
    BenchmarkSystemDescriptor,
)
from ai_parametric_architect.benchmark.runner import (
    BenchmarkRunner,
    BenchmarkSystem,
)
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    GeometryPrecisionPolicy,
    PlannerContractError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.evaluation.planning_metrics import PlanningMetricContext
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.planning.spatial_baseline import (
    RULE_BASED_SPATIAL_STRATEGY,
    RuleBasedSpatialFloorPlanPlanner,
)

BENCHMARK_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect" / "benchmark"
CORE_MODULES = ("data.py", "models.py", "runner.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "anthropic",
        "openai",
        "ortools",
        "random",
        "secrets",
        "time",
        "uuid",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.composition",
        "ai_parametric_architect.domain.audit",
        "ai_parametric_architect.domain.model",
        "ai_parametric_architect.domain.patch_impacts",
        "ai_parametric_architect.domain.patches",
        "ai_parametric_architect.domain.revisions",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.infrastructure",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.planning.solver",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.ports.patching",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.validation",
    }
)


class _StaticIntentAgent:
    def __init__(self, intent: DesignIntent) -> None:
        self._intent = intent

    def run(self, value: str) -> DesignIntent:
        return self._intent


class _SpatialPlanAgent:
    def run(self, value: DesignIntent) -> FloorPlanProposal:
        return RuleBasedSpatialFloorPlanPlanner().plan(value)


class _TickClock:
    def __init__(self) -> None:
        self._value = 0

    def monotonic_ns(self) -> int:
        self._value += 10
        return self._value


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _matches_root(imported: str, root: str) -> bool:
    return imported == root or imported.startswith(f"{root}.")


def _metric_context() -> PlanningMetricContext:
    return PlanningMetricContext(
        context_id="benchmark-boundary-v1",
        minimum_room_areas=(),
        default_minimum_room_area=6.0,
        minimum_adjacency_contact=1.0,
        separation_gap=1.0,
        near_distance=8.0,
        precision=GeometryPrecisionPolicy(
            linear_tolerance=1e-9,
            decimal_places=9,
        ),
        max_runs=1,
    )


def _report() -> tuple[DesignIntent, BenchmarkReport]:
    intent = DesignIntent(
        building_type="house",
        area=20,
        rooms=("study",),
    )
    dataset = BenchmarkDataset(
        dataset_id="architecture-boundary",
        dataset_version="1.0.0",
        cases=(
            BenchmarkCase(
                case_id="architecture_case",
                tags=("boundary",),
                input_requirement="Design a 20 sqm house with one study.",
            ),
        ),
    )
    annotations = BenchmarkAnnotationSet(
        annotation_set_id="architecture-reference",
        annotation_set_version="1.0.0",
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        annotations=(
            ReferenceAnnotation(
                case_id="architecture_case",
                expected_intent=intent,
                expected_constraints=(),
            ),
        ),
    )
    descriptor = BenchmarkSystemDescriptor(
        system_id="architecture-system",
        system_version="1.0.0",
        intent_agent_name="static-intent-agent",
        intent_agent_version="1.0.0",
        floor_plan_agent_name="spatial-baseline-agent",
        floor_plan_agent_version="1.0.0",
        planner_strategy=RULE_BASED_SPATIAL_STRATEGY,
        rules_version="1.0.0",
        random_seed=0,
        execution_mode=BenchmarkExecutionMode.DETERMINISTIC,
    )
    report = BenchmarkRunner(
        metric_context=_metric_context(),
        clock=_TickClock(),
    ).run(
        dataset,
        annotations,
        (
            BenchmarkSystem(
                descriptor=descriptor,
                intent_agent=_StaticIntentAgent(intent),
                floor_plan_agent=_SpatialPlanAgent(),
            ),
        ),
    )
    return intent, report


def test_benchmark_core_is_provider_solver_clock_random_and_world_write_neutral() -> None:
    violations = [
        f"{module} imports {imported}"
        for module in CORE_MODULES
        for imported in _imports(BENCHMARK_ROOT / module)
        if any(_matches_root(imported, root) for root in _FORBIDDEN_IMPORT_ROOTS)
    ]

    assert violations == []


def test_importing_benchmark_core_does_not_load_ortools() -> None:
    script = """
import sys
import ai_parametric_architect.benchmark
import ai_parametric_architect.benchmark.models
import ai_parametric_architect.benchmark.runner

assert "ai_parametric_architect.planning.solver" not in sys.modules
assert not any(name == "ortools" or name.startswith("ortools.") for name in sys.modules)
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_benchmark_runner_exposes_only_detached_run() -> None:
    public_methods = {
        name
        for name in dir(BenchmarkRunner)
        if not name.startswith("_") and callable(getattr(BenchmarkRunner, name))
    }

    assert public_methods == {"run"}


def test_benchmark_report_is_neither_commit_request_nor_authorization_evidence() -> None:
    intent, report = _report()
    identity = TrustedAuditIdentity(
        actor_id="benchmark-boundary-test",
        actor_type=AuditActorType.SYSTEM,
        trace_id="trace:benchmark-boundary-test",
    )
    gateway = AgentAuthorizationGateway(
        cast(Any, object()),
        cast(Any, object()),
        identity,
    )

    assert type(report) is BenchmarkReport
    with pytest.raises(PlannerContractError, match="PatchProposal"):
        AgentPatchCommitRequest(intent=intent, proposal=cast(Any, report))
    with pytest.raises(PlannerContractError, match="AgentPatchCommitRequest"):
        gateway.commit("mdl_benchmark", report)
