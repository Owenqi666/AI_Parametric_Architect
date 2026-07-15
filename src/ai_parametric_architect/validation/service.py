"""Structural and deterministic model validation orchestration."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from jsonschema.exceptions import ValidationError

from ai_parametric_architect.contracts import (
    SUPPORTED_SCHEMA_VERSIONS,
    create_model_validator,
)
from ai_parametric_architect.domain import (
    GeometryPrecisionPolicy,
    ModelComplexityError,
    ModelComplexityPolicy,
    ModelDocument,
    Severity,
    StrictJsonTreeGuard,
    ValidationIssue,
    ValidationReport,
)
from ai_parametric_architect.ports import GeometryEngine
from ai_parametric_architect.validation.base import ValidationRule
from ai_parametric_architect.validation.pointers import json_pointer
from ai_parametric_architect.validation.rules import DEFAULT_RULES

_SCHEMA_CODE_OVERRIDES = {
    "additionalProperties": "SCHEMA_ADDITIONAL_PROPERTIES",
    "exclusiveMinimum": "SCHEMA_EXCLUSIVE_MINIMUM",
    "maxItems": "SCHEMA_MAX_ITEMS",
    "minItems": "SCHEMA_MIN_ITEMS",
    "minLength": "SCHEMA_MIN_LENGTH",
    "minimum": "SCHEMA_MINIMUM",
    "pattern": "SCHEMA_PATTERN",
    "propertyNames": "SCHEMA_PROPERTY_NAMES",
    "required": "SCHEMA_REQUIRED",
    "type": "SCHEMA_TYPE",
}
_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


def _schema_issue(error: ValidationError) -> ValidationIssue:
    keyword = str(error.validator)
    fallback = "SCHEMA_" + re.sub(r"[^A-Z0-9]+", "_", keyword.upper()).strip("_")
    return ValidationIssue(
        code=_SCHEMA_CODE_OVERRIDES.get(keyword, fallback or "SCHEMA_INVALID"),
        severity=Severity.ERROR,
        message=error.message,
        path=json_pointer(error.absolute_path),
        details={"keyword": keyword},
    )


def _issue_sort_key(issue: ValidationIssue) -> tuple[object, ...]:
    return (
        _SEVERITY_ORDER[issue.severity],
        issue.code,
        issue.path,
        issue.entity_ids,
        issue.message,
    )


class ModelValidator:
    """Validate without mutating or normalizing the authoritative model."""

    def __init__(
        self,
        geometry: GeometryEngine,
        rules: Sequence[ValidationRule] = DEFAULT_RULES,
        *,
        json_guard: StrictJsonTreeGuard | None = None,
        complexity_policy: ModelComplexityPolicy | None = None,
    ) -> None:
        self._geometry = geometry
        self._rules = tuple(sorted(rules, key=lambda rule: (rule.level, rule.name)))
        self._json_guard = StrictJsonTreeGuard() if json_guard is None else json_guard
        self._complexity_policy = (
            ModelComplexityPolicy() if complexity_policy is None else complexity_policy
        )

    def validate(self, model: ModelDocument) -> ValidationReport:
        json_issue = self._json_guard.issue(model)
        if json_issue is not None:
            return ValidationReport.create(model, (json_issue,))
        if type(model) is not dict:
            issue = ValidationIssue(
                code="SCHEMA_TYPE",
                severity=Severity.ERROR,
                message="Model document root must be a JSON object.",
                path="/",
                details={"keyword": "type"},
            )
            return ValidationReport.create(model, (issue,))

        version = model.get("schema_version")
        if not isinstance(version, str) or version not in SUPPORTED_SCHEMA_VERSIONS:
            issue = ValidationIssue(
                code="SCHEMA_VERSION_UNSUPPORTED",
                severity=Severity.ERROR,
                message=f"Unsupported schema version: {version!r}.",
                path="/schema_version",
                details={"supported_versions": list(SUPPORTED_SCHEMA_VERSIONS)},
            )
            return ValidationReport.create(model, (issue,))

        schema_validator = create_model_validator(version)
        schema_errors = sorted(
            schema_validator.iter_errors(model),
            key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
        )
        if schema_errors:
            return ValidationReport.create(model, (_schema_issue(error) for error in schema_errors))

        try:
            self._complexity_policy.require_model(model)
        except ModelComplexityError as error:
            return ValidationReport.create(model, (error.to_issue(),))

        try:
            precision = GeometryPrecisionPolicy.from_model(model)
        except ValueError as exc:
            issue = ValidationIssue(
                code="GEOMETRY_PRECISION_INVALID",
                severity=Severity.ERROR,
                message=str(exc),
                path="/geometry_settings/linear_tolerance",
            )
            return ValidationReport.create(model, (issue,))
        issues: list[ValidationIssue] = []
        for rule in self._rules:
            issues.extend(rule.evaluate(model, self._geometry, precision))
        return ValidationReport.create(model, sorted(issues, key=_issue_sort_key))

    @property
    def rules(self) -> Iterable[ValidationRule]:
        return self._rules
