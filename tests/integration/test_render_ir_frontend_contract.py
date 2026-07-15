from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_parametric_architect.composition import create_service

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_frontend_example_is_the_backend_render_ir_projection() -> None:
    model = cast(
        dict[str, Any],
        json.loads(
            (PROJECT_ROOT / "examples" / "valid_simple_house.json").read_text(encoding="utf-8")
        ),
    )
    expected = create_service().render_ir(model).to_dict()
    actual = json.loads(
        (
            PROJECT_ROOT / "frontend" / "public" / "examples" / "simple-house.render-ir.json"
        ).read_text(encoding="utf-8")
    )

    assert actual == expected
