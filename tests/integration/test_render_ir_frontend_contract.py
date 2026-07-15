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


def test_frontend_svg_example_is_the_backend_projection() -> None:
    model = cast(
        dict[str, Any],
        json.loads(
            (PROJECT_ROOT / "examples" / "valid_simple_house.json").read_text(encoding="utf-8")
        ),
    )
    expected = create_service().render_svg(model)
    actual = (PROJECT_ROOT / "frontend" / "public" / "examples" / "simple-house.svg").read_text(
        encoding="utf-8"
    )

    assert actual == expected


def test_showcase_examples_are_backend_projections() -> None:
    model = cast(
        dict[str, Any],
        json.loads((PROJECT_ROOT / "examples" / "showcase_house.json").read_text(encoding="utf-8")),
    )
    service = create_service()
    expected_render_ir = service.render_ir(model).to_dict()
    actual_render_ir = json.loads(
        (
            PROJECT_ROOT / "frontend" / "public" / "examples" / "showcase-house.render-ir.json"
        ).read_text(encoding="utf-8")
    )
    expected_svg = service.render_svg(model, "flr_ground")
    actual_svg = (
        PROJECT_ROOT / "frontend" / "public" / "examples" / "showcase-house.svg"
    ).read_text(encoding="utf-8")

    assert actual_render_ir == expected_render_ir
    assert actual_svg == expected_svg
