"""Provider-neutral contracts for structured language-model output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeGuard, runtime_checkable

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.planning_errors import PlanningError
from ai_parametric_architect.planning.models import FloorPlanProposal

type LLMOutput = DesignIntent | FloorPlanProposal | PatchProposal


class LLMOutputKind(StrEnum):
    """The complete set of values an LLM adapter may return."""

    DESIGN_INTENT = "design_intent"
    FLOOR_PLAN_PROPOSAL = "floor_plan_proposal"
    PATCH_PROPOSAL = "patch_proposal"


class LLMContractError(PlanningError):
    """Raised when a provider or prompt violates the typed LLM boundary."""

    code = "LLM_CONTRACT_VIOLATION"


@dataclass(frozen=True, slots=True)
class StructuredPrompt[OutputT: LLMOutput]:
    """A prompt whose expected immutable output is explicit and runtime-checkable."""

    output_kind: LLMOutputKind
    output_type: type[OutputT]
    system_prompt: str
    user_prompt: str

    def __post_init__(self) -> None:
        if not isinstance(self.output_kind, LLMOutputKind):
            raise LLMContractError(
                "Prompt output_kind is unsupported.",
                path="/output_kind",
                details={"actual_type": type(self.output_kind).__name__},
            )
        expected_type = output_type_for(self.output_kind)
        if self.output_type is not expected_type:
            raise LLMContractError(
                "Prompt output_type does not match output_kind.",
                path="/output_type",
                details={
                    "output_kind": self.output_kind.value,
                    "actual_type": getattr(
                        self.output_type,
                        "__name__",
                        type(self.output_type).__name__,
                    ),
                    "expected_type": expected_type.__name__,
                },
            )
        _require_prompt_text(self.system_prompt, "/system_prompt")
        _require_prompt_text(self.user_prompt, "/user_prompt")


@runtime_checkable
class LLMProvider(Protocol):
    """Generate one typed suggestion without tools, mutation, or commit authority."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def complete[OutputT: LLMOutput](self, prompt: StructuredPrompt[OutputT]) -> OutputT: ...


def output_type_for(kind: LLMOutputKind) -> type[LLMOutput]:
    """Return the sole permitted concrete value class for an output kind."""

    if kind is LLMOutputKind.DESIGN_INTENT:
        return DesignIntent
    if kind is LLMOutputKind.FLOOR_PLAN_PROPOSAL:
        return FloorPlanProposal
    if kind is LLMOutputKind.PATCH_PROPOSAL:
        return PatchProposal
    raise LLMContractError(
        "LLM output kind is unsupported.",
        path="/output_kind",
        details={"actual_type": type(kind).__name__},
    )


def is_llm_output(value: object) -> TypeGuard[LLMOutput]:
    """Recognize only exact immutable architecture output value classes."""

    return type(value) in {DesignIntent, FloorPlanProposal, PatchProposal}


def require_matching_output[OutputT: LLMOutput](
    prompt: StructuredPrompt[OutputT],
    value: object,
    *,
    provider_name: str,
) -> OutputT:
    """Enforce a provider response against its prompt's exact output contract."""

    if type(value) is not prompt.output_type:
        raise LLMContractError(
            "LLM provider returned a value that does not match the requested output type.",
            path="/output",
            details={
                "provider": provider_name,
                "output_kind": prompt.output_kind.value,
                "actual_type": type(value).__name__,
                "expected_type": prompt.output_type.__name__,
            },
        )
    return value


def _require_prompt_text(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise LLMContractError("Prompt messages must be non-empty strings.", path=path)
