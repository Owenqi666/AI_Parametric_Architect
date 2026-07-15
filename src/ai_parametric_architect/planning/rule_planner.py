"""Deterministic semantic planning over existing room slots."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any, Final

from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    DesignIntent,
    InvalidDesignIntentError,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlanningCapacityError,
    PlanningContextError,
    PlanningRecord,
    RoomAssignment,
)
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.planning.rules import RuleBasedFloorPlanPlanner
from ai_parametric_architect.ports import FloorPlanPlanner

RULE_BASED_PLANNER_PROVENANCE: Final = "planner:rule-based-v1"
RULE_BASED_PLANNER_RATIONALE: Final = (
    "Assign requested room semantics and record unverified design constraints."
)

_BASE_UNVERIFIED_CONSTRAINTS: Final = ("area", "building_type")
_CANONICAL_USAGE_NAMES: Final = {
    "bathroom": "Bathroom",
    "bedroom": "Bedroom",
    "dining": "Dining Room",
    "kitchen": "Kitchen",
    "living": "Living Room",
    "study": "Study",
}
_WORD_SEPARATOR = re.compile(r"[-_]+")


class RuleBasedPlanner:
    """Assign semantic intent to existing rooms without touching geometry."""

    def __init__(
        self,
        floor_plan_planner: FloorPlanPlanner[FloorPlanProposal] | None = None,
    ) -> None:
        self._floor_plan_planner = (
            RuleBasedFloorPlanPlanner() if floor_plan_planner is None else floor_plan_planner
        )

    def plan(
        self,
        intent: DesignIntent,
        base_revision: ModelRevision,
    ) -> PatchProposal | None:
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Rule-based planning requires a validated DesignIntent.",
                path="/intent",
                details={"reason": "INVALID_INTENT_TYPE"},
            )
        if not isinstance(base_revision, ModelRevision):
            raise PlanningContextError(
                "Rule-based planning requires a ModelRevision context.",
                path="/base_revision",
                details={"reason": "INVALID_REVISION_TYPE"},
            )
        floor_plan = self._floor_plan_planner.plan(intent)
        if not isinstance(floor_plan, FloorPlanProposal) or floor_plan.intent != intent:
            raise PlanningContextError(
                "Floor-plan planner violated the proposal contract.",
                path="/floor_plan",
                details={"reason": "INVALID_FLOOR_PLAN_OUTPUT"},
            )
        return self.plan_from_floor_plan(floor_plan, base_revision)

    def plan_from_floor_plan(
        self,
        floor_plan: FloorPlanProposal,
        base_revision: ModelRevision,
    ) -> PatchProposal | None:
        """Convert a detached Plan IR into a semantic-only patch proposal."""

        if not isinstance(floor_plan, FloorPlanProposal):
            raise PlanningContextError(
                "Rule-based patch planning requires a FloorPlanProposal.",
                path="/floor_plan",
                details={"reason": "INVALID_FLOOR_PLAN_TYPE"},
            )
        if not isinstance(base_revision, ModelRevision):
            raise PlanningContextError(
                "Rule-based planning requires a ModelRevision context.",
                path="/base_revision",
                details={"reason": "INVALID_REVISION_TYPE"},
            )

        document = base_revision.document
        rooms = _room_slots(document)
        extensions, extensions_present = _extensions(document)
        existing_record = _existing_planning_record(extensions)

        requested_count = len(floor_plan.rooms)
        if requested_count > len(rooms):
            raise PlanningCapacityError(
                "The model does not contain enough room slots for the design intent.",
                path="/entities/rooms",
                details={
                    "reason": "INSUFFICIENT_ROOM_SLOTS",
                    "requested": requested_count,
                    "available": len(rooms),
                },
            )

        selected_rooms = rooms[:requested_count]
        assignments = _assignments(floor_plan, selected_rooms)
        intent = floor_plan.intent
        record = PlanningRecord(
            intent=intent,
            assignments=assignments,
            unverified_constraints=_unverified_constraints(intent),
        )
        record_value = record.to_dict()

        operations: list[PatchOperation] = []
        for assignment, (room_id, room) in zip(assignments, selected_rooms, strict=True):
            room_path = f"/entities/rooms/{_pointer_token(room_id)}"
            if "usage" not in room:
                operations.append(PatchOperation("add", f"{room_path}/usage", assignment.usage))
            elif room["usage"] != assignment.usage:
                operations.append(PatchOperation("replace", f"{room_path}/usage", assignment.usage))
            if room["name"] != assignment.name:
                operations.append(PatchOperation("replace", f"{room_path}/name", assignment.name))

        if existing_record != record:
            if not extensions_present:
                operations.append(
                    PatchOperation(
                        "add",
                        "/extensions",
                        {PLANNING_EXTENSION_KEY: record_value},
                    )
                )
            else:
                extension_path = f"/extensions/{_pointer_token(PLANNING_EXTENSION_KEY)}"
                operation = "replace" if existing_record is not None else "add"
                operations.append(PatchOperation(operation, extension_path, record_value))

        if not operations:
            return None
        return PatchProposal(
            base_model_id=base_revision.model_id,
            base_revision=base_revision.revision_number,
            operations=tuple(operations),
            provenance=RULE_BASED_PLANNER_PROVENANCE,
            rationale=RULE_BASED_PLANNER_RATIONALE,
            affected_entity_ids=tuple(assignment.room_id for assignment in assignments),
        )

    def generate(
        self,
        floor_plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        """Implement the patch-generation port without applying the proposal."""

        return self.plan_from_floor_plan(floor_plan, current_revision)


def _room_slots(document: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    entities = _mapping_member(document, "entities", path="/entities")
    rooms = _mapping_member(entities, "rooms", path="/entities/rooms")
    slots: list[tuple[str, Mapping[str, Any]]] = []
    for room_id in sorted(rooms):
        if not isinstance(room_id, str) or not room_id:
            raise PlanningContextError(
                "Room registry keys must be non-empty strings.",
                path="/entities/rooms",
                details={"reason": "INVALID_ROOM_KEY"},
            )
        room_path = f"/entities/rooms/{_pointer_token(room_id)}"
        room_value = rooms[room_id]
        if not isinstance(room_value, Mapping):
            raise PlanningContextError(
                "Room registry values must be objects.",
                path=room_path,
                details={"reason": "INVALID_ROOM_VALUE", "room_id": room_id},
            )
        room = room_value
        if room.get("id") != room_id or room.get("entity_type") != "room":
            raise PlanningContextError(
                "Room registry identity is inconsistent.",
                path=room_path,
                details={"reason": "INVALID_ROOM_IDENTITY", "room_id": room_id},
            )
        name = room.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PlanningContextError(
                "Room slots require a non-empty name.",
                path=f"{room_path}/name",
                details={"reason": "INVALID_ROOM_NAME", "room_id": room_id},
            )
        if "usage" in room and (
            not isinstance(room["usage"], str) or not str(room["usage"]).strip()
        ):
            raise PlanningContextError(
                "Existing room usage must be a non-empty string.",
                path=f"{room_path}/usage",
                details={"reason": "INVALID_ROOM_USAGE", "room_id": room_id},
            )
        slots.append((room_id, room))
    return tuple(slots)


def _extensions(
    document: Mapping[str, Any],
) -> tuple[Mapping[str, Any], bool]:
    if "extensions" not in document:
        return {}, False
    value = document["extensions"]
    if not isinstance(value, Mapping):
        raise PlanningContextError(
            "Model extensions must be an object.",
            path="/extensions",
            details={"reason": "INVALID_EXTENSIONS_CONTAINER"},
        )
    return value, True


def _existing_planning_record(extensions: Mapping[str, Any]) -> PlanningRecord | None:
    if PLANNING_EXTENSION_KEY not in extensions:
        return None
    value = extensions[PLANNING_EXTENSION_KEY]
    if not isinstance(value, Mapping):
        raise PlanningContextError(
            "The planning extension must contain a versioned planning record.",
            path=f"/extensions/{_pointer_token(PLANNING_EXTENSION_KEY)}",
            details={"reason": "INVALID_PLANNING_RECORD"},
        )
    try:
        return PlanningRecord.from_dict(value)
    except InvalidDesignIntentError as error:
        raise PlanningContextError(
            "The existing planning extension is malformed or unsupported.",
            path=f"/extensions/{_pointer_token(PLANNING_EXTENSION_KEY)}",
            details={"reason": "INVALID_PLANNING_RECORD"},
        ) from error


def _mapping_member(
    parent: Mapping[str, Any],
    member: str,
    *,
    path: str,
) -> Mapping[str, Any]:
    value = parent.get(member)
    if not isinstance(value, Mapping):
        raise PlanningContextError(
            f"Planning context member {member!r} must be an object.",
            path=path,
            details={"reason": "INVALID_CONTEXT_MEMBER", "member": member},
        )
    return value


def _assignments(
    floor_plan: FloorPlanProposal,
    selected_rooms: tuple[tuple[str, Mapping[str, Any]], ...],
) -> tuple[RoomAssignment, ...]:
    usages = tuple(room.room_type for room in floor_plan.rooms)
    totals = Counter(usages)
    occurrences: defaultdict[str, int] = defaultdict(int)
    assignments: list[RoomAssignment] = []
    for usage, (room_id, _room) in zip(usages, selected_rooms, strict=True):
        occurrences[usage] += 1
        base_name = _usage_name(usage)
        name = f"{base_name} {occurrences[usage]}" if totals[usage] > 1 else base_name
        assignments.append(RoomAssignment(room_id=room_id, usage=usage, name=name))
    return tuple(assignments)


def _usage_name(usage: str) -> str:
    configured = _CANONICAL_USAGE_NAMES.get(usage)
    if configured is not None:
        return configured
    words = tuple(word for word in _WORD_SEPARATOR.split(usage) if word)
    return " ".join(word.capitalize() for word in words)


def _unverified_constraints(intent: DesignIntent) -> tuple[str, ...]:
    values = list(_BASE_UNVERIFIED_CONSTRAINTS)
    if intent.orientation is not None:
        values.append("orientation")
    if intent.spatial_constraints:
        values.append("spatial_constraints")
    return tuple(values)


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
