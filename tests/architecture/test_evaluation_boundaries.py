from __future__ import annotations

import ast
from pathlib import Path

from ai_parametric_architect.evaluation import DetachedPatchValidator, EvaluationRunner

EVALUATION_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect" / "evaluation"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_evaluation_layer_is_provider_neutral_and_has_no_commit_dependency() -> None:
    forbidden = {
        "anthropic",
        "fastapi",
        "openai",
        "shapely",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.validation",
    }
    violations: list[str] = []
    for path in sorted(EVALUATION_ROOT.rglob("*.py")):
        for imported in _imports(path):
            if any(imported == root or imported.startswith(f"{root}.") for root in forbidden):
                violations.append(f"{path.relative_to(EVALUATION_ROOT)} imports {imported}")

    assert violations == []


def test_evaluation_public_services_expose_no_repository_or_commit_operation() -> None:
    runner_methods = {
        name
        for name in dir(EvaluationRunner)
        if not name.startswith("_") and callable(getattr(EvaluationRunner, name))
    }
    validator_methods = {
        name
        for name in dir(DetachedPatchValidator)
        if not name.startswith("_") and callable(getattr(DetachedPatchValidator, name))
    }

    assert runner_methods == {"run"}
    assert validator_methods == {"validate"}
