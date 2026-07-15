"""Immutable, serializable evaluation scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_parametric_architect.domain.design_intent import DesignIntent, SpatialConstraint
from ai_parametric_architect.domain.editing_errors import NonJsonValueError
from ai_parametric_architect.domain.guardrails import StrictJsonTreeGuard
from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError


class InvalidScenarioError(ValueError):
    """Raised when an evaluation scenario is malformed or internally inconsistent."""

    def __init__(self, message: str, *, path: str = "") -> None:
        super().__init__(message)
        self.path = path


@dataclass(frozen=True, slots=True)
class Scenario:
    """One expected requirement-to-intent/constraint behavior."""

    input_requirement: str
    expected_intent: DesignIntent
    expected_constraints: tuple[SpatialConstraint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.input_requirement, str) or not self.input_requirement.strip():
            raise InvalidScenarioError(
                "Scenario input_requirement must be a non-empty string.",
                path="/input_requirement",
            )
        if not isinstance(self.expected_intent, DesignIntent):
            raise InvalidScenarioError(
                "Scenario expected_intent must be a DesignIntent.",
                path="/expected_intent",
            )
        if not isinstance(self.expected_constraints, tuple) or not all(
            isinstance(constraint, SpatialConstraint) for constraint in self.expected_constraints
        ):
            raise InvalidScenarioError(
                "Scenario expected_constraints must be an immutable tuple of constraints.",
                path="/expected_constraints",
            )
        if self.expected_constraints != self.expected_intent.spatial_constraints:
            raise InvalidScenarioError(
                "Scenario constraints must equal the constraints in expected_intent.",
                path="/expected_constraints",
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Scenario:
        try:
            StrictJsonTreeGuard().require(value)
        except NonJsonValueError as error:
            raise InvalidScenarioError(
                f"Scenario must be a strict standard JSON tree: {error}",
                path=error.path or "/",
            ) from error
        if type(value) is not dict:
            raise InvalidScenarioError(
                "Scenario root must be a JSON object.",
                path="/",
            )
        expected_fields = {
            "input_requirement",
            "expected_intent",
            "expected_constraints",
        }
        if set(value) != expected_fields:
            raise InvalidScenarioError("Scenario has missing or unexpected fields.")

        requirement = value.get("input_requirement")
        intent_value = value.get("expected_intent")
        constraints_value = value.get("expected_constraints")
        if not isinstance(requirement, str):
            raise InvalidScenarioError(
                "Scenario input_requirement must be a string.",
                path="/input_requirement",
            )
        if not isinstance(intent_value, Mapping):
            raise InvalidScenarioError(
                "Scenario expected_intent must be an object.",
                path="/expected_intent",
            )
        if not isinstance(constraints_value, Sequence) or isinstance(
            constraints_value, (str, bytes)
        ):
            raise InvalidScenarioError(
                "Scenario expected_constraints must be an array.",
                path="/expected_constraints",
            )

        try:
            intent = DesignIntent.from_dict(intent_value)
        except InvalidDesignIntentError as error:
            raise InvalidScenarioError(str(error), path=f"/expected_intent{error.path}") from error

        constraints: list[SpatialConstraint] = []
        for index, constraint_value in enumerate(constraints_value):
            if not isinstance(constraint_value, Mapping):
                raise InvalidScenarioError(
                    "Each expected constraint must be an object.",
                    path=f"/expected_constraints/{index}",
                )
            try:
                constraints.append(SpatialConstraint.from_dict(constraint_value))
            except InvalidDesignIntentError as error:
                raise InvalidScenarioError(
                    str(error), path=f"/expected_constraints/{index}{error.path}"
                ) from error

        return cls(
            input_requirement=requirement,
            expected_intent=intent,
            expected_constraints=tuple(constraints),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "input_requirement": self.input_requirement,
            "expected_intent": self.expected_intent.to_dict(),
            "expected_constraints": [
                constraint.to_dict() for constraint in self.expected_constraints
            ],
        }
