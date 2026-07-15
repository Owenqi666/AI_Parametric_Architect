from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import PlanningContextError, Severity, ValidationIssue
from ai_parametric_architect.reasoning import (
    ReasoningStatus,
    ResolutionAction,
    RuleBasedConstraintSolver,
)


def _issue(
    *,
    code: str = "ROOM_OVERLAP",
    severity: Severity = Severity.ERROR,
    path: str = "/entities/rooms",
    entity_ids: tuple[str, ...] = ("rom_living", "rom_bedroom"),
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message="The identified geometry violates a constraint.",
        path=path,
        entity_ids=entity_ids,
        details={"overlap_area": 2.5},
    )


def test_room_overlap_maps_to_resize_and_change_layout_candidates() -> None:
    issue = _issue()

    plan = RuleBasedConstraintSolver().solve(issue)

    assert plan.issue_code == issue.code
    assert plan.issue_path == issue.path
    assert plan.entity_ids == issue.entity_ids
    assert plan.status is ReasoningStatus.CANDIDATES_AVAILABLE
    assert [candidate.candidate_id for candidate in plan.candidates] == [
        "candidate_001",
        "candidate_002",
    ]
    assert [candidate.action for candidate in plan.candidates] == [
        ResolutionAction.RESIZE_ROOM,
        ResolutionAction.CHANGE_LAYOUT,
    ]
    assert all(candidate.entity_ids == issue.entity_ids for candidate in plan.candidates)


def test_zero_length_wall_maps_to_move_wall_and_change_layout_candidates() -> None:
    issue = _issue(
        code="WALL_ZERO_LENGTH",
        path="/entities/walls/wal_north/axis",
        entity_ids=("wal_north",),
    )

    plan = RuleBasedConstraintSolver().solve(issue)

    assert [candidate.action for candidate in plan.candidates] == [
        ResolutionAction.MOVE_WALL,
        ResolutionAction.CHANGE_LAYOUT,
    ]
    assert all(candidate.entity_ids == ("wal_north",) for candidate in plan.candidates)


@pytest.mark.parametrize(
    "issue",
    [
        _issue(path="/entities/walls"),
        _issue(
            code="WALL_ZERO_LENGTH",
            path="/entities/rooms/rom_a/geometry",
            entity_ids=("rom_a",),
        ),
        _issue(
            code="WALL_ZERO_LENGTH",
            path="/entities/walls/wal_other/axis",
            entity_ids=("wal_a",),
        ),
    ],
)
def test_known_code_with_mismatched_registry_identity_requires_manual_review(
    issue: ValidationIssue,
) -> None:
    plan = RuleBasedConstraintSolver().solve(issue)

    assert plan.status is ReasoningStatus.MANUAL_REVIEW_REQUIRED
    assert plan.candidates == ()


@pytest.mark.parametrize(
    "issue",
    [
        _issue(code="UNSUPPORTED_GEOMETRY_RULE", entity_ids=("rom_living",)),
        _issue(entity_ids=()),
        _issue(code="WALL_ZERO_LENGTH", entity_ids=()),
        _issue(code="WALL_ZERO_LENGTH", entity_ids=("wal_a", "wal_b")),
    ],
)
def test_unknown_or_unsafely_localized_issue_requires_manual_review(
    issue: ValidationIssue,
) -> None:
    plan = RuleBasedConstraintSolver().solve(issue)

    assert plan.status is ReasoningStatus.MANUAL_REVIEW_REQUIRED
    assert plan.candidates == ()


def test_solver_is_deterministic_and_does_not_modify_issue() -> None:
    issue = _issue()
    before = issue.to_dict()
    solver = RuleBasedConstraintSolver()

    first = solver.solve(issue)
    second = solver.solve(issue)

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert issue.to_dict() == before
    assert "overlap_area" not in first.to_dict()


@pytest.mark.parametrize("severity", [Severity.WARNING, Severity.INFO])
def test_non_error_issue_is_rejected_with_structured_context(severity: Severity) -> None:
    with pytest.raises(PlanningContextError) as captured:
        RuleBasedConstraintSolver().solve(_issue(severity=severity))

    assert captured.value.to_dict() == {
        "code": "PLANNING_CONTEXT_INVALID",
        "path": "/issue/severity",
        "message": "Constraint rules only accept error-severity issues.",
        "details": {"reason": "NON_ERROR_ISSUE", "severity": severity.value},
    }


def test_solver_rejects_invalid_input_type() -> None:
    with pytest.raises(PlanningContextError) as captured:
        RuleBasedConstraintSolver().solve(cast(Any, {"code": "ROOM_OVERLAP"}))

    assert captured.value.path == "/issue"
    assert captured.value.details == {"reason": "INVALID_ISSUE_TYPE"}


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"code": ""}, "/issue/code"),
        ({"path": cast(Any, None)}, "/issue/path"),
        ({"path": "/entities/~2bad"}, "/issue/path"),
        ({"entity_ids": cast(Any, ["rom_a"])}, "/issue/entity_ids"),
        ({"entity_ids": cast(Any, ("",))}, "/issue/entity_ids"),
        ({"entity_ids": ("rom_a", "rom_a")}, "/issue/entity_ids"),
        ({"message": ""}, "/issue/message"),
    ],
)
def test_solver_rejects_malformed_issue_snapshots(overrides: dict[str, object], path: str) -> None:
    arguments: dict[str, object] = {
        "code": "ROOM_OVERLAP",
        "severity": Severity.ERROR,
        "message": "Invalid geometry.",
        "path": "/entities/rooms",
        "entity_ids": ("rom_a", "rom_b"),
    }
    arguments.update(overrides)
    issue = ValidationIssue(**cast(Any, arguments))

    with pytest.raises(PlanningContextError) as captured:
        RuleBasedConstraintSolver().solve(issue)

    assert captured.value.path == path


def test_solver_rejects_malformed_severity_without_attribute_error() -> None:
    issue = _issue()
    object.__setattr__(issue, "severity", "error")

    with pytest.raises(PlanningContextError) as captured:
        RuleBasedConstraintSolver().solve(issue)

    assert captured.value.path == "/issue/severity"
    assert captured.value.details == {
        "reason": "INVALID_SEVERITY_TYPE",
        "actual_type": "str",
    }
