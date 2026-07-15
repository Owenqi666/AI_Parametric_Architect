"""Generate checked-in read-only artifacts from the authoritative showcase World Model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_parametric_architect.composition import create_service

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "examples" / "showcase_house.json"
RENDER_IR_PATH = PROJECT_ROOT / "frontend" / "public" / "examples" / "showcase-house.render-ir.json"
SVG_PATH = PROJECT_ROOT / "frontend" / "public" / "examples" / "showcase-house.svg"


def main() -> int:
    model = cast(dict[str, Any], json.loads(MODEL_PATH.read_text(encoding="utf-8")))
    service = create_service()
    render_ir = service.render_ir(model).to_dict()
    svg = service.render_svg(model, "flr_ground")
    RENDER_IR_PATH.write_text(
        json.dumps(render_ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    SVG_PATH.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
