"""Provider-neutral ports for architecture requirement planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypeVar

from ai_parametric_architect.domain import DesignIntent, ModelRevision, PatchProposal

_FloorPlanT_co = TypeVar("_FloorPlanT_co", covariant=True)


class RequirementParser(Protocol):
    def parse(self, requirement: str) -> DesignIntent: ...


class ProposalPlanner(Protocol):
    def plan(self, intent: DesignIntent, base_revision: ModelRevision) -> PatchProposal | None: ...


class FloorPlanPlanner(Protocol[_FloorPlanT_co]):
    def plan(self, intent: DesignIntent) -> _FloorPlanT_co: ...


class LanguageModelAdapter(Protocol):
    """Legacy raw-payload compatibility port; prefer the typed ``llm.LLMProvider``."""

    def extract_design_intent(self, requirement: str) -> Mapping[str, object]: ...
