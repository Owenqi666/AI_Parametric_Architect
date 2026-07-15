"""Strict JSON document input."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn, cast


class ModelDocumentDecodeError(ValueError):
    """Raised when an input file is not a standards-compliant JSON object."""


def _reject_non_finite_json(value: str) -> NoReturn:
    raise ModelDocumentDecodeError(f"Non-finite JSON number is not allowed: {value}")


def load_model_document(path: Path) -> dict[str, Any]:
    """Load a JSON object while rejecting non-standard NaN/Infinity tokens."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_non_finite_json,
        )
    except json.JSONDecodeError as exc:
        raise ModelDocumentDecodeError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ModelDocumentDecodeError("Model document root must be a JSON object")
    return cast(dict[str, Any], value)
