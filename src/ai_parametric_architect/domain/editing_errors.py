"""Stable errors for patching and revision workflows."""

from __future__ import annotations

from collections.abc import Mapping


class EditingError(RuntimeError):
    code = "EDITING_ERROR"

    def __init__(
        self,
        message: str,
        *,
        path: str = "",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.details = {} if details is None else dict(details)


class InvalidPatchError(EditingError):
    code = "INVALID_PATCH"


class NonJsonValueError(EditingError):
    code = "NON_JSON_VALUE"


class ProtectedPathError(InvalidPatchError):
    code = "PATCH_PATH_PROTECTED"


class PatchModelMismatchError(InvalidPatchError):
    code = "PATCH_MODEL_MISMATCH"


class AffectedEntitiesMismatchError(InvalidPatchError):
    code = "PATCH_AFFECTED_ENTITIES_MISMATCH"


class RevisionConflictError(EditingError):
    code = "REVISION_CONFLICT"

    def __init__(self, model_id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"Revision conflict for {model_id!r}: expected {expected}, actual {actual}.",
            details={"model_id": model_id, "expected": expected, "actual": actual},
        )
        self.model_id = model_id
        self.expected = expected
        self.actual = actual


class ModelAlreadyExistsError(EditingError):
    code = "MODEL_ALREADY_EXISTS"


class ModelNotFoundError(EditingError):
    code = "MODEL_NOT_FOUND"


class RevisionNotFoundError(EditingError):
    code = "REVISION_NOT_FOUND"


class UndoUnavailableError(EditingError):
    code = "UNDO_UNAVAILABLE"


class RedoUnavailableError(EditingError):
    code = "REDO_UNAVAILABLE"
