"""Exact authorization policy for architecture-planning patch proposals.

The policy is deliberately detached from repositories and commit services.  It
can authorize only the narrow semantic-room-assignment contract owned by the
architecture planner.  An authorized proposal is still only a proposal: the
application gateway must subsequently send it through normal model validation
and revision commit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    InvalidDesignIntentError,
    ModelRevision,
    PatchOperation,
    PatchOperationType,
    PatchProposal,
    PlannerContractError,
    PlanningRecord,
)

_PLANNING_EXTENSION_PATH = f"/extensions/{PLANNING_EXTENSION_KEY}"
_MISSING = object()


class AgentAuthorizationPolicy(Protocol):
    """Port implemented by deterministic proposal authorization policies."""

    def authorize(
        self,
        intent: DesignIntent,
        current: ModelRevision,
        candidate: object,
    ) -> PatchProposal: ...

    def require_no_change(
        self,
        intent: DesignIntent,
        current: ModelRevision,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ArchitecturePlanningAuthorizationPolicy:
    """Authorize only the exact deterministic planning operation contract."""

    def authorize(
        self,
        intent: DesignIntent,
        current: ModelRevision,
        candidate: object,
    ) -> PatchProposal:
        """Return the candidate only when every owned-policy invariant holds."""

        if type(intent) is not DesignIntent:
            raise PlannerContractError(
                "Authorization requires an exact DesignIntent value.",
                path="/intent",
                details={"actual_type": type(intent).__name__},
            )
        if type(current) is not ModelRevision:
            raise PlannerContractError(
                "Authorization requires an exact ModelRevision snapshot.",
                path="/base_revision",
                details={"actual_type": type(current).__name__},
            )

        proposal = _require_patch_proposal(candidate)
        if proposal.base_model_id != current.model_id:
            raise PlannerContractError(
                "Planner proposal model does not match the planning context.",
                path="/base_model_id",
                details={
                    "actual": proposal.base_model_id,
                    "expected": current.model_id,
                },
            )
        if proposal.base_revision != current.revision_number:
            raise PlannerContractError(
                "Planner proposal base revision does not match the planning context.",
                path="/base_revision",
                details={
                    "actual": proposal.base_revision,
                    "expected": current.revision_number,
                },
            )

        operations = _require_operations(proposal)
        record = _record_from_operations(operations)
        if record.intent != intent:
            raise PlannerContractError(
                "Planning record intent does not match the parsed requirement.",
                path="/planning_record/intent",
            )
        _require_unverified_constraints(record)
        expected_affected_ids = tuple(assignment.room_id for assignment in record.assignments)
        if proposal.affected_entity_ids != expected_affected_ids:
            raise PlannerContractError(
                "Planner proposal affected entities do not match its planning record.",
                path="/affected_entity_ids",
                details={
                    "actual": list(proposal.affected_entity_ids),
                    "expected": list(expected_affected_ids),
                },
            )

        semantic_operations = _semantic_operations(record, current.document)
        extension_operation = _extension_operation(record, current.document)
        expected = (*semantic_operations, extension_operation)
        _require_exact_operations(operations, expected)

        if (
            not semantic_operations
            and _current_extension_value(current.document) == record.to_dict()
        ):
            raise PlannerContractError(
                "Planner must return no change instead of a redundant proposal.",
                path="/operations",
                details={"reason": "NO_CHANGE_EXPECTED"},
            )
        return proposal

    def require_no_change(
        self,
        intent: DesignIntent,
        current: ModelRevision,
    ) -> None:
        """Verify that no patch is needed for the supplied intent and snapshot."""

        if type(intent) is not DesignIntent:
            raise PlannerContractError(
                "No-change authorization requires an exact DesignIntent value.",
                path="/intent",
                details={"actual_type": type(intent).__name__},
            )
        if type(current) is not ModelRevision:
            raise PlannerContractError(
                "No-change authorization requires an exact ModelRevision snapshot.",
                path="/base_revision",
                details={"actual_type": type(current).__name__},
            )

        value = _current_extension_value(current.document)
        if not isinstance(value, Mapping):
            raise PlannerContractError(
                "Planner reported no change without an existing planning record.",
                path=_PLANNING_EXTENSION_PATH,
                details={"reason": "MISSING_PLANNING_RECORD"},
            )
        try:
            record = PlanningRecord.from_dict(cast(Mapping[str, Any], value))
        except InvalidDesignIntentError as error:
            raise PlannerContractError(
                f"Planner reported no change for an invalid planning record: {error}",
                path=f"{_PLANNING_EXTENSION_PATH}{error.path}",
                details={"cause": error.code},
            ) from error
        _require_unverified_constraints(record)
        if record.intent != intent or _semantic_operations(record, current.document):
            raise PlannerContractError(
                "Planner reported no change although the current model "
                "does not realize the intent.",
                path="/proposal",
                details={"reason": "FALSE_NO_CHANGE"},
            )


def _require_patch_proposal(candidate: object) -> PatchProposal:
    if type(candidate) is not PatchProposal:
        raise PlannerContractError(
            "Planner must return a PatchProposal or no change.",
            path="/proposal",
            details={"actual_type": type(candidate).__name__},
        )
    proposal = candidate
    try:
        base_model_id = proposal.base_model_id
        base_revision = proposal.base_revision
        provenance = proposal.provenance
        rationale = proposal.rationale
        affected_entity_ids = proposal.affected_entity_ids
    except AttributeError as error:
        raise PlannerContractError(
            "Planner returned an incompletely initialized PatchProposal.",
            path="/proposal",
        ) from error
    if not isinstance(base_model_id, str) or not base_model_id.strip():
        raise PlannerContractError(
            "Planner proposal base model ID must be a non-empty string.",
            path="/base_model_id",
        )
    if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
        raise PlannerContractError(
            "Planner proposal base revision must be a non-negative integer.",
            path="/base_revision",
        )
    if not isinstance(provenance, str) or not provenance.strip():
        raise PlannerContractError(
            "Planner proposal provenance cannot be empty.",
            path="/provenance",
        )
    if not isinstance(rationale, str) or not rationale.strip():
        raise PlannerContractError(
            "Planner proposal rationale cannot be empty.",
            path="/rationale",
        )
    if not isinstance(affected_entity_ids, tuple) or not all(
        isinstance(entity_id, str) and entity_id for entity_id in affected_entity_ids
    ):
        raise PlannerContractError(
            "Planner proposal affected entities must be an immutable string tuple.",
            path="/affected_entity_ids",
        )
    return proposal


def _require_operations(proposal: PatchProposal) -> tuple[PatchOperation, ...]:
    try:
        operations = proposal.operations
    except AttributeError as error:
        raise PlannerContractError(
            "Planner returned an incompletely initialized PatchProposal.",
            path="/operations",
        ) from error
    if not isinstance(operations, tuple) or not operations:
        raise PlannerContractError(
            "Planner proposal must contain an immutable non-empty operation list.",
            path="/operations",
        )
    for index, operation in enumerate(operations):
        if type(operation) is not PatchOperation:
            raise PlannerContractError(
                "Planner proposal contains a malformed operation.",
                path=f"/operations/{index}",
                details={"actual_type": type(operation).__name__},
            )
        try:
            operation_type = operation.op
            operation_path = operation.path
            has_value = operation.has_value
        except AttributeError as error:
            raise PlannerContractError(
                "Planner proposal contains an incompletely initialized operation.",
                path=f"/operations/{index}",
            ) from error
        if not isinstance(operation_type, PatchOperationType) or not isinstance(
            operation_path, str
        ):
            raise PlannerContractError(
                "Planner proposal contains a malformed operation.",
                path=f"/operations/{index}",
            )
        if operation_type not in {PatchOperationType.ADD, PatchOperationType.REPLACE}:
            raise PlannerContractError(
                "Planning proposals may only add or replace owned semantic values.",
                path=f"/operations/{index}/op",
                details={"op": operation_type.value},
            )
        if not has_value:
            raise PlannerContractError(
                "Planning operations must carry an explicit value.",
                path=f"/operations/{index}/value",
            )
    return operations


def _record_from_operations(operations: tuple[PatchOperation, ...]) -> PlanningRecord:
    extension_indices = [
        index
        for index, operation in enumerate(operations)
        if operation.path in {"/extensions", _PLANNING_EXTENSION_PATH}
    ]
    if len(extension_indices) != 1:
        raise PlannerContractError(
            "Planner proposal must contain exactly one owned planning-record operation.",
            path="/operations",
            details={"planning_record_operations": len(extension_indices)},
        )

    index = extension_indices[0]
    operation = operations[index]
    value = operation.value
    if operation.path == "/extensions":
        if not isinstance(value, Mapping) or set(value) != {PLANNING_EXTENSION_KEY}:
            raise PlannerContractError(
                "Creating extensions may only create the owned planning namespace.",
                path=f"/operations/{index}/value",
            )
        value = value[PLANNING_EXTENSION_KEY]
    if not isinstance(value, Mapping):
        raise PlannerContractError(
            "Planning-record operation value must be an object.",
            path=f"/operations/{index}/value",
        )
    try:
        return PlanningRecord.from_dict(cast(Mapping[str, Any], value))
    except InvalidDesignIntentError as error:
        raise PlannerContractError(
            f"Planner returned an invalid planning record: {error}",
            path=f"/operations/{index}/value{error.path}",
            details={"cause": error.code},
        ) from error


def _semantic_operations(
    record: PlanningRecord,
    document: Mapping[str, Any],
) -> tuple[PatchOperation, ...]:
    entities = document.get("entities")
    rooms = entities.get("rooms") if isinstance(entities, Mapping) else None
    if not isinstance(rooms, Mapping):
        raise PlannerContractError(
            "Planning context must contain a room registry.",
            path="/entities/rooms",
        )

    expected: list[PatchOperation] = []
    for assignment in record.assignments:
        room = rooms.get(assignment.room_id)
        if not isinstance(room, Mapping):
            raise PlannerContractError(
                "Planning record assigns a room that does not exist in the base revision.",
                path=f"/entities/rooms/{_pointer_token(assignment.room_id)}",
                details={"room_id": assignment.room_id},
            )
        room_path = f"/entities/rooms/{_pointer_token(assignment.room_id)}"
        current_usage = room.get("usage", _MISSING)
        if current_usage != assignment.usage:
            operation_type = (
                PatchOperationType.ADD if current_usage is _MISSING else PatchOperationType.REPLACE
            )
            expected.append(PatchOperation(operation_type, f"{room_path}/usage", assignment.usage))

        if "name" not in room:
            raise PlannerContractError(
                "Planning context room is missing its required name.",
                path=f"{room_path}/name",
                details={"room_id": assignment.room_id},
            )
        if room["name"] != assignment.name:
            expected.append(
                PatchOperation(
                    PatchOperationType.REPLACE,
                    f"{room_path}/name",
                    assignment.name,
                )
            )
    return tuple(expected)


def _require_unverified_constraints(record: PlanningRecord) -> None:
    expected = {"area", "building_type"}
    if record.intent.orientation is not None:
        expected.add("orientation")
    if record.intent.spatial_constraints:
        expected.add("spatial_constraints")
    expected_values = tuple(sorted(expected))
    if record.unverified_constraints != expected_values:
        raise PlannerContractError(
            "Planning record must disclose every unverified design constraint.",
            path="/planning_record/realization/unverified_constraints",
            details={
                "actual": list(record.unverified_constraints),
                "expected": list(expected_values),
            },
        )


def _extension_operation(
    record: PlanningRecord,
    document: Mapping[str, Any],
) -> PatchOperation:
    value = record.to_dict()
    extensions = document.get("extensions", _MISSING)
    if extensions is _MISSING:
        return PatchOperation(
            PatchOperationType.ADD,
            "/extensions",
            {PLANNING_EXTENSION_KEY: value},
        )
    if not isinstance(extensions, Mapping):
        raise PlannerContractError(
            "Planning context extensions must be an object.",
            path="/extensions",
        )
    operation_type = (
        PatchOperationType.REPLACE
        if PLANNING_EXTENSION_KEY in extensions
        else PatchOperationType.ADD
    )
    return PatchOperation(operation_type, _PLANNING_EXTENSION_PATH, value)


def _require_exact_operations(
    actual: tuple[PatchOperation, ...],
    expected: tuple[PatchOperation, ...],
) -> None:
    if len(actual) != len(expected):
        raise PlannerContractError(
            "Planner proposal does not contain the exact required planning operations.",
            path="/operations",
            details={"actual_count": len(actual), "expected_count": len(expected)},
        )
    for index, (actual_operation, expected_operation) in enumerate(
        zip(actual, expected, strict=True)
    ):
        try:
            actual_value = actual_operation.to_dict()
        except (AttributeError, TypeError, ValueError) as error:
            raise PlannerContractError(
                "Planner proposal contains a malformed operation.",
                path=f"/operations/{index}",
            ) from error
        expected_value = expected_operation.to_dict()
        if actual_value != expected_value:
            raise PlannerContractError(
                "Planner operation violates the owned planning contract.",
                path=f"/operations/{index}",
                details={
                    "actual": actual_value,
                    "expected": expected_value,
                },
            )


def _current_extension_value(document: Mapping[str, Any]) -> object:
    extensions = document.get("extensions")
    if not isinstance(extensions, Mapping):
        return _MISSING
    return extensions.get(PLANNING_EXTENSION_KEY, _MISSING)


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
