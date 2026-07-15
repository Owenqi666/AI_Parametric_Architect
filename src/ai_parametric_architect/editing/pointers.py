"""Strict RFC 6901 JSON Pointer decoding for patch targets."""

from __future__ import annotations

from ai_parametric_architect.domain import (
    InvalidPatchError,
    JsonPointerSyntaxError,
    decode_json_pointer,
)


def decode_pointer(pointer: str) -> tuple[str, ...]:
    """Decode a JSON Pointer while rejecting malformed escape sequences."""
    try:
        return decode_json_pointer(pointer)
    except JsonPointerSyntaxError as error:
        details = {"reason": error.reason}
        if error.token is not None:
            details["token"] = error.token
        raise InvalidPatchError(str(error), path=pointer, details=details) from error
