from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ai_parametric_architect.infrastructure.llm import (
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
)

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect"
LLM_ROOT = SOURCE_ROOT / "llm"
INFRASTRUCTURE_LLM_ROOT = SOURCE_ROOT / "infrastructure" / "llm"
OPENAI_PROVIDER_PATH = INFRASTRUCTURE_LLM_ROOT / "openai_provider.py"


def _python_files(root: Path) -> Iterator[Path]:
    yield from sorted(root.rglob("*.py"))


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


class _NeverResponses:
    def create(self, **kwargs: Any) -> object:
        raise AssertionError(f"Unexpected OpenAI call with keys: {sorted(kwargs)}")


class _NeverClient:
    @property
    def responses(self) -> _NeverResponses:
        return _NeverResponses()


def test_provider_neutral_llm_layer_has_no_sdk_network_or_write_dependencies() -> None:
    forbidden = {
        "aiohttp",
        "anthropic",
        "fastapi",
        "httpx",
        "openai",
        "requests",
        "socket",
        "urllib",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.infrastructure",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.validation",
    }
    violations = [
        f"{path.relative_to(SOURCE_ROOT)} imports {imported}"
        for path in _python_files(LLM_ROOT)
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in forbidden)
    ]

    assert violations == []


def test_openai_sdk_import_is_confined_to_the_concrete_infrastructure_adapter() -> None:
    importers = [
        path.relative_to(SOURCE_ROOT)
        for path in _python_files(SOURCE_ROOT)
        if any(_matches_root(imported, "openai") for imported in _imports(path))
    ]

    assert importers == [OPENAI_PROVIDER_PATH.relative_to(SOURCE_ROOT)]
    assert "openai" in _imports(OPENAI_PROVIDER_PATH)


def test_real_llm_infrastructure_cannot_reach_write_or_geometry_capabilities() -> None:
    forbidden = {
        "ortools",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.domain.patch_impacts",
        "ai_parametric_architect.domain.patches",
        "ai_parametric_architect.domain.revisions",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.planning.solver",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.ports.patching",
        "ai_parametric_architect.ports.repository",
        "ai_parametric_architect.ports.validation",
        "ai_parametric_architect.reasoning.solver",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.validation",
    }
    violations = [
        f"{path.relative_to(SOURCE_ROOT)} imports {imported}"
        for path in _python_files(INFRASTRUCTURE_LLM_ROOT)
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in forbidden)
    ]

    assert violations == []


def test_real_provider_surface_has_no_mutation_or_commit_authority() -> None:
    provider = OpenAIResponsesProvider(
        OpenAIProviderConfig(model="gpt-test"),
        client=_NeverClient(),
    )
    public_class_members = {
        name for name in vars(OpenAIResponsesProvider) if not name.startswith("_")
    }

    assert public_class_members == {"complete", "name", "version"}
    assert not hasattr(provider, "__dict__")
    for capability in (
        "apply",
        "commit",
        "mutate",
        "patch",
        "repository",
        "revision",
        "write",
    ):
        assert not hasattr(provider, capability)
        with pytest.raises(AttributeError):
            setattr(provider, capability, object())
