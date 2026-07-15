from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from ai_parametric_architect.application import (
    AgentAuthorizationGateway,
    AgentPatchCommitRequest,
    EditingService,
)
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlannerContractError,
    TrustedAuditIdentity,
)


def _intent() -> DesignIntent:
    return DesignIntent(building_type="house", area=60, rooms=("bedroom",))


def _revision(number: int) -> ModelRevision:
    return ModelRevision(
        model_id="mdl_house",
        revision_number=number,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        parent_revision=None if number == 0 else number - 1,
        document={
            "schema_version": "1.0.0",
            "model_id": "mdl_house",
            "revision": number,
            "entities": {"rooms": {}},
        },
    )


def _proposal() -> PatchProposal:
    return PatchProposal(
        base_model_id="mdl_house",
        base_revision=0,
        operations=(PatchOperation("add", "/metadata", {"source": "agent"}),),
        provenance="planner:claimed-other-agent",
        rationale="A detached test proposal.",
    )


def _identity() -> TrustedAuditIdentity:
    return TrustedAuditIdentity(
        actor_id="trusted-planning-agent",
        actor_type=AuditActorType.AGENT,
        agent_version="test-v1",
        trace_id="trace:authorization-unit",
    )


class SpyPolicy:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def authorize(
        self,
        intent: DesignIntent,
        current: ModelRevision,
        candidate: object,
    ) -> PatchProposal:
        self.events.append("policy")
        assert intent == _intent()
        assert current.revision_number == 0
        assert type(candidate) is PatchProposal
        return candidate

    def require_no_change(self, intent: DesignIntent, current: ModelRevision) -> None:
        self.events.append("no-change-policy")


class SpyEditingService(EditingService):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.identities: list[TrustedAuditIdentity] = []

    def current(self, model_id: str) -> ModelRevision:
        self.events.append("snapshot")
        assert model_id == "mdl_house"
        return _revision(0)

    def apply_patch(
        self,
        model_id: str,
        proposal: PatchProposal,
        *,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        self.events.append("core-validation-commit")
        assert model_id == "mdl_house"
        assert proposal is not None
        self.identities.append(audit_identity)
        return _revision(1)


def test_gateway_orders_policy_before_core_validation_and_commit() -> None:
    events: list[str] = []
    editing = SpyEditingService(events)
    identity = _identity()
    gateway = AgentAuthorizationGateway(editing, SpyPolicy(events), identity)

    committed = gateway.commit(
        "mdl_house",
        AgentPatchCommitRequest(_intent(), _proposal()),
    )

    assert committed.revision_number == 1
    assert events == ["snapshot", "policy", "core-validation-commit"]
    assert editing.identities == [identity]


def test_non_request_evidence_is_rejected_before_reading_world_state() -> None:
    events: list[str] = []
    gateway = AgentAuthorizationGateway(
        SpyEditingService(events),
        SpyPolicy(events),
        _identity(),
    )

    with pytest.raises(PlannerContractError) as error:
        gateway.commit("mdl_house", {"patch_valid": True, "score": 1.0})

    assert error.value.path == "/request"
    assert events == []


def test_commit_request_rejects_non_domain_intent() -> None:
    with pytest.raises(PlannerContractError) as error:
        AgentPatchCommitRequest(cast(DesignIntent, object()), _proposal())

    assert error.value.path == "/request/intent"
