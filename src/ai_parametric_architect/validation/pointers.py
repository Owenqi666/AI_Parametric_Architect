"""JSON Pointer helpers used by validation reports."""

from __future__ import annotations

from collections.abc import Iterable


def json_pointer(parts: Iterable[str | int]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else "/"


def entity_pointer(registry: str, entity_id: str, *suffix: str) -> str:
    return json_pointer(("entities", registry, entity_id, *suffix))
