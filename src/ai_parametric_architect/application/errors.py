"""Application-level failure types."""

from __future__ import annotations

from ai_parametric_architect.domain import ValidationReport


class ModelValidationError(ValueError):
    """Raised when a use case requires a valid model but receives errors."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__(f"Model validation failed with {report.error_count} error(s)")
        self.report = report


class PatchedModelValidationError(ModelValidationError):
    """Raised when a patch result fails schema, semantic, or geometry validation."""

    code = "PATCHED_MODEL_INVALID"


class RestoredModelValidationError(ModelValidationError):
    """Raised when an undo or redo target fails the current validation policy."""

    code = "RESTORED_MODEL_INVALID"
