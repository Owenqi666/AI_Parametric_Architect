from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import OpenAI

from ai_parametric_architect.domain import DesignIntent
from ai_parametric_architect.infrastructure.llm import (
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
)
from ai_parametric_architect.llm import (
    LLMConfigurationError,
    LLMContractError,
    LLMProviderRateLimitError,
    LLMProviderRefusalError,
    LLMProviderResponseError,
    LLMProviderTruncatedError,
    LLMProviderUnavailableError,
    design_intent_output_schema,
    design_intent_prompt,
)

VALID_PAYLOAD: dict[str, object] = {
    "building_type": "house",
    "area": 90,
    "rooms": ["living", "bedroom"],
    "orientation": None,
    "spatial_constraints": [],
}


def _completed_response(text: str) -> object:
    block = SimpleNamespace(type="output_text", text=text)
    message = SimpleNamespace(
        type="message",
        role="assistant",
        status="completed",
        content=[block],
    )
    return SimpleNamespace(status="completed", error=None, output=[message])


class _FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(deepcopy(kwargs))
        return self.response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.responses = _FakeResponses(response)


def _fake_provider(
    response: object,
    *,
    config: OpenAIProviderConfig | None = None,
) -> tuple[OpenAIResponsesProvider, _FakeClient]:
    client = _FakeClient(response)
    provider = OpenAIResponsesProvider(
        OpenAIProviderConfig(model="gpt-test") if config is None else config,
        client=client,
    )
    return provider, client


def test_success_uses_one_bounded_tool_free_strict_request_and_returns_exact_intent() -> None:
    provider, client = _fake_provider(_completed_response(json.dumps(VALID_PAYLOAD)))

    result = provider.complete(design_intent_prompt("Create a 90 sqm house"))

    assert type(result) is DesignIntent
    assert result == DesignIntent(
        building_type="house",
        area=90,
        rooms=("living", "bedroom"),
        orientation=None,
    )
    assert len(client.responses.calls) == 1
    request = client.responses.calls[0]
    assert request == {
        "model": "gpt-test",
        "input": [
            {"role": "developer", "content": design_intent_prompt("x").system_prompt},
            {
                "role": "user",
                "content": (
                    'Untrusted requirement JSON:\n{"input_requirement":"Create a 90 sqm house"}'
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "design_intent_1_0_0",
                "schema": design_intent_output_schema(),
                "strict": True,
            }
        },
        "max_output_tokens": 2048,
        "store": False,
        "tools": [],
        "truncation": "disabled",
        "timeout": 30.0,
    }


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("model", "", "MODEL_INVALID"),
        ("model", " gpt-test", "MODEL_INVALID"),
        ("model", "gpt/test", "MODEL_INVALID"),
        ("timeout_seconds", True, "TIMEOUT_INVALID"),
        ("timeout_seconds", float("nan"), "TIMEOUT_INVALID"),
        ("timeout_seconds", 0.99, "TIMEOUT_INVALID"),
        ("timeout_seconds", 121, "TIMEOUT_INVALID"),
        ("max_retries", -1, "RETRY_BUDGET_INVALID"),
        ("max_retries", 3, "RETRY_BUDGET_INVALID"),
        ("max_output_tokens", 127, "OUTPUT_TOKEN_BUDGET_INVALID"),
        ("max_output_tokens", 4097, "OUTPUT_TOKEN_BUDGET_INVALID"),
        ("max_input_bytes", 1023, "INPUT_BYTE_BUDGET_INVALID"),
        ("max_response_bytes", 262_145, "RESPONSE_BYTE_BUDGET_INVALID"),
    ],
)
def test_configuration_is_strict_and_sanitized(field: str, value: object, reason: str) -> None:
    values: dict[str, object] = {"model": "gpt-test"}
    values[field] = value

    with pytest.raises(LLMConfigurationError) as captured:
        OpenAIProviderConfig(**cast(Any, values))

    assert captured.value.details == {"provider": "openai-responses", "reason": reason}
    if str(value):
        assert str(value) not in str(captured.value)


def test_config_and_provider_use_slots_and_do_not_contain_credentials() -> None:
    marker = "sk-secret-marker"
    config = OpenAIProviderConfig(model="gpt-test", max_retries=0)
    provider, _client = _fake_provider(
        _completed_response(json.dumps(VALID_PAYLOAD)),
        config=config,
    )

    assert not hasattr(config, "__dict__")
    assert not hasattr(provider, "__dict__")
    assert not hasattr(config, "api_key")
    assert not hasattr(provider, "api_key")
    assert marker not in repr(config)
    assert marker not in repr(provider)


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "null",
        "```json\n{}\n```",
        json.dumps(VALID_PAYLOAD) + " trailing",
        '{"building_type":"house","area":90,"area":80,"rooms":["living"],'
        '"orientation":null,"spatial_constraints":[]}',
        '{"building_type":"house","area":NaN,"rooms":["living"],'
        '"orientation":null,"spatial_constraints":[]}',
        json.dumps({key: value for key, value in VALID_PAYLOAD.items() if key != "orientation"}),
        json.dumps({**VALID_PAYLOAD, "geometry": {"x": 1}}),
        json.dumps({**VALID_PAYLOAD, "area": True}),
        json.dumps({**VALID_PAYLOAD, "rooms": []}),
        json.dumps(
            {
                **VALID_PAYLOAD,
                "spatial_constraints": [
                    {
                        "source_room_type": "garage",
                        "relation": "near",
                        "target_room_type": "living",
                        "required": True,
                    }
                ],
            }
        ),
        json.dumps(
            {
                **VALID_PAYLOAD,
                "spatial_constraints": [
                    {
                        "source_room_type": "living",
                        "relation": "near",
                        "target_room_type": "bedroom",
                        "required": True,
                    }
                ]
                * 2,
            }
        ),
    ],
)
def test_malformed_or_semantically_invalid_output_fails_local_validation(text: str) -> None:
    provider, _client = _fake_provider(_completed_response(text))

    with pytest.raises(LLMProviderResponseError) as captured:
        provider.complete(design_intent_prompt("Create a house"))

    assert captured.value.code == "LLM_PROVIDER_RESPONSE_INVALID"
    assert "Create a house" not in str(captured.value.to_dict())


def test_response_byte_budget_is_checked_before_json_decoding() -> None:
    config = OpenAIProviderConfig(model="gpt-test", max_response_bytes=1024)
    provider, _client = _fake_provider(_completed_response("x" * 1025), config=config)

    with pytest.raises(LLMProviderResponseError) as captured:
        provider.complete(design_intent_prompt("Create a house"))

    assert captured.value.details["reason"] == "RESPONSE_TOO_LARGE"


def test_prompt_byte_budget_fails_before_a_network_call() -> None:
    config = OpenAIProviderConfig(model="gpt-test", max_input_bytes=1024)
    provider, client = _fake_provider(
        _completed_response(json.dumps(VALID_PAYLOAD)),
        config=config,
    )

    with pytest.raises(LLMContractError) as captured:
        provider.complete(design_intent_prompt("x" * 2000))

    assert captured.value.details["reason"] == "INPUT_TOO_LARGE"
    assert client.responses.calls == []


def test_refusal_and_incomplete_responses_fail_closed_without_disclosing_text() -> None:
    refusal = SimpleNamespace(type="refusal", refusal="secret refusal body")
    refused_message = SimpleNamespace(
        type="message",
        role="assistant",
        status="completed",
        content=[refusal],
    )
    cases = [
        SimpleNamespace(status="completed", error=None, output=[refused_message]),
        SimpleNamespace(
            status="incomplete",
            error=None,
            incomplete_details=SimpleNamespace(reason="content_filter"),
            output=[],
        ),
    ]

    for response in cases:
        provider, _client = _fake_provider(response)
        with pytest.raises(LLMProviderRefusalError) as captured:
            provider.complete(design_intent_prompt("secret requirement"))
        assert "secret" not in str(captured.value.to_dict())

    truncated, _client = _fake_provider(
        SimpleNamespace(
            status="incomplete",
            error=None,
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            output=[],
        )
    )
    with pytest.raises(LLMProviderTruncatedError):
        truncated.complete(design_intent_prompt("Create a house"))


@pytest.mark.parametrize(
    "output",
    [
        [],
        [SimpleNamespace(type="tool_call")],
        [
            cast(Any, _completed_response(json.dumps(VALID_PAYLOAD))).output[0],
            cast(Any, _completed_response(json.dumps(VALID_PAYLOAD))).output[0],
        ],
    ],
)
def test_ambiguous_or_tool_output_is_rejected(output: list[object]) -> None:
    provider, _client = _fake_provider(
        SimpleNamespace(status="completed", error=None, output=output)
    )

    with pytest.raises(LLMProviderResponseError):
        provider.complete(design_intent_prompt("Create a house"))


def _sdk_response(payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1.0,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 2048,
        "model": "gpt-test",
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload),
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": None,
        "store": False,
        "temperature": None,
        "text": {"format": {"type": "json_schema"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "truncation": "disabled",
        "usage": None,
    }


def test_actual_sdk_serializes_the_responses_request_without_external_network() -> None:
    observed: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(cast(dict[str, object], json.loads(request.content)))
        return httpx.Response(200, json=_sdk_response(VALID_PAYLOAD))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        sdk_client = OpenAI(
            api_key="test-only-key",
            base_url="https://openai.invalid/v1",
            http_client=http_client,
            max_retries=0,
        )
        provider = OpenAIResponsesProvider(
            OpenAIProviderConfig(model="gpt-test"),
            client=cast(Any, sdk_client),
        )

        intent = provider.complete(design_intent_prompt("Create a 90 sqm house"))

    assert intent.area == 90
    assert len(observed) == 1
    body = observed[0]
    assert body["store"] is False
    assert body["tools"] == []
    assert body["truncation"] == "disabled"
    assert cast(dict[str, Any], body["text"])["format"]["strict"] is True


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(429, LLMProviderRateLimitError), (500, LLMProviderUnavailableError)],
)
def test_actual_sdk_status_failures_are_sanitized_and_not_retried(
    status: int,
    error_type: type[Exception],
) -> None:
    marker = "upstream-secret-marker"
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            headers={"x-request-id": marker},
            json={
                "error": {
                    "message": marker,
                    "type": "rate_limit_error" if status == 429 else "server_error",
                    "param": None,
                    "code": None,
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        sdk_client = OpenAI(
            api_key="test-only-key",
            base_url="https://openai.invalid/v1",
            http_client=http_client,
            max_retries=0,
        )
        provider = OpenAIResponsesProvider(
            OpenAIProviderConfig(model="gpt-test"),
            client=cast(Any, sdk_client),
        )
        with pytest.raises(error_type) as captured:
            provider.complete(design_intent_prompt("Create a house"))

    assert calls == 1
    assert marker not in str(captured.value)
    assert marker not in str(cast(Any, captured.value).to_dict())
    assert captured.value.__cause__ is None
    assert captured.value.__suppress_context__
