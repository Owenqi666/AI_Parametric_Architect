"""ASGI request-body limits for the HTTP transport boundary."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_parametric_architect.domain import Severity, ValidationIssue, ValidationReport

DEFAULT_MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RequestBodySizePolicy:
    """Central byte budget for one HTTP request body."""

    max_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_bytes, int)
            or isinstance(self.max_bytes, bool)
            or self.max_bytes <= 0
        ):
            raise ValueError("max_bytes must be a positive integer")


class RequestBodySizeLimitMiddleware:
    """Reject oversized bodies before they reach the FastAPI application.

    The entire body is staged inside the configured budget before downstream
    dispatch. This is required because Content-Length is optional and must not
    be trusted when present.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        policy: RequestBodySizePolicy | None = None,
    ) -> None:
        self._app = app
        self._policy = RequestBodySizePolicy() if policy is None else policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared_length = _content_length(scope)
        if declared_length is not None and declared_length > self._policy.max_bytes:
            await self._reject(scope, receive, send)
            return

        staged_messages: list[Message] = []
        observed_bytes = 0
        while True:
            message = await receive()
            staged_messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                # ASGI requires bytes; let the framework handle a broken server
                # message instead of coercing or executing an arbitrary object.
                await self._app(scope, _replay(staged_messages), send)
                return
            observed_bytes += len(body)
            if observed_bytes > self._policy.max_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        await self._app(scope, _replay(staged_messages), send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        issue = ValidationIssue(
            code="REQUEST_BODY_TOO_LARGE",
            severity=Severity.ERROR,
            path="/",
            entity_ids=(),
            message="Request body exceeds the configured byte limit.",
            details={"limit_bytes": self._policy.max_bytes},
        )
        report = ValidationReport.create({}, (issue,))
        response = JSONResponse(status_code=413, content=report.to_dict())
        await response(scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    raw_values = [
        value for name, value in scope.get("headers", ()) if name.lower() == b"content-length"
    ]
    if len(raw_values) != 1:
        return None
    try:
        value = int(raw_values[0].decode("ascii"), 10)
    except (UnicodeDecodeError, ValueError):
        return None
    return value if value >= 0 else None


def _replay(messages: list[Message]) -> Receive:
    iterator = iter(messages)

    async def receive() -> Message:
        return next(iterator, {"type": "http.disconnect"})

    return receive


__all__ = [
    "DEFAULT_MAX_REQUEST_BODY_BYTES",
    "RequestBodySizeLimitMiddleware",
    "RequestBodySizePolicy",
]
