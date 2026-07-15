from __future__ import annotations

import ast
from pathlib import Path

from ai_parametric_architect.llm import (
    LLMFloorPlanPlanner,
    LLMPatchProposalGenerator,
    LLMRequirementParser,
)

LLM_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect" / "llm"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_llm_layer_has_no_provider_sdk_or_write_side_dependencies() -> None:
    forbidden = {
        "anthropic",
        "fastapi",
        "openai",
        "shapely",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.validation",
    }
    violations: list[str] = []

    for path in sorted(LLM_ROOT.glob("*.py")):
        for imported in _imports(path):
            if any(imported == root or imported.startswith(f"{root}.") for root in forbidden):
                violations.append(f"{path.name} imports {imported}")

    assert violations == []


def test_llm_provider_contract_exposes_no_mutation_or_commit_method() -> None:
    tree = ast.parse(
        (LLM_ROOT / "base.py").read_text(encoding="utf-8"),
        filename=str(LLM_ROOT / "base.py"),
    )
    provider = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "LLMProvider"
    )
    methods = {
        node.name
        for node in provider.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert methods == {"complete", "name", "version"}


def test_llm_agent_adapters_expose_only_their_proposal_port_operation() -> None:
    public_methods = {
        adapter.__name__: {
            name
            for name in dir(adapter)
            if not name.startswith("_") and callable(getattr(adapter, name))
        }
        for adapter in (
            LLMRequirementParser,
            LLMFloorPlanPlanner,
            LLMPatchProposalGenerator,
        )
    }

    assert public_methods == {
        "LLMRequirementParser": {"parse"},
        "LLMFloorPlanPlanner": {"plan"},
        "LLMPatchProposalGenerator": {"generate"},
    }
