from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from starlette.types import Message, Receive, Scope, Send

from ai_parametric_architect.backend import (
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    RequestBodySizeLimitMiddleware,
    RequestBodySizePolicy,
    create_app,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _post(
    body: bytes | AsyncIterator[bytes],
    *,
    policy: RequestBodySizePolicy,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(request_body_policy=policy))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/v1/models/validate",
            content=body,
            headers={"content-type": "application/json", **(headers or {})},
        )


def _assert_too_large(response: httpx.Response, limit_bytes: int) -> None:
    assert response.status_code == 413
    assert response.json() == {
        "valid": False,
        "model_id": None,
        "revision": None,
        "error_count": 1,
        "issues": [
            {
                "code": "REQUEST_BODY_TOO_LARGE",
                "severity": "error",
                "path": "/",
                "entity_ids": [],
                "message": "Request body exceeds the configured byte limit.",
                "details": {"limit_bytes": limit_bytes},
            }
        ],
    }


async def test_default_policy_rejects_oversized_request() -> None:
    body = b"x" * (DEFAULT_MAX_REQUEST_BODY_BYTES + 1)

    response = await _post(body, policy=RequestBodySizePolicy())

    _assert_too_large(response, DEFAULT_MAX_REQUEST_BODY_BYTES)


async def test_exact_byte_limit_is_allowed(
    valid_simple_house: dict[str, Any],
) -> None:
    body = json.dumps(
        valid_simple_house,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    response = await _post(body, policy=RequestBodySizePolicy(max_bytes=len(body)))

    assert response.status_code == 200
    assert response.json()["valid"] is True


async def test_one_byte_over_policy_is_rejected(
    valid_simple_house: dict[str, Any],
) -> None:
    body = json.dumps(valid_simple_house, separators=(",", ":")).encode()
    limit = len(body) - 1

    response = await _post(body, policy=RequestBodySizePolicy(max_bytes=limit))

    _assert_too_large(response, limit)


async def test_stream_without_content_length_is_counted() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"payload":"'
        yield b"x" * 64
        yield b'"}'

    response = await _post(chunks(), policy=RequestBodySizePolicy(max_bytes=32))

    _assert_too_large(response, 32)


async def test_forged_content_length_does_not_bypass_stream_counting() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"payload":"'
        yield b"x" * 64
        yield b'"}'

    response = await _post(
        chunks(),
        policy=RequestBodySizePolicy(max_bytes=32),
        headers={"content-length": "1"},
    )

    _assert_too_large(response, 32)


async def test_health_is_unaffected_by_small_body_budget() -> None:
    transport = httpx.ASGITransport(
        app=create_app(request_body_policy=RequestBodySizePolicy(max_bytes=1))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_declared_oversize_is_rejected_without_reading_or_dispatching() -> None:
    downstream_called = False
    receive_called = False
    sent: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        nonlocal receive_called
        receive_called = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(
        downstream,
        policy=RequestBodySizePolicy(max_bytes=8),
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/v1/models/validate",
        "headers": [(b"content-length", b"9")],
    }

    await middleware(scope, receive, send)

    assert downstream_called is False
    assert receive_called is False
    assert sent[0]["status"] == 413


async def test_streamed_oversize_is_not_dispatched_downstream() -> None:
    downstream_called = False
    messages = iter(
        (
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"56789", "more_body": False},
        )
    )
    sent: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        return next(messages)

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(
        downstream,
        policy=RequestBodySizePolicy(max_bytes=8),
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/v1/models/validate",
        "headers": [],
    }

    await middleware(scope, receive, send)

    assert downstream_called is False
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("max_bytes", [0, -1, True])
def test_request_body_policy_rejects_invalid_limits(max_bytes: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        RequestBodySizePolicy(max_bytes=max_bytes)
