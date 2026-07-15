from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from ai_parametric_architect.application import AgentPatchCommitRequest

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _layer_imports(layer: str) -> list[tuple[Path, str]]:
    return [
        (path, imported)
        for path in sorted((SOURCE_ROOT / layer).rglob("*.py"))
        for imported in _imports(path)
    ]


def test_policy_layer_is_repository_free_and_deterministic() -> None:
    forbidden = {
        "fastapi",
        "shapely",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.evaluation",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.validation",
    }
    violations = [
        f"{path.relative_to(SOURCE_ROOT)} imports {imported}"
        for path, imported in _layer_imports("policy")
        if any(imported == root or imported.startswith(f"{root}.") for root in forbidden)
    ]

    assert violations == []


def test_untrusted_agent_llm_and_evaluation_layers_cannot_reach_authorization() -> None:
    forbidden = {
        "ai_parametric_architect.application.authorization",
        "ai_parametric_architect.policy",
    }
    violations = [
        f"{path.relative_to(SOURCE_ROOT)} imports {imported}"
        for layer in ("agents", "evaluation", "llm")
        for path, imported in _layer_imports(layer)
        if any(imported == root or imported.startswith(f"{root}.") for root in forbidden)
    ]

    assert violations == []


def test_planning_service_has_no_duplicate_semantic_authorization_helpers() -> None:
    planning_path = SOURCE_ROOT / "application" / "planning.py"
    source = planning_path.read_text(encoding="utf-8")
    imported = _imports(planning_path)

    assert "ai_parametric_architect.application.authorization" in imported
    assert "_enforce_proposal_contract" not in source
    assert "_require_exact_operations" not in source
    assert "ArchitecturePlanningAuthorizationPolicy" not in source


def test_commit_request_contains_no_identity_or_evaluation_evidence_field() -> None:
    assert tuple(field.name for field in fields(AgentPatchCommitRequest)) == (
        "intent",
        "proposal",
    )
