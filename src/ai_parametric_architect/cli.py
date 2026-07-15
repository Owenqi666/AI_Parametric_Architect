"""Command-line interface for deterministic validation and SVG rendering."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ai_parametric_architect.application import (
    ModelDocumentDecodeError,
    ModelValidationError,
    load_model_document,
)
from ai_parametric_architect.composition import create_service
from ai_parametric_architect.ports import FloorNotFoundError, NoRenderableGeometryError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-architect")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a building JSON document")
    validate.add_argument("model", type=Path)

    render = commands.add_parser("render-svg", help="render a validated floor to SVG")
    render.add_argument("model", type=Path)
    render.add_argument("output", type=Path)
    render.add_argument("--floor-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        model = load_model_document(arguments.model)
    except (FileNotFoundError, ModelDocumentDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    service = create_service()
    if arguments.command == "validate":
        report = service.validate(model)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report.valid else 1

    try:
        svg = service.render_svg(model, arguments.floor_id)
    except ModelValidationError as exc:
        print(
            json.dumps(exc.report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    except (FloorNotFoundError, NoRenderableGeometryError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    arguments.output.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
