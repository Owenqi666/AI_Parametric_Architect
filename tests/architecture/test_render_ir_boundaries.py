from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

from ai_parametric_architect.ports import RenderIRProjector

PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "ai_parametric_architect"
RENDERER_ROOT = SOURCE_ROOT / "renderer"
FRONTEND_ROOT = PROJECT_ROOT / "frontend"

_RENDER_IR_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "fastapi",
        "shapely",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.evaluation",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.infrastructure",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.planning",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.repositories",
    }
)
_RENDER_IR_PROTECTED_LAYERS = (
    "agent_trace",
    "agents",
    "contracts",
    "editing",
    "evaluation",
    "geometry_engine",
    "infrastructure",
    "intent",
    "llm",
    "planning",
    "policy",
    "reasoning",
    "repositories",
    "validation",
)
_PACKAGE_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
_THREE_IMPORT = re.compile(
    r"(?:from\s+|import\s*\(\s*|require\s*\(\s*)['\"]three(?:/[^'\"]*)?['\"]"
)


def _python_files(root: Path) -> Iterator[Path]:
    if root.is_dir():
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


def _imports_render_ir(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_render_ir_name(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and _is_render_ir_name(node.module):
                return True
            if any(_is_render_ir_name(alias.name) for alias in node.names):
                return True
    return False


def _is_render_ir_name(value: str) -> bool:
    normalized = value.lower()
    return "render_ir" in normalized or "renderir" in normalized


def _project_files() -> Iterator[Path]:
    ignored_directories = {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vinext",
        ".wrangler",
        "build",
        "coverage",
        "dist",
        "node_modules",
    }
    for root, directories, filenames in os.walk(PROJECT_ROOT):
        directories[:] = sorted(
            directory for directory in directories if directory not in ignored_directories
        )
        root_path = Path(root)
        for filename in sorted(filenames):
            yield root_path / filename


def test_render_ir_adapter_depends_only_on_neutral_rendering_boundaries() -> None:
    adapter_path = RENDERER_ROOT / "render_ir.py"

    assert adapter_path.is_file(), "The Render IR projector must remain a renderer adapter."
    violations = [
        imported
        for imported in sorted(_imports(adapter_path))
        if any(
            _matches_root(imported, forbidden) for forbidden in _RENDER_IR_FORBIDDEN_IMPORT_ROOTS
        )
    ]

    assert violations == []


def test_render_ir_projector_port_exposes_only_projection() -> None:
    public_methods = {
        name
        for name in dir(RenderIRProjector)
        if not name.startswith("_") and callable(getattr(RenderIRProjector, name))
    }

    assert public_methods == {"project"}


def test_three_js_dependency_is_confined_to_frontend() -> None:
    manifests = [path for path in _project_files() if path.name == "package.json"]
    declarations: list[Path] = []
    for manifest in manifests:
        content = json.loads(manifest.read_text(encoding="utf-8"))
        for section_name in _PACKAGE_DEPENDENCY_SECTIONS:
            section = content.get(section_name, {})
            if isinstance(section, dict) and "three" in section:
                declarations.append(manifest)

    assert [
        str(path.relative_to(PROJECT_ROOT))
        for path in declarations
        if FRONTEND_ROOT not in path.parents
    ] == []

    source_violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _project_files()
        if path.suffix in {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
        and FRONTEND_ROOT not in path.parents
        and _THREE_IMPORT.search(path.read_text(encoding="utf-8")) is not None
    ]
    assert source_violations == []


def test_protected_python_layers_do_not_depend_on_render_ir() -> None:
    violations = [
        str(path.relative_to(SOURCE_ROOT))
        for layer in _RENDER_IR_PROTECTED_LAYERS
        for path in _python_files(SOURCE_ROOT / layer)
        if _imports_render_ir(path)
    ]

    assert violations == []
