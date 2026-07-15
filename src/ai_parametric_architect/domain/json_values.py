"""One strict definition of values allowed in authoritative JSON state."""

from __future__ import annotations

from math import isfinite
from typing import Final

from ai_parametric_architect.domain.editing_errors import NonJsonValueError

MAX_JSON_DEPTH: Final = 128


def ensure_json_value(value: object) -> None:
    """Reject values that cannot represent a standard, alias-free JSON tree."""
    active_containers: set[int] = set()
    seen_containers: set[int] = set()
    stack: list[tuple[object, str, bool, int]] = [(value, "", False, 0)]

    while stack:
        current, path, exiting, depth = stack.pop()
        if exiting:
            active_containers.remove(id(current))
            continue
        if depth > MAX_JSON_DEPTH:
            raise NonJsonValueError(
                "JSON value exceeds the supported structural depth.",
                path=path,
                details={"reason": "JSON_DEPTH_EXCEEDED", "max_depth": MAX_JSON_DEPTH},
            )

        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not isfinite(current):
                raise NonJsonValueError(
                    "JSON numbers must be finite.",
                    path=path,
                    details={"reason": "NON_FINITE_NUMBER"},
                )
            continue
        if isinstance(current, dict) and type(current) is dict:
            _enter_container(
                current,
                path,
                depth,
                active_containers,
                seen_containers,
                stack,
            )
            items = list(current.items())
            for key, child in reversed(items):
                if type(key) is not str:
                    raise NonJsonValueError(
                        "JSON object keys must be strings.",
                        path=path,
                        details={"reason": "NON_STRING_KEY", "key_type": type(key).__name__},
                    )
                stack.append((child, _child_path(path, key), False, depth + 1))
            continue
        if isinstance(current, list) and type(current) is list:
            _enter_container(
                current,
                path,
                depth,
                active_containers,
                seen_containers,
                stack,
            )
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], _child_path(path, str(index)), False, depth + 1))
            continue
        raise NonJsonValueError(
            f"Value of type {type(current).__name__!r} is not a standard JSON value.",
            path=path,
            details={"reason": "NON_JSON_TYPE", "type": type(current).__name__},
        )


def _enter_container(
    value: dict[object, object] | list[object],
    path: str,
    depth: int,
    active_containers: set[int],
    seen_containers: set[int],
    stack: list[tuple[object, str, bool, int]],
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise NonJsonValueError(
            "JSON values cannot contain cyclic references.",
            path=path,
            details={"reason": "CYCLIC_REFERENCE"},
        )
    if identity in seen_containers:
        raise NonJsonValueError(
            "JSON trees cannot contain shared container references.",
            path=path,
            details={"reason": "SHARED_REFERENCE"},
        )
    active_containers.add(identity)
    seen_containers.add(identity)
    stack.append((value, path, True, depth))


def _child_path(parent: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"
