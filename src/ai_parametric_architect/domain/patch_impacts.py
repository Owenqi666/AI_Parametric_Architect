"""Derive trustworthy entity impact metadata from authoritative JSON snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError
from ai_parametric_architect.domain.planning_record import (
    PLANNING_EXTENSION_KEY,
    PlanningRecord,
)

_MISSING = object()


def derive_affected_entity_ids(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return canonical IDs whose entity values or owned planning bindings changed.

    Callers run this only after both snapshots have passed the model validator. A
    ``ValueError`` therefore signals a broken validator contract rather than an
    ordinary invalid proposal.
    """

    affected: set[str] = set()
    before_registries = _entity_registries(before)
    after_registries = _entity_registries(after)
    for registry_name in sorted(set(before_registries) | set(after_registries)):
        before_registry = _entity_registry(before_registries, registry_name)
        after_registry = _entity_registry(after_registries, registry_name)
        for entity_id in sorted(set(before_registry) | set(after_registry)):
            if before_registry.get(entity_id, _MISSING) != after_registry.get(entity_id, _MISSING):
                affected.add(entity_id)

    if _planning_payload(before) != _planning_payload(after):
        affected.update(_planning_assignment_ids(before))
        affected.update(_planning_assignment_ids(after))
    return tuple(sorted(affected))


def _entity_registries(document: Mapping[str, Any]) -> Mapping[str, object]:
    value = document.get("entities", _MISSING)
    if value is _MISSING:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Validator accepted a model with a malformed entity registry")
    if not all(isinstance(registry_name, str) for registry_name in value):
        raise ValueError("Validator accepted a model with a malformed entity registry name")
    return cast(Mapping[str, object], value)


def _entity_registry(
    registries: Mapping[str, object],
    registry_name: str,
) -> Mapping[str, object]:
    value = registries.get(registry_name, _MISSING)
    if value is _MISSING:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Validator accepted a model with a malformed entity registry")
    if not all(isinstance(entity_id, str) for entity_id in value):
        raise ValueError("Validator accepted a model with a malformed entity ID")
    return cast(Mapping[str, object], value)


def _planning_payload(document: Mapping[str, Any]) -> object:
    extensions = document.get("extensions", _MISSING)
    if extensions is _MISSING:
        return _MISSING
    if not isinstance(extensions, Mapping):
        raise ValueError("Validator accepted a model with malformed extensions")
    return extensions.get(PLANNING_EXTENSION_KEY, _MISSING)


def _planning_assignment_ids(document: Mapping[str, Any]) -> tuple[str, ...]:
    payload = _planning_payload(document)
    if payload is _MISSING:
        return ()
    if not isinstance(payload, Mapping):
        raise ValueError("Validator accepted a malformed architecture planning record")
    try:
        record = PlanningRecord.from_dict(cast(Mapping[str, Any], payload))
    except InvalidDesignIntentError as error:
        raise ValueError("Validator accepted a malformed architecture planning record") from error
    return tuple(assignment.room_id for assignment in record.assignments)
