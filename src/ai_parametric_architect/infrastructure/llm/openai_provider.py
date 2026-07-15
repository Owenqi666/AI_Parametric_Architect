"""OpenAI Responses API adapter for validated DesignIntent extraction only."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, Final, Protocol, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError
from ai_parametric_architect.intent import IntentValidator
from ai_parametric_architect.llm.base import (
    LLMConfigurationError,
    LLMContractError,
    LLMOutput,
    LLMOutputKind,
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderRefusalError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderTruncatedError,
    LLMProviderUnavailableError,
    StructuredPrompt,
    require_matching_output,
)
from ai_parametric_architect.llm.prompts import (
    DESIGN_INTENT_OUTPUT_SCHEMA_NAME,
    design_intent_output_schema,
)

OPENAI_PROVIDER_NAME: Final = "openai-responses"
OPENAI_PROVIDER_VERSION: Final = "1.0.0"

_MODEL_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MIN_TIMEOUT_SECONDS: Final = 1.0
_MAX_TIMEOUT_SECONDS: Final = 120.0
_MAX_RETRIES: Final = 2
_MIN_OUTPUT_TOKENS: Final = 128
_MAX_OUTPUT_TOKENS: Final = 4096
_MIN_BYTE_BUDGET: Final = 1024
_MAX_BYTE_BUDGET: Final = 262_144
_DESIGN_INTENT_TRANSPORT_FIELDS: Final = frozenset(
    {"building_type", "area", "rooms", "orientation", "spatial_constraints"}
)


class _ResponsesAPI(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class _OpenAIClient(Protocol):
    @property
    def responses(self) -> _ResponsesAPI: ...


@dataclass(frozen=True, slots=True)
class OpenAIProviderConfig:
    """Trusted deployment settings; credentials are deliberately excluded."""

    model: str
    timeout_seconds: float = 30.0
    max_retries: int = 0
    max_output_tokens: int = 2048
    max_input_bytes: int = 65_536
    max_response_bytes: int = 65_536

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model, str)
            or self.model != self.model.strip()
            or _MODEL_PATTERN.fullmatch(self.model) is None
        ):
            raise _configuration_error("MODEL_INVALID")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not isfinite(float(self.timeout_seconds))
            or not _MIN_TIMEOUT_SECONDS <= float(self.timeout_seconds) <= _MAX_TIMEOUT_SECONDS
        ):
            raise _configuration_error("TIMEOUT_INVALID")
        _require_bounded_int(
            self.max_retries,
            minimum=0,
            maximum=_MAX_RETRIES,
            reason="RETRY_BUDGET_INVALID",
        )
        _require_bounded_int(
            self.max_output_tokens,
            minimum=_MIN_OUTPUT_TOKENS,
            maximum=_MAX_OUTPUT_TOKENS,
            reason="OUTPUT_TOKEN_BUDGET_INVALID",
        )
        _require_bounded_int(
            self.max_input_bytes,
            minimum=_MIN_BYTE_BUDGET,
            maximum=_MAX_BYTE_BUDGET,
            reason="INPUT_BYTE_BUDGET_INVALID",
        )
        _require_bounded_int(
            self.max_response_bytes,
            minimum=_MIN_BYTE_BUDGET,
            maximum=_MAX_BYTE_BUDGET,
            reason="RESPONSE_BYTE_BUDGET_INVALID",
        )


class OpenAIResponsesProvider:
    """Generate one typed DesignIntent without tools or write-side capabilities."""

    __slots__ = ("_client", "_config")

    def __init__(
        self,
        config: OpenAIProviderConfig,
        *,
        client: _OpenAIClient | None = None,
    ) -> None:
        if type(config) is not OpenAIProviderConfig:
            raise _configuration_error("CONFIG_TYPE_INVALID")
        self._config = config
        if client is not None:
            self._client = client
            return
        try:
            sdk_client = OpenAI(
                timeout=float(config.timeout_seconds),
                max_retries=config.max_retries,
            )
        except OpenAIError:
            raise _configuration_error("CREDENTIALS_UNAVAILABLE") from None
        self._client = cast(_OpenAIClient, sdk_client)

    @property
    def name(self) -> str:
        return OPENAI_PROVIDER_NAME

    @property
    def version(self) -> str:
        return OPENAI_PROVIDER_VERSION

    def complete[OutputT: LLMOutput](self, prompt: StructuredPrompt[OutputT]) -> OutputT:
        if not isinstance(prompt, StructuredPrompt):
            raise LLMContractError(
                "Provider input must be a StructuredPrompt.",
                path="/prompt",
                details={"actual_type": type(prompt).__name__},
            )
        if prompt.output_kind is not LLMOutputKind.DESIGN_INTENT:
            raise LLMContractError(
                "The OpenAI network adapter only supports DesignIntent output.",
                path="/output_kind",
                details={
                    "provider": self.name,
                    "output_kind": prompt.output_kind.value,
                    "reason": "UNSUPPORTED_OUTPUT_KIND",
                },
            )
        _enforce_input_budget(prompt, self._config.max_input_bytes)

        try:
            response = self._client.responses.create(
                model=self._config.model,
                input=[
                    {"role": "developer", "content": prompt.system_prompt},
                    {"role": "user", "content": prompt.user_prompt},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": DESIGN_INTENT_OUTPUT_SCHEMA_NAME,
                        "schema": design_intent_output_schema(),
                        "strict": True,
                    }
                },
                max_output_tokens=self._config.max_output_tokens,
                store=False,
                tools=[],
                truncation="disabled",
                timeout=float(self._config.timeout_seconds),
            )
        except AuthenticationError:
            raise _authentication_error("AUTHENTICATION") from None
        except PermissionDeniedError:
            raise _authentication_error("PERMISSION") from None
        except APITimeoutError:
            raise _timeout_error() from None
        except RateLimitError:
            raise _rate_limit_error() from None
        except APIConnectionError:
            raise _unavailable_error("CONNECTION") from None
        except InternalServerError:
            raise _unavailable_error("UPSTREAM") from None
        except (BadRequestError, NotFoundError):
            raise _provider_error("REQUEST_REJECTED", retryable=False) from None
        except APIStatusError:
            raise _provider_error("UPSTREAM_STATUS", retryable=False) from None
        except OpenAIError:
            raise _provider_error("SDK_FAILURE", retryable=False) from None

        text = _extract_response_text(response)
        intent = _parse_design_intent(text, max_bytes=self._config.max_response_bytes)
        return require_matching_output(prompt, intent, provider_name=self.name)


def _extract_response_text(response: object) -> str:
    status = getattr(response, "status", None)
    if status == "incomplete":
        details = getattr(response, "incomplete_details", None)
        reason = getattr(details, "reason", None)
        if reason == "max_output_tokens":
            raise _truncated_error()
        raise _refusal_error("CONTENT_FILTER" if reason == "content_filter" else "INCOMPLETE")
    if status != "completed" or getattr(response, "error", None) is not None:
        raise _response_error("ENVELOPE_INVALID")

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        raise _response_error("OUTPUT_INVALID")
    unexpected = [
        item for item in output if getattr(item, "type", None) not in {"message", "reasoning"}
    ]
    messages = [item for item in output if getattr(item, "type", None) == "message"]
    if unexpected or len(messages) != 1:
        raise _response_error("OUTPUT_AMBIGUOUS")

    message = messages[0]
    if (
        getattr(message, "role", None) != "assistant"
        or getattr(message, "status", None) != "completed"
    ):
        raise _response_error("MESSAGE_INVALID")
    content = getattr(message, "content", None)
    if not isinstance(content, list) or len(content) != 1:
        raise _response_error("CONTENT_AMBIGUOUS")
    block = content[0]
    block_type = getattr(block, "type", None)
    if block_type == "refusal":
        raise _refusal_error("REFUSAL")
    text = getattr(block, "text", None)
    if block_type != "output_text" or not isinstance(text, str) or not text:
        raise _response_error("TEXT_INVALID")
    return text


def _parse_design_intent(text: str, *, max_bytes: int) -> DesignIntent:
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        raise _response_error("TEXT_ENCODING_INVALID") from None
    if len(encoded) > max_bytes:
        raise _response_error("RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError):
        raise _response_error("JSON_INVALID") from None
    if type(payload) is not dict:
        raise _response_error("ROOT_TYPE_INVALID")
    if set(payload) != _DESIGN_INTENT_TRANSPORT_FIELDS:
        raise _response_error("TRANSPORT_SCHEMA_INVALID")

    issues = IntentValidator().validate(payload)
    if issues:
        raise _response_error("SCHEMA_OR_SEMANTIC_INVALID")
    try:
        return DesignIntent.from_dict(cast(Mapping[str, Any], payload))
    except InvalidDesignIntentError:
        raise _response_error("DOMAIN_INVALID") from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object member.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"Non-standard JSON constant: {value}")


def _enforce_input_budget(prompt: StructuredPrompt[LLMOutput], maximum: int) -> None:
    try:
        size = len(prompt.system_prompt.encode("utf-8")) + len(prompt.user_prompt.encode("utf-8"))
    except UnicodeEncodeError:
        raise LLMContractError(
            "Prompt text must be valid UTF-8.",
            path="/prompt",
            details={"reason": "TEXT_ENCODING_INVALID"},
        ) from None
    if size > maximum:
        raise LLMContractError(
            "Prompt exceeds the configured byte budget.",
            path="/prompt",
            details={"maximum_bytes": maximum, "reason": "INPUT_TOO_LARGE"},
        )


def _require_bounded_int(value: object, *, minimum: int, maximum: int, reason: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise _configuration_error(reason)


def _configuration_error(reason: str) -> LLMConfigurationError:
    return LLMConfigurationError(
        details={"provider": OPENAI_PROVIDER_NAME, "reason": reason},
    )


def _authentication_error(reason: str) -> LLMProviderAuthenticationError:
    return LLMProviderAuthenticationError(
        details=_provider_details(reason, retryable=False),
    )


def _timeout_error() -> LLMProviderTimeoutError:
    return LLMProviderTimeoutError(
        details=_provider_details("TIMEOUT", retryable=True),
    )


def _rate_limit_error() -> LLMProviderRateLimitError:
    return LLMProviderRateLimitError(
        details=_provider_details("RATE_LIMITED", retryable=True),
    )


def _unavailable_error(reason: str) -> LLMProviderUnavailableError:
    return LLMProviderUnavailableError(
        details=_provider_details(reason, retryable=True),
    )


def _provider_error(reason: str, *, retryable: bool) -> LLMProviderError:
    return LLMProviderError(
        details=_provider_details(reason, retryable=retryable),
    )


def _refusal_error(reason: str) -> LLMProviderRefusalError:
    return LLMProviderRefusalError(
        details=_provider_details(reason, retryable=False),
    )


def _truncated_error() -> LLMProviderTruncatedError:
    return LLMProviderTruncatedError(
        details=_provider_details("MAX_OUTPUT_TOKENS", retryable=False),
    )


def _response_error(reason: str) -> LLMProviderResponseError:
    return LLMProviderResponseError(
        details=_provider_details(reason, retryable=False),
    )


def _provider_details(reason: str, *, retryable: bool) -> dict[str, object]:
    return {
        "provider": OPENAI_PROVIDER_NAME,
        "output_kind": LLMOutputKind.DESIGN_INTENT.value,
        "reason": reason,
        "retryable": retryable,
    }


__all__ = [
    "OPENAI_PROVIDER_NAME",
    "OPENAI_PROVIDER_VERSION",
    "OpenAIProviderConfig",
    "OpenAIResponsesProvider",
]
