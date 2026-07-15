from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import PlanningContextError, ensure_json_value
from ai_parametric_architect.reasoning import (
    CONSTRAINT_RESOLUTION_SCHEMA_VERSION,
    RULE_BASED_CONSTRAINT_STRATEGY,
    CandidateSolution,
    ConstraintResolutionPlan,
    ReasoningStatus,
    ResolutionAction,
)


def _candidate(
    *,
    candidate_id: str = "candidate_001",
    action: ResolutionAction | str = ResolutionAction.RESIZE_ROOM,
    entity_ids: tuple[str, ...] = ("rom_living", "rom_bedroom"),
) -> CandidateSolution:
    return CandidateSolution(
        candidate_id=candidate_id,
        action=action,
        entity_ids=entity_ids,
        rationale="Resize the identified rooms, then validate the resulting geometry.",
    )


def _plan(**overrides: object) -> ConstraintResolutionPlan:
    arguments: dict[str, object] = {
        "issue_code": "ROOM_OVERLAP",
        "issue_path": "/entities/rooms",
        "entity_ids": ("rom_living", "rom_bedroom"),
        "status": ReasoningStatus.CANDIDATES_AVAILABLE,
        "candidates": (_candidate(),),
    }
    arguments.update(overrides)
    return ConstraintResolutionPlan(**cast(Any, arguments))


def test_candidate_and_plan_have_stable_json_round_trip() -> None:
    plan = _plan()

    assert CONSTRAINT_RESOLUTION_SCHEMA_VERSION == "1.0.0"
    assert RULE_BASED_CONSTRAINT_STRATEGY == "rule-based-symbolic-candidates-v1"
    assert plan.to_dict() == {
        "schema_version": "1.0.0",
        "strategy": "rule-based-symbolic-candidates-v1",
        "issue_code": "ROOM_OVERLAP",
        "issue_path": "/entities/rooms",
        "entity_ids": ["rom_living", "rom_bedroom"],
        "status": "candidates_available",
        "candidates": [
            {
                "candidate_id": "candidate_001",
                "action": "resize_room",
                "entity_ids": ["rom_living", "rom_bedroom"],
                "rationale": ("Resize the identified rooms, then validate the resulting geometry."),
            }
        ],
    }
    assert ConstraintResolutionPlan.from_dict(plan.to_dict()) == plan
    assert CandidateSolution.from_dict(_candidate().to_dict()) == _candidate()
    ensure_json_value(plan.to_dict())


def test_plan_ir_contains_no_geometry_patch_model_or_revision_fields() -> None:
    serialized = _plan().to_dict()
    forbidden = {
        "coordinates",
        "geometry",
        "model",
        "model_id",
        "operations",
        "patch",
        "revision",
    }

    assert forbidden.isdisjoint(serialized)
    candidate = cast(list[dict[str, object]], serialized["candidates"])[0]
    assert forbidden.isdisjoint(candidate)


def test_manual_review_plan_is_explicit_and_contains_no_candidates() -> None:
    plan = _plan(
        issue_code="UNKNOWN_RULE",
        entity_ids=(),
        status=ReasoningStatus.MANUAL_REVIEW_REQUIRED,
        candidates=(),
    )

    assert plan.status is ReasoningStatus.MANUAL_REVIEW_REQUIRED
    assert plan.candidates == ()


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"candidate_id": "candidate_1"}, "/candidate_id"),
        ({"action": "move_room"}, "/action"),
        ({"entity_ids": ()}, "/entity_ids"),
        ({"entity_ids": ("rom_a", "rom_a")}, "/entity_ids"),
        ({"entity_ids": ["rom_a"]}, "/entity_ids"),
        ({"rationale": ""}, "/rationale"),
        ({"rationale": " padded "}, "/rationale"),
    ],
)
def test_candidate_rejects_invalid_values(overrides: dict[str, object], path: str) -> None:
    arguments: dict[str, object] = {
        "candidate_id": "candidate_001",
        "action": "resize_room",
        "entity_ids": ("rom_a",),
        "rationale": "Resize the room and revalidate it.",
    }
    arguments.update(overrides)

    with pytest.raises(PlanningContextError) as captured:
        CandidateSolution(**cast(Any, arguments))

    assert captured.value.path == path


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"schema_version": "2.0.0"}, "/schema_version"),
        ({"strategy": "Rule Based"}, "/strategy"),
        ({"issue_code": "room overlap"}, "/issue_code"),
        ({"issue_path": "entities/rooms"}, "/issue_path"),
        ({"issue_path": "/entities/~2bad"}, "/issue_path"),
        ({"entity_ids": ["rom_a"]}, "/entity_ids"),
        ({"entity_ids": ("rom_a", "rom_a")}, "/entity_ids"),
        ({"status": "unknown"}, "/status"),
        ({"candidates": []}, "/candidates"),
        ({"candidates": ()}, "/candidates"),
        (
            {
                "status": ReasoningStatus.MANUAL_REVIEW_REQUIRED,
                "candidates": (_candidate(),),
            },
            "/candidates",
        ),
        (
            {"candidates": (_candidate(entity_ids=("rom_unreported",)),)},
            "/candidates",
        ),
        (
            {
                "candidates": (
                    _candidate(candidate_id="candidate_001"),
                    _candidate(candidate_id="candidate_001"),
                )
            },
            "/candidates",
        ),
    ],
)
def test_plan_rejects_invalid_values(overrides: dict[str, object], path: str) -> None:
    with pytest.raises(PlanningContextError) as captured:
        _plan(**overrides)

    assert captured.value.path == path


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**_plan().to_dict(), "extra": True},
        {**_plan().to_dict(), "issue_code": 1},
        {**_plan().to_dict(), "issue_path": 1},
        {**_plan().to_dict(), "entity_ids": "rom_a"},
        {**_plan().to_dict(), "status": 1},
        {**_plan().to_dict(), "candidates": "invalid"},
        {**_plan().to_dict(), "candidates": ["invalid"]},
        {**_plan().to_dict(), "strategy": 1},
        {**_plan().to_dict(), "schema_version": 1},
    ],
)
def test_plan_from_dict_rejects_malformed_documents(payload: dict[str, Any]) -> None:
    with pytest.raises(PlanningContextError):
        ConstraintResolutionPlan.from_dict(payload)


def test_candidate_from_dict_is_strict_and_nested_paths_are_complete() -> None:
    with pytest.raises(PlanningContextError):
        CandidateSolution.from_dict({})
    for field in ("candidate_id", "action", "entity_ids", "rationale"):
        payload = _candidate().to_dict()
        payload[field] = 1
        with pytest.raises(PlanningContextError):
            CandidateSolution.from_dict(payload)

    payload = _plan().to_dict()
    cast(list[dict[str, object]], payload["candidates"])[0]["action"] = "invalid"
    with pytest.raises(PlanningContextError) as captured:
        ConstraintResolutionPlan.from_dict(payload)

    assert captured.value.path == "/candidates/0/action"


def test_values_are_frozen_slotted_and_serialization_is_defensive() -> None:
    candidate = _candidate()
    plan = _plan()
    payload = plan.to_dict()
    cast(list[str], payload["entity_ids"])[0] = "changed"
    cast(list[dict[str, object]], payload["candidates"])[0]["rationale"] = "changed"

    with pytest.raises((AttributeError, FrozenInstanceError)):
        candidate.action = ResolutionAction.MOVE_WALL  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError)):
        plan.status = ReasoningStatus.MANUAL_REVIEW_REQUIRED  # type: ignore[misc]

    assert not hasattr(candidate, "__dict__")
    assert not hasattr(plan, "__dict__")
    assert plan.entity_ids == ("rom_living", "rom_bedroom")
    assert plan.candidates[0].rationale.startswith("Resize")
