from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


def load_example(name: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "examples" / name
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
def valid_simple_house() -> dict[str, Any]:
    return copy.deepcopy(load_example("valid_simple_house.json"))


@pytest.fixture
def invalid_overlap() -> dict[str, Any]:
    return copy.deepcopy(load_example("invalid_overlap.json"))


@pytest.fixture
def invalid_opening() -> dict[str, Any]:
    return copy.deepcopy(load_example("invalid_opening.json"))
