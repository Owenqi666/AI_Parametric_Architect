"""Validation rule contracts."""

from __future__ import annotations

from enum import IntEnum
from typing import Protocol

from ai_parametric_architect.domain import (
    GeometryPrecisionPolicy,
    ModelDocument,
    ValidationIssue,
)
from ai_parametric_architect.ports import GeometryEngine


class ValidationLevel(IntEnum):
    BASIC_GEOMETRY = 1
    SPATIAL_RELATIONSHIPS = 2
    BUILDING_RULES = 3
    ENGINEERING_CONSTRAINTS = 4


class ValidationRule(Protocol):
    level: ValidationLevel
    name: str

    def evaluate(
        self,
        model: ModelDocument,
        geometry: GeometryEngine,
        precision: GeometryPrecisionPolicy,
    ) -> tuple[ValidationIssue, ...]: ...
