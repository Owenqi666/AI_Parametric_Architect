"""Deterministic application use cases."""

from __future__ import annotations

from ai_parametric_architect.application.errors import ModelValidationError
from ai_parametric_architect.domain import ModelDocument, RenderIR, ValidationReport
from ai_parametric_architect.ports import Renderer, RenderIRProjector, Validator


class ArchitectService:
    def __init__(
        self,
        validator: Validator,
        renderer: Renderer,
        render_ir_projector: RenderIRProjector | None = None,
    ) -> None:
        self._validator = validator
        self._renderer = renderer
        self._render_ir_projector = render_ir_projector

    def validate(self, model: ModelDocument) -> ValidationReport:
        return self._validator.validate(model)

    def render_svg(self, model: ModelDocument, floor_id: str | None = None) -> str:
        report = self.validate(model)
        if not report.valid:
            raise ModelValidationError(report)
        return self._renderer.render(model, floor_id)

    def render_ir(self, model: ModelDocument, floor_id: str | None = None) -> RenderIR:
        report = self.validate(model)
        if not report.valid:
            raise ModelValidationError(report)
        if self._render_ir_projector is None:
            raise RuntimeError("Render IR projection is not configured")
        return self._render_ir_projector.project(model, floor_id)
