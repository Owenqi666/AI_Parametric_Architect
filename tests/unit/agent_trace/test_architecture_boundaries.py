from __future__ import annotations

import ast
from pathlib import Path

from ai_parametric_architect.agent_trace import AgentTraceRecorder

PROJECT_ROOT = Path(__file__).parents[3]
TRACE_PACKAGE = PROJECT_ROOT / "src" / "ai_parametric_architect" / "agent_trace"

FORBIDDEN_IMPORTS = {
    "ai_parametric_architect.application",
    "ai_parametric_architect.backend",
    "ai_parametric_architect.editing",
    "ai_parametric_architect.geometry_engine",
    "ai_parametric_architect.llm",
    "ai_parametric_architect.repositories",
    "anthropic",
    "cohere",
    "fastapi",
    "google.generativeai",
    "langchain",
    "mistralai",
    "openai",
    "shapely",
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_trace_package_has_no_mutation_transport_geometry_or_llm_dependencies() -> None:
    violations: list[str] = []
    for path in sorted(TRACE_PACKAGE.glob("*.py")):
        for imported in sorted(imported_modules(path)):
            if any(
                imported == forbidden or imported.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_IMPORTS
            ):
                violations.append(f"{path.name}: {imported}")

    assert violations == []


def test_recorder_exposes_observation_only_and_no_commit_capability() -> None:
    public_methods = {
        name
        for name in dir(AgentTraceRecorder)
        if not name.startswith("_") and callable(getattr(AgentTraceRecorder, name))
    }

    assert public_methods == {"record"}
