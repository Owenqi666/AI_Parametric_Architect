"""Provider-neutral JSON Patch proposal values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from ai_parametric_architect.domain.editing_errors import InvalidPatchError, NonJsonValueError
from ai_parametric_architect.domain.json_values import ensure_json_value


class PatchOperationType(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


class _MissingValue:
    pass


MISSING_VALUE: Final = _MissingValue()
_PATCH_PROPOSAL_FIELDS: Final = frozenset(
    {
        "affected_entity_ids",
        "base_model_id",
        "base_revision",
        "operations",
        "provenance",
        "rationale",
    }
)


@dataclass(frozen=True, slots=True, init=False)
class PatchOperation:
    op: PatchOperationType
    path: str
    _value: object = field(repr=False)

    def __init__(
        self,
        op: PatchOperationType | str,
        path: str,
        value: object = MISSING_VALUE,
    ) -> None:
        if not isinstance(op, (str, PatchOperationType)):
            raise InvalidPatchError(
                "Patch operation 'op' must be a string.",
                path="/op",
            )
        try:
            operation_type = PatchOperationType(op)
        except ValueError as exc:
            raise InvalidPatchError(
                f"Unsupported patch operation: {op!r}.",
                path="/op",
                details={"op": str(op)},
            ) from exc
        if not isinstance(path, str) or (path and not path.startswith("/")):
            raise InvalidPatchError(
                "Patch path must be an RFC 6901 pointer.",
                path="/path",
            )
        if operation_type in {PatchOperationType.ADD, PatchOperationType.REPLACE} and isinstance(
            value, _MissingValue
        ):
            raise InvalidPatchError(
                f"Patch operation {operation_type.value!r} requires a value.",
                path="/value",
            )
        if operation_type in {PatchOperationType.ADD, PatchOperationType.REPLACE}:
            try:
                ensure_json_value(value)
            except NonJsonValueError as error:
                raise InvalidPatchError(
                    f"Patch value is not JSON-compatible: {error}",
                    path=f"/value{error.path}",
                    details=error.details,
                ) from error

        object.__setattr__(self, "op", operation_type)
        object.__setattr__(self, "path", path)
        object.__setattr__(
            self,
            "_value",
            MISSING_VALUE if operation_type is PatchOperationType.REMOVE else deepcopy(value),
        )

    @property
    def has_value(self) -> bool:
        return not isinstance(self._value, _MissingValue)

    @property
    def value(self) -> object:
        if not self.has_value:
            raise AttributeError("remove operation has no value")
        return deepcopy(self._value)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PatchOperation:
        if "op" not in value:
            raise InvalidPatchError("Patch operation is missing 'op'.", path="/op")
        if "path" not in value:
            raise InvalidPatchError("Patch operation is missing 'path'.", path="/path")
        operation_type = value["op"]
        path = value["path"]
        if not isinstance(operation_type, str):
            raise InvalidPatchError("Patch operation 'op' must be a string.", path="/op")
        if not isinstance(path, str):
            raise InvalidPatchError("Patch operation 'path' must be a string.", path="/path")
        operation_value = value.get("value", MISSING_VALUE)
        return cls(operation_type, path, operation_value)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"op": self.op.value, "path": self.path}
        if self.has_value:
            result["value"] = self.value
        return result


@dataclass(frozen=True, slots=True)
class PatchProposal:
    base_model_id: str
    base_revision: int
    operations: tuple[PatchOperation, ...]
    provenance: str
    rationale: str
    affected_entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.base_model_id, str) or not self.base_model_id.strip():
            raise InvalidPatchError("base_model_id must be a non-empty string.")
        if (
            not isinstance(self.base_revision, int)
            or isinstance(self.base_revision, bool)
            or self.base_revision < 0
        ):
            raise InvalidPatchError("base_revision must be a non-negative integer.")
        if not isinstance(self.operations, tuple) or not all(
            isinstance(operation, PatchOperation) for operation in self.operations
        ):
            raise InvalidPatchError("Patch proposal operations must contain patch operations.")
        if not self.operations:
            raise InvalidPatchError("Patch proposal must contain at least one operation.")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise InvalidPatchError("Patch provenance cannot be empty.")
        if _claims_human_identity(self.provenance):
            raise InvalidPatchError(
                "Patch provenance cannot declare a human identity.",
                path="/provenance",
            )
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise InvalidPatchError("Patch rationale cannot be empty.")
        if not isinstance(self.affected_entity_ids, tuple) or not all(
            isinstance(entity_id, str) and entity_id.strip()
            for entity_id in self.affected_entity_ids
        ):
            raise InvalidPatchError(
                "Patch affected_entity_ids must be an immutable tuple of non-empty strings."
            )
        if len(self.affected_entity_ids) != len(set(self.affected_entity_ids)):
            raise InvalidPatchError("Patch affected_entity_ids must be unique.")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PatchProposal:
        unexpected_fields = set(value) - _PATCH_PROPOSAL_FIELDS
        if unexpected_fields:
            unexpected = sorted(str(field_name) for field_name in unexpected_fields)
            raise InvalidPatchError(
                "Patch proposal contains unexpected fields.",
                details={"unexpected_fields": unexpected},
            )
        base_model_id = value.get("base_model_id")
        base_revision = value.get("base_revision")
        provenance = value.get("provenance")
        rationale = value.get("rationale")
        if not isinstance(base_model_id, str) or not base_model_id.strip():
            raise InvalidPatchError("base_model_id must be a non-empty string.")
        if not isinstance(base_revision, int) or isinstance(base_revision, bool):
            raise InvalidPatchError("base_revision must be a non-negative integer.")
        if not isinstance(provenance, str):
            raise InvalidPatchError("Patch provenance must be a string.")
        if not isinstance(rationale, str):
            raise InvalidPatchError("Patch rationale must be a string.")
        affected_value = value.get("affected_entity_ids", ())
        if not isinstance(affected_value, Sequence) or isinstance(affected_value, (str, bytes)):
            raise InvalidPatchError("Patch affected_entity_ids must be an array.")
        operations_value = value.get("operations")
        if not isinstance(operations_value, Sequence) or isinstance(operations_value, (str, bytes)):
            raise InvalidPatchError("Patch proposal operations must be an array.")
        operations: list[PatchOperation] = []
        for index, operation in enumerate(operations_value):
            if not isinstance(operation, Mapping):
                raise InvalidPatchError(
                    "Each patch operation must be an object.",
                    path=f"/operations/{index}",
                    details={"operation_index": index},
                )
            try:
                operations.append(PatchOperation.from_dict(operation))
            except InvalidPatchError as error:
                raise InvalidPatchError(
                    str(error),
                    path=f"/operations/{index}{error.path}",
                    details={**error.details, "operation_index": index},
                ) from error
        return cls(
            base_model_id=base_model_id,
            base_revision=base_revision,
            operations=tuple(operations),
            provenance=provenance,
            rationale=rationale,
            affected_entity_ids=tuple(affected_value),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "base_model_id": self.base_model_id,
            "base_revision": self.base_revision,
            "operations": [operation.to_dict() for operation in self.operations],
            "provenance": self.provenance,
            "rationale": self.rationale,
        }
        if self.affected_entity_ids:
            result["affected_entity_ids"] = list(self.affected_entity_ids)
        return result


def _claims_human_identity(value: str) -> bool:
    compact = "".join(value.casefold().split())
    return compact == "human" or compact.startswith(("human:", "human/", "human@"))
