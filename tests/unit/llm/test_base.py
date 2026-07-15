from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast, get_type_hints

import pytest

from ai_parametric_architect.domain import DesignIntent, PatchProposal, PlanningError
from ai_parametric_architect.llm import (
    LLMConfigurationError,
    LLMContractError,
    LLMOutputKind,
    LLMProvider,
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderRefusalError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderTruncatedError,
    LLMProviderUnavailableError,
    StructuredPrompt,
)
from ai_parametric_architect.llm.base import (
    is_llm_output,
    output_type_for,
    require_matching_output,
)
from ai_parametric_architect.planning import FloorPlanProposal

from .helpers import make_intent, make_patch, make_plan


class EchoProvider:
    @property
    def name(self) -> str:
        return "echo"

    @property
    def version(self) -> str:
        return "1.0.0"

    def complete[OutputT: DesignIntent | FloorPlanProposal | PatchProposal](
        self,
        prompt: StructuredPrompt[OutputT],
    ) -> OutputT:
        value: object = {
            LLMOutputKind.DESIGN_INTENT: make_intent(),
            LLMOutputKind.FLOOR_PLAN_PROPOSAL: make_plan(),
            LLMOutputKind.PATCH_PROPOSAL: make_patch(),
        }[prompt.output_kind]
        return require_matching_output(prompt, value, provider_name=self.name)


def test_provider_protocol_is_runtime_checkable_and_fully_typed() -> None:
    provider = EchoProvider()
    annotations = get_type_hints(LLMProvider.complete)

    assert isinstance(provider, LLMProvider)
    assert annotations["prompt"] is not Any
    assert annotations["return"] is not Any


def test_output_kind_has_one_exact_immutable_value_type() -> None:
    assert output_type_for(LLMOutputKind.DESIGN_INTENT) is DesignIntent
    assert output_type_for(LLMOutputKind.FLOOR_PLAN_PROPOSAL) is FloorPlanProposal
    assert output_type_for(LLMOutputKind.PATCH_PROPOSAL) is PatchProposal
    assert is_llm_output(make_intent())
    assert is_llm_output(make_plan())
    assert is_llm_output(make_patch())
    assert not is_llm_output({"building_type": "house"})

    with pytest.raises(LLMContractError) as captured:
        output_type_for(cast(LLMOutputKind, "unknown"))

    assert captured.value.path == "/output_kind"


def test_structured_prompt_rejects_output_kind_and_type_mismatch() -> None:
    with pytest.raises(LLMContractError) as captured:
        StructuredPrompt(
            output_kind=LLMOutputKind.DESIGN_INTENT,
            output_type=cast(type[DesignIntent], FloorPlanProposal),
            system_prompt="system",
            user_prompt="user",
        )

    assert captured.value.to_dict() == {
        "code": "LLM_CONTRACT_VIOLATION",
        "path": "/output_type",
        "message": "Prompt output_type does not match output_kind.",
        "details": {
            "output_kind": "design_intent",
            "actual_type": "FloorPlanProposal",
            "expected_type": "DesignIntent",
        },
    }

    with pytest.raises(LLMContractError) as invalid_kind:
        StructuredPrompt(
            output_kind=cast(LLMOutputKind, "unknown"),
            output_type=DesignIntent,
            system_prompt="system",
            user_prompt="user",
        )

    assert invalid_kind.value.path == "/output_kind"


@pytest.mark.parametrize(
    ("system_prompt", "user_prompt", "path"),
    [("", "user", "/system_prompt"), ("system", "  ", "/user_prompt")],
)
def test_structured_prompt_requires_nonempty_messages(
    system_prompt: str,
    user_prompt: str,
    path: str,
) -> None:
    with pytest.raises(LLMContractError) as captured:
        StructuredPrompt(
            output_kind=LLMOutputKind.DESIGN_INTENT,
            output_type=DesignIntent,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    assert captured.value.path == path


def test_matching_output_contract_rejects_wrong_allowed_value() -> None:
    prompt = StructuredPrompt(
        output_kind=LLMOutputKind.DESIGN_INTENT,
        output_type=DesignIntent,
        system_prompt="system",
        user_prompt="user",
    )

    with pytest.raises(LLMContractError) as captured:
        require_matching_output(prompt, make_plan(), provider_name="test-provider")

    assert captured.value.details == {
        "provider": "test-provider",
        "output_kind": "design_intent",
        "actual_type": "FloorPlanProposal",
        "expected_type": "DesignIntent",
    }


@pytest.mark.parametrize(
    ("factory", "code", "message"),
    [
        (
            LLMConfigurationError,
            "LLM_CONFIGURATION_INVALID",
            "Language-model provider configuration is invalid.",
        ),
        (
            LLMProviderError,
            "LLM_PROVIDER_FAILED",
            "The language-model provider request failed.",
        ),
        (
            LLMProviderAuthenticationError,
            "LLM_PROVIDER_AUTHENTICATION_FAILED",
            "The language-model provider rejected its credentials.",
        ),
        (
            LLMProviderTimeoutError,
            "LLM_PROVIDER_TIMEOUT",
            "The language-model provider request timed out.",
        ),
        (
            LLMProviderRateLimitError,
            "LLM_PROVIDER_RATE_LIMITED",
            "The language-model provider rate limit was exceeded.",
        ),
        (
            LLMProviderUnavailableError,
            "LLM_PROVIDER_UNAVAILABLE",
            "The language-model provider is unavailable.",
        ),
        (
            LLMProviderRefusalError,
            "LLM_PROVIDER_REFUSED",
            "The language-model provider refused the request.",
        ),
        (
            LLMProviderTruncatedError,
            "LLM_PROVIDER_TRUNCATED",
            "The language-model provider returned an incomplete response.",
        ),
        (
            LLMProviderResponseError,
            "LLM_PROVIDER_RESPONSE_INVALID",
            "The language-model provider returned an invalid response.",
        ),
    ],
)
def test_provider_errors_use_stable_sanitized_messages(
    factory: Callable[..., PlanningError],
    code: str,
    message: str,
) -> None:
    error = factory()

    assert error.to_dict() == {
        "code": code,
        "path": "",
        "message": message,
        "details": {},
    }
    assert "vendor-secret-response" not in str(error)
    with pytest.raises(TypeError):
        cast(Callable[[str], PlanningError], factory)("vendor-secret-response")


def test_provider_error_defensively_copies_allowlisted_details() -> None:
    details: dict[str, object] = {
        "provider": "openai",
        "reason": "UPSTREAM_UNAVAILABLE",
    }
    error = LLMProviderUnavailableError(path="/provider", details=details)

    details["reason"] = "mutated"

    assert error.to_dict() == {
        "code": "LLM_PROVIDER_UNAVAILABLE",
        "path": "/provider",
        "message": "The language-model provider is unavailable.",
        "details": {
            "provider": "openai",
            "reason": "UPSTREAM_UNAVAILABLE",
        },
    }
