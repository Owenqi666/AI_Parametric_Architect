"""Enforce a branch-only coverage threshold from Coverage.py JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

COVERAGE_REPORT = Path("coverage.json")
MINIMUM_BRANCH_COVERAGE = 85.0


def main() -> int:
    payload = cast(dict[str, Any], json.loads(COVERAGE_REPORT.read_text(encoding="utf-8")))
    totals = cast(dict[str, Any], payload["totals"])
    covered = int(totals["covered_branches"])
    total = int(totals["num_branches"])
    if total == 0:
        raise SystemExit("Coverage report contains no branches")

    percentage = covered / total * 100
    if percentage < MINIMUM_BRANCH_COVERAGE:
        raise SystemExit(
            f"Branch coverage {percentage:.2f}% is below {MINIMUM_BRANCH_COVERAGE:.2f}%"
        )
    print(f"Branch coverage: {covered}/{total} ({percentage:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
