"""Read-only renderer port."""

from __future__ import annotations

from typing import Protocol

from ai_parametric_architect.domain import ModelDocument, RenderIR


class RenderError(ValueError):
    """Base failure exposed by a read-only rendering adapter."""


class FloorNotFoundError(RenderError):
    """Raised when a requested floor is not part of the root building."""


class NoRenderableGeometryError(RenderError):
    """Raised when a selected floor has no geometry to derive an output from."""


class Renderer(Protocol):
    media_type: str

    def render(self, model: ModelDocument, floor_id: str | None = None) -> str: ...


class RenderIRProjector(Protocol):
    """Project validated world-model geometry into an immutable visualization value."""

    def project(self, model: ModelDocument, floor_id: str | None = None) -> RenderIR: ...
