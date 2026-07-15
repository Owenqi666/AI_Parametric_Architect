from __future__ import annotations

from typing import cast

import pytest

from ai_parametric_architect.domain import DesignIntent
from ai_parametric_architect.llm import (
    MOCK_LLM_PROVIDER_NAME,
    MOCK_LLM_PROVIDER_VERSION,
    LLMContractError,
    LLMProvider,
    MockLLMProvider,
    design_intent_prompt,
    floor_plan_suggestion_prompt,
    patch_proposal_prompt,
)
from ai_parametric_architect.llm.base import LLMOutput

from .helpers import make_intent, make_patch, make_plan, make_revision


class DesignIntentSubclass(DesignIntent):
    pass


def test_mock_provider_returns_all_allowed_outputs_in_stable_order() -> None:
    intent = make_intent()
    plan = make_plan()
    patch = make_patch()
    responses: list[LLMOutput] = [intent, plan, patch]
    provider = MockLLMProvider(responses)
    intent_prompt = design_intent_prompt("Design a 120 sqm two-room house")
    plan_prompt = floor_plan_suggestion_prompt(intent)
    patch_prompt = patch_proposal_prompt(plan, make_revision())

    responses.clear()

    assert isinstance(provider, LLMProvider)
    assert provider.name == MOCK_LLM_PROVIDER_NAME == "mock-llm-provider"
    assert provider.version == MOCK_LLM_PROVIDER_VERSION == "1.0.0"
    assert provider.complete(intent_prompt) is intent
    assert provider.complete(plan_prompt) is plan
    assert provider.complete(patch_prompt) is patch
    assert provider.requests == (intent_prompt, plan_prompt, patch_prompt)
    assert provider.remaining_responses == 0


def test_mock_provider_rejects_response_kind_mismatch() -> None:
    provider = MockLLMProvider([make_plan()])

    with pytest.raises(LLMContractError) as captured:
        provider.complete(design_intent_prompt("Design a house"))

    assert captured.value.to_dict() == {
        "code": "LLM_CONTRACT_VIOLATION",
        "path": "/output",
        "message": ("LLM provider returned a value that does not match the requested output type."),
        "details": {
            "provider": "mock-llm-provider",
            "output_kind": "design_intent",
            "actual_type": "FloorPlanProposal",
            "expected_type": "DesignIntent",
        },
    }
    assert len(provider.requests) == 1
    assert provider.remaining_responses == 0


def test_mock_provider_reports_response_exhaustion_without_recording_request() -> None:
    provider = MockLLMProvider([])

    with pytest.raises(LLMContractError) as captured:
        provider.complete(design_intent_prompt("Design a house"))

    assert captured.value.path == "/responses"
    assert captured.value.details["reason"] == "RESPONSES_EXHAUSTED"
    assert provider.requests == ()


def test_mock_provider_rejects_arbitrary_outputs_and_untyped_prompts() -> None:
    with pytest.raises(LLMContractError) as invalid_response:
        MockLLMProvider(cast("list[LLMOutput]", [{"area": 120}]))

    assert invalid_response.value.path == "/responses/0"

    provider = MockLLMProvider([make_intent()])
    with pytest.raises(LLMContractError) as invalid_prompt:
        provider.complete(cast("object", {"prompt": "unsafe"}))  # type: ignore[arg-type]

    assert invalid_prompt.value.path == "/prompt"
    assert provider.remaining_responses == 1


def test_mock_provider_rejects_subclasses_of_allowed_values() -> None:
    subclass = DesignIntentSubclass(
        building_type="house",
        area=50,
        rooms=("living",),
    )

    with pytest.raises(LLMContractError) as captured:
        MockLLMProvider(cast("list[LLMOutput]", [subclass]))

    assert captured.value.path == "/responses/0"
    assert captured.value.details == {"actual_type": "DesignIntentSubclass"}


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        ({"name": " "}, "/name"),
        ({"version": ""}, "/version"),
    ],
)
def test_mock_provider_requires_observable_identity(
    arguments: dict[str, str],
    path: str,
) -> None:
    with pytest.raises(LLMContractError) as captured:
        MockLLMProvider([make_intent()], **arguments)

    assert captured.value.path == path


def test_mock_provider_has_no_write_capability_or_dynamic_attributes() -> None:
    provider = MockLLMProvider([make_intent()])

    assert not hasattr(provider, "repository")
    assert not hasattr(provider, "commit")
    assert not hasattr(provider, "mutate")
    assert not hasattr(provider, "__dict__")
    with pytest.raises(AttributeError):
        provider.repository = object()  # type: ignore[attr-defined]


def test_generic_provider_result_retains_precise_static_value_type() -> None:
    provider = MockLLMProvider([make_intent()])
    result: DesignIntent = provider.complete(design_intent_prompt("Design a house"))

    assert result == make_intent()
