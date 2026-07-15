from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from ai_parametric_architect.agents import Agent, ConstraintReasoningAgent
from ai_parametric_architect.composition import (
    create_constraint_reasoning_agent,
    create_service,
)
from ai_parametric_architect.domain import ValidationIssue
from ai_parametric_architect.reasoning import (
    ConstraintResolutionPlan,
    ReasoningStatus,
    ResolutionAction,
)

_EXECUTABLE_OR_WORLD_FIELDS = frozenset(
    {
        "coordinates",
        "created_at",
        "entities",
        "geometry",
        "model",
        "model_id",
        "operations",
        "parent_revision",
        "patch",
        "revision",
        "revision_number",
    }
)


def test_validation_error_becomes_a_read_only_symbolic_resolution_plan(
    invalid_overlap: dict[str, Any],
) -> None:
    before = copy.deepcopy(invalid_overlap)
    report = create_service().validate(invalid_overlap)
    issue = next(issue for issue in report.issues if issue.code == "ROOM_OVERLAP")
    agent = create_constraint_reasoning_agent()

    first = agent.run(issue)
    second = agent.run(issue)

    assert isinstance(agent, ConstraintReasoningAgent)
    assert isinstance(agent, Agent)
    assert isinstance(first, ConstraintResolutionPlan)
    assert first == second
    assert first.status is ReasoningStatus.CANDIDATES_AVAILABLE
    assert [candidate.action for candidate in first.candidates] == [
        ResolutionAction.RESIZE_ROOM,
        ResolutionAction.CHANGE_LAYOUT,
    ]
    assert first.issue_code == issue.code
    assert first.issue_path == issue.path
    assert first.entity_ids == issue.entity_ids
    assert _all_mapping_keys(first.to_dict()).isdisjoint(_EXECUTABLE_OR_WORLD_FIELDS)
    assert invalid_overlap == before


def test_schema_error_without_safe_entity_localization_requires_manual_review(
    invalid_overlap: dict[str, Any],
) -> None:
    invalid_overlap.pop("root_building_id")
    report = create_service().validate(invalid_overlap)
    issue = next(issue for issue in report.issues if issue.code == "SCHEMA_REQUIRED")

    plan = create_constraint_reasoning_agent().run(issue)

    assert isinstance(issue, ValidationIssue)
    assert plan.status is ReasoningStatus.MANUAL_REVIEW_REQUIRED
    assert plan.candidates == ()
    assert "base_revision" not in plan.to_dict()
    assert "operations" not in plan.to_dict()


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return set(value).union(
            *(_all_mapping_keys(member) for member in value.values()),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return set().union(*(_all_mapping_keys(member) for member in value))
    return set()
