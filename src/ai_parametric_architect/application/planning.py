"""Trusted orchestration boundary for architecture planning proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ai_parametric_architect.application.authorization import (
    AgentAuthorizationGateway,
    AgentPatchCommitRequest,
)
from ai_parametric_architect.domain import (
    DesignIntent,
    ModelRevision,
    PatchProposal,
    PlannerContractError,
    RevisionConflictError,
)
from ai_parametric_architect.ports import ProposalPlanner, RequirementParser


@dataclass(frozen=True, slots=True)
class PlanningProposalResult:
    """A policy-authorized proposal and the exact revision planned from."""

    intent: DesignIntent
    base_revision: ModelRevision
    proposal: PatchProposal | None

    @property
    def has_changes(self) -> bool:
        return self.proposal is not None

    @property
    def no_change(self) -> bool:
        return self.proposal is None


@dataclass(frozen=True, slots=True)
class PlanningCommitResult:
    """The committed revision, or the unchanged current revision when no work exists."""

    intent: DesignIntent
    base_revision: ModelRevision
    revision: ModelRevision
    proposal: PatchProposal | None
    changed: bool

    @property
    def no_change(self) -> bool:
        return not self.changed


class ArchitecturePlanningService:
    """Parse requirements and route agent output through authorization policy."""

    def __init__(
        self,
        parser: RequirementParser,
        planner: ProposalPlanner,
        authorization_gateway: AgentAuthorizationGateway,
    ) -> None:
        self._parser = parser
        self._planner = planner
        self._authorization_gateway = authorization_gateway

    def propose(self, model_id: str, requirement: str) -> PlanningProposalResult:
        intent = self._parser.parse(requirement)
        if not isinstance(intent, DesignIntent):
            raise PlannerContractError(
                "Requirement parser must return a DesignIntent.",
                path="/intent",
                details={"actual_type": type(intent).__name__},
            )

        current = self._authorization_gateway.current(model_id)
        candidate = self._planner.plan(intent, current)
        if candidate is None:
            self._authorization_gateway.require_no_change(intent, current)
            proposal = None
        else:
            proposal = self._authorization_gateway.authorize(intent, current, candidate)
        return PlanningProposalResult(
            intent=intent,
            base_revision=current,
            proposal=proposal,
        )

    def plan_and_commit(self, model_id: str, requirement: str) -> PlanningCommitResult:
        planned = self.propose(model_id, requirement)
        if planned.proposal is None:
            latest = self._authorization_gateway.current(model_id)
            if latest.revision_number != planned.base_revision.revision_number:
                raise RevisionConflictError(
                    model_id,
                    planned.base_revision.revision_number,
                    latest.revision_number,
                )
            self._authorization_gateway.require_no_change(planned.intent, latest)
            return PlanningCommitResult(
                intent=planned.intent,
                base_revision=planned.base_revision,
                revision=latest,
                proposal=None,
                changed=False,
            )

        committed = self._authorization_gateway.commit(
            model_id,
            AgentPatchCommitRequest(planned.intent, planned.proposal),
        )
        return PlanningCommitResult(
            intent=planned.intent,
            base_revision=planned.base_revision,
            revision=committed,
            proposal=planned.proposal,
            changed=True,
        )
