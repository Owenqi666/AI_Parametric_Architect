"""Infrastructure-neutral aliases for the authoritative JSON document."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

type ModelDocument = Mapping[str, Any]
type Entity = Mapping[str, Any]
type Point2 = tuple[float, float]
type Ring2 = tuple[Point2, ...]
