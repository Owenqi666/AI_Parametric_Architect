from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "ai_parametric_architect"
SOLVER_ROOT = SOURCE_ROOT / "planning" / "solver"

_ORTOOLS_FREE_LAYERS = (
    "agents",
    "domain",
    "evaluation",
    "llm",
    "policy",
    "ports",
)
_SOLVER_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "anthropic",
        "fastapi",
        "openai",
        "shapely",
        "ai_parametric_architect.agent_trace",
        "ai_parametric_architect.application",
        "ai_parametric_architect.backend",
        "ai_parametric_architect.composition",
        "ai_parametric_architect.domain.audit",
        "ai_parametric_architect.domain.model",
        "ai_parametric_architect.domain.patch_impacts",
        "ai_parametric_architect.domain.patches",
        "ai_parametric_architect.domain.planning_record",
        "ai_parametric_architect.domain.revisions",
        "ai_parametric_architect.editing",
        "ai_parametric_architect.geometry_engine",
        "ai_parametric_architect.infrastructure",
        "ai_parametric_architect.llm",
        "ai_parametric_architect.policy",
        "ai_parametric_architect.repositories",
        "ai_parametric_architect.renderer",
        "ai_parametric_architect.validation",
    }
)
_NONDETERMINISTIC_IMPORT_ROOTS = frozenset(
    {
        "datetime",
        "numpy.random",
        "random",
        "secrets",
        "time",
        "uuid",
    }
)
_BRUTE_FORCE_ITERTOOLS = frozenset(
    {
        "combinations",
        "combinations_with_replacement",
        "permutations",
        "product",
    }
)


def _python_files(root: Path = SOURCE_ROOT) -> Iterator[Path]:
    if root.is_dir():
        yield from sorted(root.rglob("*.py"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _matches_root(imported: str, root: str) -> bool:
    return imported == root or imported.startswith(f"{root}.")


def _relative(path: Path) -> str:
    return str(path.relative_to(SOURCE_ROOT))


def _forbidden_itertools_uses(path: Path) -> set[str]:
    tree = _tree(path)
    module_aliases: set[str] = set()
    member_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "itertools":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "itertools":
            for alias in node.names:
                if alias.name in _BRUTE_FORCE_ITERTOOLS:
                    member_aliases[alias.asname or alias.name] = alias.name

    violations = set(member_aliases.values())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _BRUTE_FORCE_ITERTOOLS
            and isinstance(node.value, ast.Name)
            and node.value.id in module_aliases
        ):
            violations.add(node.attr)
    return violations


def test_ortools_cp_sat_is_confined_to_the_planning_solver_adapter() -> None:
    ortools_imports = [
        (path, imported)
        for path in _python_files()
        for imported in _imports(path)
        if _matches_root(imported, "ortools")
    ]

    assert ortools_imports, "The planning solver must use the OR-Tools CP-SAT implementation."
    assert [
        f"{_relative(path)} imports {imported}"
        for path, imported in ortools_imports
        if SOLVER_ROOT not in path.parents
    ] == []
    assert any(
        imported == "ortools.sat.python" or imported.startswith("ortools.sat.python.cp_model")
        for _path, imported in ortools_imports
    ), "The planning solver must import the OR-Tools CP-SAT API."


def test_planning_solver_cannot_reach_infrastructure_world_state_or_llm_layers() -> None:
    violations = [
        f"{_relative(path)} imports {imported}"
        for path in _python_files(SOLVER_ROOT)
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in _SOLVER_FORBIDDEN_IMPORT_ROOTS)
    ]

    assert violations == []


def test_neutral_and_untrusted_layers_do_not_depend_on_ortools_or_concrete_solver() -> None:
    forbidden_roots = ("ortools", "ai_parametric_architect.planning.solver")
    violations = [
        f"{_relative(path)} imports {imported}"
        for layer in _ORTOOLS_FREE_LAYERS
        for path in _python_files(SOURCE_ROOT / layer)
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in forbidden_roots)
    ]

    assert violations == []


def test_planning_solver_avoids_brute_force_and_nondeterministic_sources() -> None:
    import_violations = [
        f"{_relative(path)} imports {imported}"
        for path in _python_files(SOLVER_ROOT)
        for imported in _imports(path)
        if any(_matches_root(imported, root) for root in _NONDETERMINISTIC_IMPORT_ROOTS)
    ]
    enumeration_violations = [
        f"{_relative(path)} uses itertools.{member}"
        for path in _python_files(SOLVER_ROOT)
        for member in sorted(_forbidden_itertools_uses(path))
    ]

    assert [*import_violations, *enumeration_violations] == []
