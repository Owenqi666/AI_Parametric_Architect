"""Fail when the built wheel omits the authoritative JSON Schema resource."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from zipfile import ZipFile

EXPECTED_SCHEMAS = {
    "ai_parametric_architect/contracts/schemas/model-1.0.0.schema.json": (
        "https://schemas.ai-parametric-architect.dev/model/1.0.0.json"
    ),
    "ai_parametric_architect/intent/schemas/design-intent-1.0.0.schema.json": (
        "https://schemas.ai-parametric-architect.dev/design-intent/1.0.0.json"
    ),
}


def main() -> int:
    wheels = sorted(Path("dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one wheel in dist, found {len(wheels)}")

    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        for expected_schema, expected_id in EXPECTED_SCHEMAS.items():
            if expected_schema not in names:
                raise SystemExit(f"Wheel does not contain {expected_schema}")
            packaged_bytes = archive.read(expected_schema)
            source_schema = Path("src") / expected_schema
            if packaged_bytes != source_schema.read_bytes():
                raise SystemExit(f"Packaged schema differs from source resource: {expected_schema}")
            schema = cast(dict[str, Any], json.loads(packaged_bytes))
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise SystemExit(f"Packaged schema is not Draft 2020-12: {expected_schema}")
            if schema.get("$id") != expected_id:
                raise SystemExit(f"Packaged schema has the wrong versioned $id: {expected_schema}")
    print(f"Verified {len(EXPECTED_SCHEMAS)} packaged schemas in {wheels[0].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
