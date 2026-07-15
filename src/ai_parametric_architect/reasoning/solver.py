"""Deterministic, conservative constraint-resolution rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ai_parametric_architect.domain.issues import ValidationIssue
from ai_parametric_architect.domain.json_pointers import decode_json_pointer
from ai_parametric_architect.reasoning.constraints import (
    CandidateSolution,
    ConstraintResolutionPlan,
    ReasoningStatus,
    ResolutionAction,
    validate_error_issue,
)

_ROOM_OVERLAP: Final = "ROOM_OVERLAP"
_WALL_ZERO_LENGTH: Final = "WALL_ZERO_LENGTH"


@dataclass(frozen=True, slots=True)
class RuleBasedConstraintSolver:
    """Map safely localized validator errors to symbolic alternatives only."""

    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        validate_error_issue(issue)

        candidates = self._candidates(issue)
        status = (
            ReasoningStatus.CANDIDATES_AVAILABLE
            if candidates
            else ReasoningStatus.MANUAL_REVIEW_REQUIRED
        )
        return ConstraintResolutionPlan(
            issue_code=issue.code,
            issue_path=issue.path,
            entity_ids=issue.entity_ids,
            status=status,
            candidates=candidates,
        )

    @staticmethod
    def _candidates(issue: ValidationIssue) -> tuple[CandidateSolution, ...]:
        if (
            issue.code == _ROOM_OVERLAP
            and issue.path == "/entities/rooms"
            and len(issue.entity_ids) == 2
        ):
            return (
                CandidateSolution(
                    candidate_id="candidate_001",
                    action=ResolutionAction.RESIZE_ROOM,
                    entity_ids=issue.entity_ids,
                    rationale=(
                        "Resize the identified rooms to eliminate their overlap; a later "
                        "patch stage must supply geometry and revalidate it."
                    ),
                ),
                CandidateSolution(
                    candidate_id="candidate_002",
                    action=ResolutionAction.CHANGE_LAYOUT,
                    entity_ids=issue.entity_ids,
                    rationale=(
                        "Re-plan the identified rooms as an alternative layout; a later "
                        "planning stage must define and validate the geometry."
                    ),
                ),
            )
        if issue.code == _WALL_ZERO_LENGTH and _is_localized_wall_axis(issue):
            return (
                CandidateSolution(
                    candidate_id="candidate_001",
                    action=ResolutionAction.MOVE_WALL,
                    entity_ids=issue.entity_ids,
                    rationale=(
                        "Move one endpoint of the identified wall to restore non-zero length; "
                        "a later patch stage must supply geometry and revalidate it."
                    ),
                ),
                CandidateSolution(
                    candidate_id="candidate_002",
                    action=ResolutionAction.CHANGE_LAYOUT,
                    entity_ids=issue.entity_ids,
                    rationale=(
                        "Re-plan the layout containing the identified wall; a later planning "
                        "stage must define and validate the geometry."
                    ),
                ),
            )
        return ()


def _is_localized_wall_axis(issue: ValidationIssue) -> bool:
    if len(issue.entity_ids) != 1:
        return False
    return decode_json_pointer(issue.path) == (
        "entities",
        "walls",
        issue.entity_ids[0],
        "axis",
    )
