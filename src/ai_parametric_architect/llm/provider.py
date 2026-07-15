"""Concrete provider-neutral test adapters; no network provider is configured here."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.revisions import ModelRevision
from ai_parametric_architect.llm.base import (
    LLMContractError,
    LLMOutput,
    LLMProvider,
    StructuredPrompt,
    is_llm_output,
    require_matching_output,
)
from ai_parametric_architect.llm.prompts import (
    design_intent_prompt,
    floor_plan_suggestion_prompt,
    patch_proposal_prompt,
)
from ai_parametric_architect.planning.models import FloorPlanProposal

MOCK_LLM_PROVIDER_NAME: Final = "mock-llm-provider"
MOCK_LLM_PROVIDER_VERSION: Final = "1.0.0"


class MockLLMProvider:
    """A deterministic in-memory queue of already typed LLM suggestions."""

    __slots__ = ("_cursor", "_name", "_requests", "_responses", "_version")

    def __init__(
        self,
        responses: Sequence[LLMOutput],
        *,
        name: str = MOCK_LLM_PROVIDER_NAME,
        version: str = MOCK_LLM_PROVIDER_VERSION,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise LLMContractError("Provider name must be a non-empty string.", path="/name")
        if not isinstance(version, str) or not version.strip():
            raise LLMContractError("Provider version must be a non-empty string.", path="/version")
        validated: list[LLMOutput] = []
        for index, response in enumerate(responses):
            if not is_llm_output(response):
                raise LLMContractError(
                    "Mock responses must use an allowed immutable LLM output type.",
                    path=f"/responses/{index}",
                    details={"actual_type": type(response).__name__},
                )
            validated.append(response)

        self._name = name
        self._version = version
        self._responses = tuple(validated)
        self._requests: list[StructuredPrompt[LLMOutput]] = []
        self._cursor = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def requests(self) -> tuple[StructuredPrompt[LLMOutput], ...]:
        """Expose an immutable observable request history for tests and traces."""

        return tuple(self._requests)

    @property
    def remaining_responses(self) -> int:
        return len(self._responses) - self._cursor

    def complete[OutputT: LLMOutput](self, prompt: StructuredPrompt[OutputT]) -> OutputT:
        if not isinstance(prompt, StructuredPrompt):
            raise LLMContractError(
                "Provider input must be a StructuredPrompt.",
                path="/prompt",
                details={"actual_type": type(prompt).__name__},
            )
        if self._cursor >= len(self._responses):
            raise LLMContractError(
                "Mock LLM provider has no response remaining.",
                path="/responses",
                details={"provider": self.name, "reason": "RESPONSES_EXHAUSTED"},
            )

        response = self._responses[self._cursor]
        self._cursor += 1
        self._requests.append(prompt)
        return require_matching_output(prompt, response, provider_name=self.name)


@dataclass(frozen=True, slots=True)
class LLMRequirementParser:
    """Adapt typed provider completion to the existing RequirementParser port."""

    _provider: LLMProvider = field(repr=False)

    def parse(self, requirement: str) -> DesignIntent:
        return _complete(self._provider, design_intent_prompt(requirement))


@dataclass(frozen=True, slots=True)
class LLMFloorPlanPlanner:
    """Adapt typed provider completion to the existing FloorPlanPlanner port."""

    _provider: LLMProvider = field(repr=False)

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        return _complete(self._provider, floor_plan_suggestion_prompt(intent))


@dataclass(frozen=True, slots=True)
class LLMPatchProposalGenerator:
    """Adapt typed provider completion to detached Patch proposal generation."""

    _provider: LLMProvider = field(repr=False)

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal:
        return _complete(self._provider, patch_proposal_prompt(plan, current_revision))


def _complete[OutputT: LLMOutput](
    provider: LLMProvider,
    prompt: StructuredPrompt[OutputT],
) -> OutputT:
    value = provider.complete(prompt)
    return require_matching_output(prompt, value, provider_name=provider.name)
