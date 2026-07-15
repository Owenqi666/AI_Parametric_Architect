from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai_parametric_architect.renderer import WorldModelRenderIRProjector
from ai_parametric_architect.showcase_generation import build_preview_artifact

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_MODULE = PROJECT_ROOT / "src/ai_parametric_architect/showcase.py"
GENERATION_MODULE = PROJECT_ROOT / "src/ai_parametric_architect/showcase_generation.py"
GENERATOR_SCRIPT = PROJECT_ROOT / "scripts/generate_showcase_fixtures.py"

_FORBIDDEN_SHOWCASE_IMPORTS = (
    "ai_parametric_architect.application",
    "ai_parametric_architect.backend",
    "ai_parametric_architect.domain.model",
    "ai_parametric_architect.domain.patches",
    "ai_parametric_architect.domain.revisions",
    "ai_parametric_architect.editing",
    "ai_parametric_architect.policy",
    "ai_parametric_architect.repositories",
    "ai_parametric_architect.renderer",
    "ai_parametric_architect.validation",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            result.add(node.module)
    return result


def test_showcase_contract_has_no_world_write_or_render_projection_dependency() -> None:
    imported = _imports(SHOWCASE_MODULE)

    assert not any(
        value == forbidden or value.startswith(f"{forbidden}.")
        for value in imported
        for forbidden in _FORBIDDEN_SHOWCASE_IMPORTS
    )


def test_generator_does_not_name_world_model_or_write_services() -> None:
    source = "\n".join(
        (
            GENERATION_MODULE.read_text(encoding="utf-8"),
            GENERATOR_SCRIPT.read_text(encoding="utf-8"),
        )
    )

    for forbidden in (
        "WorldModelRenderIRProjector",
        "create_editing_service",
        "create_planning_service",
        "AgentPatchCommitRequest",
        "EditingService",
        "RevisionRepository",
    ):
        assert forbidden not in source


def test_preview_generation_does_not_construct_the_world_model_projector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_projector(*args: object, **kwargs: object) -> None:
        raise AssertionError("proposal preview must not construct a World Model projector")

    monkeypatch.setattr(WorldModelRenderIRProjector, "__init__", unexpected_projector)

    artifact = build_preview_artifact()

    assert len(artifact.scenarios) == 3
