"""Deterministic validation for provider-neutral design-intent documents."""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, cast

from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.editing_errors import NonJsonValueError
from ai_parametric_architect.domain.issues import Severity, ValidationIssue
from ai_parametric_architect.domain.json_values import ensure_json_value
from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError
from ai_parametric_architect.intent.schema import (
    DEFAULT_INTENT_SCHEMA_VERSION,
    create_intent_schema_validator,
)

_SCHEMA_CODE_OVERRIDES = {
    "additionalProperties": "INTENT_SCHEMA_ADDITIONAL_PROPERTIES",
    "const": "INTENT_SCHEMA_CONST",
    "enum": "INTENT_SCHEMA_ENUM",
    "exclusiveMinimum": "INTENT_SCHEMA_EXCLUSIVE_MINIMUM",
    "maxItems": "INTENT_SCHEMA_MAX_ITEMS",
    "maximum": "INTENT_SCHEMA_MAXIMUM",
    "minItems": "INTENT_SCHEMA_MIN_ITEMS",
    "minimum": "INTENT_SCHEMA_MINIMUM",
    "oneOf": "INTENT_SCHEMA_ONE_OF",
    "pattern": "INTENT_SCHEMA_PATTERN",
    "required": "INTENT_SCHEMA_REQUIRED",
    "type": "INTENT_SCHEMA_TYPE",
    "uniqueItems": "INTENT_SCHEMA_UNIQUE_ITEMS",
}


def _json_pointer(parts: Iterable[object]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else "/"


def _error_sort_key(error: ValidationError) -> tuple[object, ...]:
    path = tuple((isinstance(part, int), str(part)) for part in error.absolute_path)
    return (path, str(error.validator), error.message)


def _schema_issue(error: ValidationError) -> ValidationIssue:
    keyword = str(error.validator)
    fallback = "INTENT_SCHEMA_" + re.sub(r"[^A-Z0-9]+", "_", keyword.upper()).strip("_")
    return ValidationIssue(
        code=_SCHEMA_CODE_OVERRIDES.get(keyword, fallback or "INTENT_SCHEMA_INVALID"),
        severity=Severity.ERROR,
        message=error.message,
        path=_json_pointer(error.absolute_path),
        details={"keyword": keyword},
    )


def _json_value_issue(error: NonJsonValueError) -> ValidationIssue:
    non_finite = error.details.get("reason") == "NON_FINITE_NUMBER"
    if non_finite:
        return ValidationIssue(
            code="INTENT_SEMANTIC_INVALID",
            severity=Severity.ERROR,
            message="Design intent numbers must be finite.",
            path=error.path or "/",
            details={"reason": "NON_FINITE_NUMBER"},
        )
    return ValidationIssue(
        code="INTENT_JSON_INVALID",
        severity=Severity.ERROR,
        message=str(error),
        path=error.path or "/",
        details=error.details,
    )


def _issue_sort_key(issue: ValidationIssue) -> tuple[object, ...]:
    return (issue.code, issue.path, issue.message)


def _semantic_issue(error: InvalidDesignIntentError) -> ValidationIssue:
    """Translate the domain failure without leaking an exception across the port."""

    return ValidationIssue(
        code="INTENT_SEMANTIC_INVALID",
        severity=Severity.ERROR,
        message=str(error),
        path=error.path or "/",
        details=deepcopy(error.details),
    )


class IntentValidator:
    """Validate intent JSON without mutating or normalizing caller-owned data."""

    def __init__(self, version: str = DEFAULT_INTENT_SCHEMA_VERSION) -> None:
        self._version = version
        self._schema_validator: Validator = create_intent_schema_validator(version)

    @property
    def version(self) -> str:
        return self._version

    def validate(self, intent: object) -> tuple[ValidationIssue, ...]:
        try:
            ensure_json_value(intent)
        except NonJsonValueError as error:
            return (_json_value_issue(error),)
        errors = sorted(
            self._schema_validator.iter_errors(cast(Any, intent)),
            key=_error_sort_key,
        )
        if errors:
            return tuple(sorted((_schema_issue(error) for error in errors), key=_issue_sort_key))
        try:
            DesignIntent.from_dict(cast(dict[str, Any], intent))
        except InvalidDesignIntentError as error:
            return (_semantic_issue(error),)
        return ()
