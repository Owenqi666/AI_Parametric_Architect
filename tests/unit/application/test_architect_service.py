from __future__ import annotations

from typing import Any

import pytest

from ai_parametric_architect.application import ArchitectService, ModelValidationError
from ai_parametric_architect.domain import ModelDocument, RenderIR
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.renderer import (
    SvgRenderer,
    WorldModelRenderIRProjector,
)
from ai_parametric_architect.validation import ModelValidator


class SpyRenderIRProjector:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self._delegate = WorldModelRenderIRProjector(ShapelyGeometryEngine())

    def project(self, model: ModelDocument, floor_id: str | None = None) -> RenderIR:
        self.calls.append(floor_id)
        return self._delegate.project(model, floor_id)


def _service(projector: SpyRenderIRProjector | None) -> ArchitectService:
    geometry = ShapelyGeometryEngine()
    return ArchitectService(
        ModelValidator(geometry),
        SvgRenderer(geometry),
        render_ir_projector=projector,
    )


def test_render_ir_validates_before_invoking_the_read_only_projector(
    invalid_opening: dict[str, Any],
) -> None:
    projector = SpyRenderIRProjector()

    with pytest.raises(ModelValidationError):
        _service(projector).render_ir(invalid_opening)

    assert projector.calls == []


def test_render_ir_delegates_with_the_requested_floor(
    valid_simple_house: dict[str, Any],
) -> None:
    projector = SpyRenderIRProjector()

    result = _service(projector).render_ir(valid_simple_house, "flr_ground")

    assert result.source_model.model_id == "mdl_simple_house"
    assert projector.calls == ["flr_ground"]


def test_render_ir_reports_missing_optional_projector_after_validation(
    valid_simple_house: dict[str, Any],
) -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        _service(None).render_ir(valid_simple_house)
