"""Atomic RFC 6902 add/remove/replace operations over JSON-compatible values."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from ai_parametric_architect.domain import (
    InvalidPatchError,
    ModelComplexityError,
    ModelComplexityPolicy,
    NonJsonValueError,
    PatchOperation,
    PatchOperationType,
    StrictJsonTreeGuard,
)
from ai_parametric_architect.editing.pointers import decode_pointer

type JsonContainer = dict[str, object] | list[object]


class JsonPatchEngine:
    """Apply supported JSON Patch operations without mutating their inputs."""

    def __init__(
        self,
        *,
        json_guard: StrictJsonTreeGuard | None = None,
        complexity_policy: ModelComplexityPolicy | None = None,
    ) -> None:
        self._json_guard = StrictJsonTreeGuard() if json_guard is None else json_guard
        self._complexity_policy = (
            ModelComplexityPolicy() if complexity_policy is None else complexity_policy
        )

    def apply(self, document: object, operations: Sequence[PatchOperation]) -> object:
        try:
            self._json_guard.require(document)
        except NonJsonValueError as error:
            raise InvalidPatchError(
                f"Patch source is not JSON-compatible: {error}",
                path=error.path,
                details=error.details,
            ) from error
        try:
            self._complexity_policy.require_patch_operations(len(operations))
        except ModelComplexityError as error:
            raise InvalidPatchError(
                str(error),
                path=error.path,
                details={**error.details, "reason": error.code},
            ) from error
        working = deepcopy(document)
        for index, operation in enumerate(operations):
            try:
                tokens = decode_pointer(operation.path)
                working = self._apply_one(working, operation, tokens, index)
            except InvalidPatchError as error:
                if error.details.get("operation_index") == index:
                    raise
                raise InvalidPatchError(
                    str(error),
                    path=error.path or operation.path,
                    details={**error.details, "operation_index": index},
                ) from error
        return working

    def _apply_one(
        self,
        document: object,
        operation: PatchOperation,
        tokens: tuple[str, ...],
        operation_index: int,
    ) -> object:
        if not tokens:
            return self._apply_at_root(document, operation, operation_index)

        parent = self._resolve_parent(document, tokens, operation, operation_index)
        token = tokens[-1]
        if operation.op is PatchOperationType.ADD:
            self._add(parent, token, operation, operation_index)
        elif operation.op is PatchOperationType.REMOVE:
            self._remove(parent, token, operation, operation_index)
        else:
            self._replace(parent, token, operation, operation_index)
        return document

    def _apply_at_root(
        self,
        document: object,
        operation: PatchOperation,
        operation_index: int,
    ) -> object:
        if operation.op is PatchOperationType.REMOVE:
            raise self._error(
                "Removing the document root is not supported.",
                operation,
                operation_index,
                "ROOT_REMOVE_UNSUPPORTED",
            )
        return operation.value

    def _resolve_parent(
        self,
        document: object,
        tokens: tuple[str, ...],
        operation: PatchOperation,
        operation_index: int,
    ) -> JsonContainer:
        current = document
        for token in tokens[:-1]:
            if isinstance(current, dict):
                if token not in current:
                    raise self._error(
                        "Patch path parent does not exist.",
                        operation,
                        operation_index,
                        "PARENT_NOT_FOUND",
                        token=token,
                    )
                current = current[token]
                continue
            if isinstance(current, list):
                array_index = self._array_index(
                    token,
                    len(current),
                    allow_end=False,
                    allow_append=False,
                    operation=operation,
                    operation_index=operation_index,
                )
                current = current[array_index]
                continue
            raise self._error(
                "Patch path traverses a scalar value.",
                operation,
                operation_index,
                "SCALAR_TRAVERSAL",
                token=token,
            )
        if not isinstance(current, (dict, list)):
            raise self._error(
                "Patch target parent is not an object or array.",
                operation,
                operation_index,
                "INVALID_TARGET_PARENT",
            )
        return current

    def _add(
        self,
        parent: JsonContainer,
        token: str,
        operation: PatchOperation,
        operation_index: int,
    ) -> None:
        value = operation.value
        if isinstance(parent, dict):
            parent[token] = value
            return
        array_index = self._array_index(
            token,
            len(parent),
            allow_end=True,
            allow_append=True,
            operation=operation,
            operation_index=operation_index,
        )
        parent.insert(array_index, value)

    def _remove(
        self,
        parent: JsonContainer,
        token: str,
        operation: PatchOperation,
        operation_index: int,
    ) -> None:
        if isinstance(parent, dict):
            if token not in parent:
                raise self._error(
                    "Patch remove target does not exist.",
                    operation,
                    operation_index,
                    "TARGET_NOT_FOUND",
                    token=token,
                )
            del parent[token]
            return
        array_index = self._array_index(
            token,
            len(parent),
            allow_end=False,
            allow_append=False,
            operation=operation,
            operation_index=operation_index,
        )
        del parent[array_index]

    def _replace(
        self,
        parent: JsonContainer,
        token: str,
        operation: PatchOperation,
        operation_index: int,
    ) -> None:
        value = operation.value
        if isinstance(parent, dict):
            if token not in parent:
                raise self._error(
                    "Patch replace target does not exist.",
                    operation,
                    operation_index,
                    "TARGET_NOT_FOUND",
                    token=token,
                )
            parent[token] = value
            return
        array_index = self._array_index(
            token,
            len(parent),
            allow_end=False,
            allow_append=False,
            operation=operation,
            operation_index=operation_index,
        )
        parent[array_index] = value

    def _array_index(
        self,
        token: str,
        length: int,
        *,
        allow_end: bool,
        allow_append: bool,
        operation: PatchOperation,
        operation_index: int,
    ) -> int:
        if token == "-":
            if allow_append:
                return length
            raise self._error(
                "Array '-' token is only valid for add.",
                operation,
                operation_index,
                "INVALID_ARRAY_INDEX",
                token=token,
            )
        if not token or (len(token) > 1 and token.startswith("0")) or not _is_ascii_digits(token):
            raise self._error(
                "Array index is not in canonical decimal form.",
                operation,
                operation_index,
                "INVALID_ARRAY_INDEX",
                token=token,
            )

        maximum = length if allow_end else length - 1
        if maximum < 0 or _decimal_greater_than(token, maximum):
            raise self._error(
                "Array index is outside the target array.",
                operation,
                operation_index,
                "ARRAY_INDEX_OUT_OF_BOUNDS",
                token=token,
                length=length,
            )
        return int(token)

    @staticmethod
    def _error(
        message: str,
        operation: PatchOperation,
        operation_index: int,
        reason: str,
        **details: object,
    ) -> InvalidPatchError:
        return InvalidPatchError(
            message,
            path=operation.path,
            details={"operation_index": operation_index, "reason": reason, **details},
        )


def _is_ascii_digits(value: str) -> bool:
    return bool(value) and all("0" <= character <= "9" for character in value)


def _decimal_greater_than(value: str, maximum: int) -> bool:
    maximum_text = str(maximum)
    return len(value) > len(maximum_text) or (
        len(value) == len(maximum_text) and value > maximum_text
    )
