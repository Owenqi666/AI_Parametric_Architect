"""Deterministic model-validation port."""

from __future__ import annotations

from typing import Protocol

from ai_parametric_architect.domain import ModelDocument, ValidationReport


class Validator(Protocol):
    def validate(self, model: ModelDocument) -> ValidationReport: ...
