"""Stable ports for infrastructure and future integrations."""

from ai_parametric_architect.ports.clock import Clock
from ai_parametric_architect.ports.exporter import ModelExporter
from ai_parametric_architect.ports.geometry import GeometryEngine
from ai_parametric_architect.ports.patch_generation import PatchProposalGenerator
from ai_parametric_architect.ports.patching import PatchEngine
from ai_parametric_architect.ports.planning import (
    FloorPlanPlanner,
    LanguageModelAdapter,
    ProposalPlanner,
    RequirementParser,
)
from ai_parametric_architect.ports.reasoning import ConstraintSolver
from ai_parametric_architect.ports.rendering import (
    FloorNotFoundError,
    NoRenderableGeometryError,
    Renderer,
    RenderError,
    RenderIRProjector,
)
from ai_parametric_architect.ports.repository import RevisionRepository
from ai_parametric_architect.ports.validation import Validator

__all__ = [
    "Clock",
    "ConstraintSolver",
    "FloorNotFoundError",
    "FloorPlanPlanner",
    "GeometryEngine",
    "LanguageModelAdapter",
    "ModelExporter",
    "NoRenderableGeometryError",
    "PatchEngine",
    "PatchProposalGenerator",
    "ProposalPlanner",
    "RenderError",
    "RenderIRProjector",
    "Renderer",
    "RequirementParser",
    "RevisionRepository",
    "Validator",
]
