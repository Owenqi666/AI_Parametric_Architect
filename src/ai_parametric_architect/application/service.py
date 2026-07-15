"""Deterministic application use cases."""

from __future__ import annotations

from ai_parametric_architect.application.errors import ModelValidationError
from ai_parametric_architect.domain import ModelDocument, ValidationReport
from ai_parametric_architect.ports import Renderer, Validator


class ArchitectService:
    def __init__(self, validator: Validator, renderer: Renderer) -> None:
        self._validator = validator
        self._renderer = renderer

    def validate(self, model: ModelDocument) -> ValidationReport:
        return self._validator.validate(model)

    def render_svg(self, model: ModelDocument, floor_id: str | None = None) -> str:
        report = self.validate(model)
        if not report.valid:
            raise ModelValidationError(report)
        return self._renderer.render(model, floor_id)
