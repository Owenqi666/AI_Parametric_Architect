"""Generate deterministic proposal previews and an offline planning benchmark report."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ai_parametric_architect.showcase_generation import (
    DEFAULT_BENCHMARK_OUTPUT,
    DEFAULT_PREVIEW_OUTPUT,
    build_benchmark_report,
    build_preview_artifact,
)


def write_json(path: Path, value: object) -> None:
    if not path.parent.is_dir():
        raise OSError(f"Output parent does not exist: {path.parent}")
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(f"{encoded}\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-output", type=Path, default=DEFAULT_PREVIEW_OUTPUT)
    parser.add_argument("--benchmark-output", type=Path, default=DEFAULT_BENCHMARK_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    write_json(arguments.preview_output, build_preview_artifact().to_dict())
    write_json(arguments.benchmark_output, build_benchmark_report().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
