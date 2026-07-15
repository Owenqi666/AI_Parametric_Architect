"""Port reserved for derived BIM/CAD exporters."""

from __future__ import annotations

from typing import Protocol

from ai_parametric_architect.domain import ModelDocument


class ModelExporter(Protocol):
    media_type: str
    file_extension: str

    def export(self, model: ModelDocument) -> bytes: ...
