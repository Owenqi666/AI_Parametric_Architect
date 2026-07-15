from __future__ import annotations

from ai_parametric_architect.domain import PlanningCapacityError


def test_planning_error_has_stable_defensive_shape() -> None:
    details: dict[str, object] = {"requested": 3, "available": ["rom_a"]}
    error = PlanningCapacityError(
        "Not enough room slots.",
        path="/rooms",
        details=details,
    )
    details["available"] = []
    serialized = error.to_dict()
    serialized["details"] = {}

    assert error.to_dict() == {
        "code": "PLANNING_CAPACITY_INSUFFICIENT",
        "path": "/rooms",
        "message": "Not enough room slots.",
        "details": {"requested": 3, "available": ["rom_a"]},
    }
