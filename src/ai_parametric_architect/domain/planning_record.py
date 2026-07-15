"""Versioned planning trace stored in the model extension namespace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError

PLANNING_EXTENSION_KEY: Final = "dev.ai-parametric-architect.design-intent"
PLANNING_RECORD_VERSION: Final = "1.0.0"
PLANNING_REALIZATION_SCOPE: Final = "semantic-room-assignment"


@dataclass(frozen=True, slots=True)
class RoomAssignment:
    room_id: str
    usage: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.room_id, str) or not self.room_id:
            raise InvalidDesignIntentError("Assignment room_id cannot be empty.")
        if not isinstance(self.usage, str) or not self.usage:
            raise InvalidDesignIntentError("Assignment usage cannot be empty.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidDesignIntentError("Assignment name cannot be empty.")

    def to_dict(self) -> dict[str, str]:
        return {"room_id": self.room_id, "usage": self.usage, "name": self.name}


@dataclass(frozen=True, slots=True)
class PlanningRecord:
    intent: DesignIntent
    assignments: tuple[RoomAssignment, ...]
    unverified_constraints: tuple[str, ...]
    schema_version: str = PLANNING_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PLANNING_RECORD_VERSION:
            raise InvalidDesignIntentError("Unsupported planning record version.")
        if not isinstance(self.intent, DesignIntent):
            raise InvalidDesignIntentError("Planning record intent is invalid.")
        if not isinstance(self.assignments, tuple) or not all(
            isinstance(assignment, RoomAssignment) for assignment in self.assignments
        ):
            raise InvalidDesignIntentError("Planning assignments must be immutable values.")
        room_ids = tuple(assignment.room_id for assignment in self.assignments)
        if len(room_ids) != len(set(room_ids)):
            raise InvalidDesignIntentError("Planning assignment room IDs must be unique.")
        if tuple(assignment.usage for assignment in self.assignments) != self.intent.rooms:
            raise InvalidDesignIntentError(
                "Planning assignments must realize requested room usages in order."
            )
        if (
            not isinstance(self.unverified_constraints, tuple)
            or tuple(sorted(set(self.unverified_constraints))) != self.unverified_constraints
            or not all(isinstance(value, str) and value for value in self.unverified_constraints)
        ):
            raise InvalidDesignIntentError("Unverified constraints must be sorted unique strings.")
        expected_constraints = {"area", "building_type"}
        if self.intent.orientation is not None:
            expected_constraints.add("orientation")
        if self.intent.spatial_constraints:
            expected_constraints.add("spatial_constraints")
        if self.unverified_constraints != tuple(sorted(expected_constraints)):
            raise InvalidDesignIntentError(
                "Semantic room assignment must explicitly record every unverified constraint."
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PlanningRecord:
        if set(value) != {"schema_version", "intent", "realization"}:
            raise InvalidDesignIntentError("Planning record has unexpected fields.")
        intent_value = value.get("intent")
        realization = value.get("realization")
        if not isinstance(intent_value, Mapping) or not isinstance(realization, Mapping):
            raise InvalidDesignIntentError("Planning record sections must be objects.")
        if set(realization) != {"scope", "assignments", "unverified_constraints"}:
            raise InvalidDesignIntentError("Planning realization has unexpected fields.")
        if realization.get("scope") != PLANNING_REALIZATION_SCOPE:
            raise InvalidDesignIntentError("Planning realization scope is unsupported.")
        assignments_value = realization.get("assignments")
        constraints_value = realization.get("unverified_constraints")
        if not isinstance(assignments_value, Sequence) or isinstance(
            assignments_value, (str, bytes)
        ):
            raise InvalidDesignIntentError("Planning assignments must be an array.")
        assignments: list[RoomAssignment] = []
        for assignment in assignments_value:
            if not isinstance(assignment, Mapping) or set(assignment) != {
                "room_id",
                "usage",
                "name",
            }:
                raise InvalidDesignIntentError("Planning assignment is malformed.")
            room_id = assignment.get("room_id")
            usage = assignment.get("usage")
            name = assignment.get("name")
            if (
                not isinstance(room_id, str)
                or not isinstance(usage, str)
                or not isinstance(name, str)
            ):
                raise InvalidDesignIntentError("Planning assignment fields must be strings.")
            assignments.append(RoomAssignment(room_id=room_id, usage=usage, name=name))
        if not isinstance(constraints_value, Sequence) or isinstance(
            constraints_value, (str, bytes)
        ):
            raise InvalidDesignIntentError("Unverified constraints must be an array.")
        if not all(isinstance(item, str) for item in constraints_value):
            raise InvalidDesignIntentError("Unverified constraints must be strings.")
        schema_version = value.get("schema_version")
        if not isinstance(schema_version, str):
            raise InvalidDesignIntentError("Planning record schema_version must be a string.")
        return cls(
            schema_version=schema_version,
            intent=DesignIntent.from_dict(intent_value),
            assignments=tuple(assignments),
            unverified_constraints=tuple(constraints_value),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "intent": self.intent.to_dict(),
            "realization": {
                "scope": PLANNING_REALIZATION_SCOPE,
                "assignments": [assignment.to_dict() for assignment in self.assignments],
                "unverified_constraints": list(self.unverified_constraints),
            },
        }
