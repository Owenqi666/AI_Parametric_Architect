"""Trusted application gateway for agent-produced patch proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ai_parametric_architect.application.editing import EditingService
from ai_parametric_architect.domain import (
    DesignIntent,
    ModelRevision,
    PatchProposal,
    PlannerContractError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.policy import AgentAuthorizationPolicy


@dataclass(frozen=True, slots=True)
class AgentPatchCommitRequest:
    """Explicit request to authorize, validate, and commit one agent proposal.

    Evaluation reports are deliberately not accepted as commit requests.  The
    authenticated audit identity travels separately through the gateway and is
    never inferred from proposal-controlled provenance.
    """

    intent: DesignIntent
    proposal: PatchProposal

    def __post_init__(self) -> None:
        if type(self.intent) is not DesignIntent:
            raise PlannerContractError(
                "Agent commit requests require an exact DesignIntent value.",
                path="/request/intent",
                details={"actual_type": type(self.intent).__name__},
            )
        if type(self.proposal) is not PatchProposal:
            raise PlannerContractError(
                "Agent commit requests require an exact PatchProposal value.",
                path="/request/proposal",
                details={"actual_type": type(self.proposal).__name__},
            )


class AgentAuthorizationGateway:
    """Apply policy immediately before core validation and revision commit."""

    def __init__(
        self,
        editing_service: EditingService,
        policy: AgentAuthorizationPolicy,
        audit_identity: TrustedAuditIdentity,
    ) -> None:
        if type(audit_identity) is not TrustedAuditIdentity:
            raise TypeError("Agent authorization gateway requires a trusted audit identity.")
        self._editing_service = editing_service
        self._policy = policy
        self._audit_identity = audit_identity

    def current(self, model_id: str) -> ModelRevision:
        """Read the current immutable snapshot without exposing a repository."""

        return self._editing_service.current(model_id)

    def authorize(
        self,
        intent: DesignIntent,
        current: ModelRevision,
        candidate: object,
    ) -> PatchProposal:
        """Review a detached candidate without validating or committing it."""

        return self._policy.authorize(intent, current, candidate)

    def require_no_change(
        self,
        intent: DesignIntent,
        current: ModelRevision,
    ) -> None:
        """Verify an explicit no-change planning result."""

        self._policy.require_no_change(intent, current)

    def commit(self, model_id: str, request: object) -> ModelRevision:
        """Authorize a typed request, then run core validation and CAS commit."""

        if type(request) is not AgentPatchCommitRequest:
            raise PlannerContractError(
                "Only an explicit AgentPatchCommitRequest may enter the commit gateway.",
                path="/request",
                details={"actual_type": type(request).__name__},
            )
        commit_request = request
        current = self._editing_service.current(model_id)
        authorized = self._policy.authorize(
            commit_request.intent,
            current,
            commit_request.proposal,
        )
        return self._editing_service.apply_patch(
            model_id,
            authorized,
            audit_identity=self._audit_identity,
        )
