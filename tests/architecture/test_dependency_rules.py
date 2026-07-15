from __future__ import annotations

import ast
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect"


def _python_files(layer: str | None = None) -> Iterator[Path]:
    root = SOURCE_ROOT if layer is None else SOURCE_ROOT / layer
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


def _assert_layer_avoids(layer: str, forbidden_roots: set[str]) -> None:
    violations: list[str] = []
    for path in _python_files(layer):
        for imported in _imports(path):
            if any(imported == root or imported.startswith(f"{root}.") for root in forbidden_roots):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {imported}")
    assert violations == []


def test_domain_has_no_infrastructure_dependencies() -> None:
    _assert_layer_avoids(
        "domain",
        {
            "fastapi",
            "jsonschema",
            "shapely",
            "ai_parametric_architect.backend",
            "ai_parametric_architect.geometry_engine",
            "ai_parametric_architect.renderer",
        },
    )


def test_intent_models_have_no_llm_transport_or_geometry_dependencies() -> None:
    model_imports = _imports(SOURCE_ROOT / "intent" / "models.py")
    forbidden = {
        "anthropic",
        "fastapi",
        "jsonschema",
        "openai",
        "shapely",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.renderer",
    }

    assert not {
        imported
        for imported in model_imports
        if any(imported == root or imported.startswith(f"{root}.") for root in forbidden)
    }


def test_agents_cannot_access_mutation_or_infrastructure_adapters() -> None:
    _assert_layer_avoids(
        "agents",
        {
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
        },
    )


def test_only_patch_agent_may_read_revision_and_patch_domain_contracts() -> None:
    forbidden = {
        "ai_parametric_architect.domain.patches",
        "ai_parametric_architect.domain.revisions",
    }
    violations: list[str] = []
    for path in _python_files("agents"):
        if path.name == "patch_agent.py":
            continue
        for imported in _imports(path):
            if imported in forbidden:
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {imported}")

    assert violations == []


def test_validation_and_renderer_do_not_import_transport_or_shapely() -> None:
    for layer in ("validation", "renderer", "editing", "repositories"):
        _assert_layer_avoids(layer, {"fastapi", "shapely"})


def test_renderers_cannot_reach_write_or_validation_boundaries() -> None:
    _assert_layer_avoids(
        "renderer",
        {
            "ai_parametric_architect.application",
            "ai_parametric_architect.backend",
            "ai_parametric_architect.editing",
            "ai_parametric_architect.policy",
            "ai_parametric_architect.repositories",
            "ai_parametric_architect.validation",
        },
    )


def test_editing_application_does_not_import_transport_or_geometry_backend() -> None:
    _assert_layer_avoids(
        "application",
        {
            "fastapi",
            "shapely",
            "ai_parametric_architect.backend",
            "ai_parametric_architect.geometry_engine",
        },
    )


def test_planning_core_is_provider_neutral_and_cannot_commit_models() -> None:
    _assert_layer_avoids(
        "planning",
        {
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
        },
    )


def test_planning_core_has_no_time_randomness_sources() -> None:
    _assert_layer_avoids("planning", {"datetime", "random", "time", "uuid"})


def test_reasoning_core_is_symbolic_read_only_and_deterministic() -> None:
    _assert_layer_avoids(
        "reasoning",
        {
            "anthropic",
            "datetime",
            "fastapi",
            "openai",
            "random",
            "shapely",
            "time",
            "uuid",
            "ai_parametric_architect.application",
            "ai_parametric_architect.backend",
            "ai_parametric_architect.domain.model",
            "ai_parametric_architect.domain.patches",
            "ai_parametric_architect.domain.revisions",
            "ai_parametric_architect.editing",
            "ai_parametric_architect.geometry_engine",
            "ai_parametric_architect.planning",
            "ai_parametric_architect.repositories",
            "ai_parametric_architect.renderer",
            "ai_parametric_architect.validation",
        },
    )


def test_shapely_is_confined_to_geometry_engine() -> None:
    violations = [
        str(path.relative_to(SOURCE_ROOT))
        for path in _python_files()
        if "geometry_engine" not in path.parts
        and any(name == "shapely" or name.startswith("shapely.") for name in _imports(path))
    ]
    assert violations == []


def test_epsilon_assignments_are_not_scattered_across_modules() -> None:
    violations: list[str] = []
    for path in _python_files():
        if path.name == "precision.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and any(token in target.id.lower() for token in ("epsilon", "tolerance"))
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, (int, float))
                ):
                    violations.append(f"{path.relative_to(SOURCE_ROOT)}:{node.lineno}")
    assert violations == []


def test_versioned_schema_is_an_installed_package_resource() -> None:
    resource = files("ai_parametric_architect.contracts.schemas").joinpath(
        "model-1.0.0.schema.json"
    )

    assert resource.is_file()
