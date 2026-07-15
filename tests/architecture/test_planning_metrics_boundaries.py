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
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    GeometryPrecisionPolicy,
    PlannerContractError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.evaluation.planning_metrics import (
    PlanningMetricContext,
    PlanningMetricsEvaluator,
    PlanningMetricsReport,
)
from ai_parametric_architect.planning import RuleBasedFloorPlanPlanner

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect"
PLANNING_METRICS_ROOT = SOURCE_ROOT / "evaluation" / "planning_metrics"

_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "datetime",
        "fastapi",
        "ortools",
        "random",
        "secrets",
        "shapely",
        "time",
        "uuid",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.domain.revisions",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.planning.solver",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.repository",
        "ai_parametric_architect.validation",
    }
)


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


def _detached_report() -> tuple[DesignIntent, PlanningMetricsReport]:
    intent = DesignIntent(building_type="house", area=20, rooms=("study",))
    plan = RuleBasedFloorPlanPlanner().plan(intent)
    context = PlanningMetricContext(
        context_id="architecture-boundary-v1",
        minimum_room_areas=(),
        default_minimum_room_area=6.0,
        minimum_adjacency_contact=1.0,
        separation_gap=1.0,
        near_distance=8.0,
        precision=GeometryPrecisionPolicy(linear_tolerance=1e-9, decimal_places=9),
        max_runs=2,
    )
    return intent, PlanningMetricsEvaluator(context).evaluate((plan,))


def test_planning_metrics_are_solver_provider_and_authority_neutral() -> None:
    violations = [
        f"{path.relative_to(SOURCE_ROOT)} imports {imported}"
        for path in sorted(PLANNING_METRICS_ROOT.rglob("*.py"))
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in _FORBIDDEN_IMPORT_ROOTS)
    ]

    assert violations == []


def test_importing_planning_metrics_does_not_load_native_solver() -> None:
    script = """
import sys
import ai_parametric_architect.evaluation.planning_metrics

assert "ai_parametric_architect.planning.solver" not in sys.modules
assert not any(name == "ortools" or name.startswith("ortools.") for name in sys.modules)
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_planning_metrics_evaluator_exposes_only_detached_evaluation() -> None:
    public_methods = {
        name
        for name in dir(PlanningMetricsEvaluator)
        if not name.startswith("_") and callable(getattr(PlanningMetricsEvaluator, name))
    }

    assert public_methods == {"evaluate"}


def test_planning_metrics_report_is_neither_authorization_evidence_nor_commit_request() -> None:
    intent, report = _detached_report()
    identity = TrustedAuditIdentity(
        actor_id="architecture-boundary-test",
        actor_type=AuditActorType.SYSTEM,
        trace_id="trace:planning-metrics-boundary",
    )
    gateway = AgentAuthorizationGateway(
        cast(Any, object()),
        cast(Any, object()),
        identity,
    )

    with pytest.raises(PlannerContractError, match="PatchProposal"):
        AgentPatchCommitRequest(intent=intent, proposal=cast(Any, report))
    with pytest.raises(PlannerContractError, match="AgentPatchCommitRequest"):
        gateway.commit("mdl_detached", report)
