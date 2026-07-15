"""Infrastructure-neutral RFC 6901 JSON Pointer syntax handling."""

from __future__ import annotations


class JsonPointerSyntaxError(ValueError):
    """Describe malformed pointer syntax without choosing an adapter error type."""

    def __init__(self, message: str, *, reason: str, token: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.token = token


def decode_json_pointer(pointer: str) -> tuple[str, ...]:
    """Decode an RFC 6901 pointer and reject malformed escape sequences."""

    if not isinstance(pointer, str):
        raise JsonPointerSyntaxError(
            "JSON Pointer must be a string.",
            reason="INVALID_POINTER_TYPE",
        )
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise JsonPointerSyntaxError(
            "JSON Pointer must be empty or start with '/'.",
            reason="INVALID_POINTER_PREFIX",
        )
    return tuple(_decode_token(token) for token in pointer[1:].split("/"))


def _decode_token(token: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise JsonPointerSyntaxError(
                "JSON Pointer contains an invalid escape sequence.",
                reason="INVALID_POINTER_ESCAPE",
                token=token,
            )
        decoded.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)
