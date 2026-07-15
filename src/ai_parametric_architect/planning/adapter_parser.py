"""Validated compatibility bridge for the legacy raw-payload LLM port."""

from __future__ import annotations

from collections.abc import Mapping

from ai_parametric_architect.domain import (
    DesignIntent,
    InvalidDesignIntentError,
    RequirementParseError,
)
from ai_parametric_architect.ports import LanguageModelAdapter


class LanguageModelRequirementParser:
    """Convert provider-neutral adapter output into a trusted DesignIntent."""

    def __init__(self, adapter: LanguageModelAdapter) -> None:
        self._adapter = adapter

    def parse(self, requirement: str) -> DesignIntent:
        if not isinstance(requirement, str) or not requirement.strip():
            raise RequirementParseError(
                "Requirement text cannot be empty.",
                details={"reason": "EMPTY_REQUIREMENT"},
            )
        try:
            payload = self._adapter.extract_design_intent(requirement)
        except InvalidDesignIntentError as error:
            raise _wrap_invalid_intent(error) from error
        if not isinstance(payload, Mapping):
            raise RequirementParseError(
                "Language-model adapter must return an intent object.",
                details={"reason": "ADAPTER_OUTPUT_INVALID"},
            )
        try:
            return DesignIntent.from_dict(payload)
        except InvalidDesignIntentError as error:
            raise _wrap_invalid_intent(error) from error
        except (OverflowError, ValueError) as error:
            raise RequirementParseError(
                "Language-model adapter returned an invalid numeric value.",
                path="/area",
                details={
                    "reason": "ADAPTER_OUTPUT_INVALID",
                    "cause": "INVALID_DESIGN_INTENT",
                },
            ) from error


def _wrap_invalid_intent(error: InvalidDesignIntentError) -> RequirementParseError:
    return RequirementParseError(
        f"Language-model adapter returned an invalid intent: {error}",
        path=error.path,
        details={
            "reason": "ADAPTER_OUTPUT_INVALID",
            "cause": error.code,
            "cause_details": error.details,
        },
    )
