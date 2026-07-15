from __future__ import annotations

from typing import Any

import pytest

from ai_parametric_architect.agents import (
    ArchitecturePlannerAgent,
    PatchGeneratorAgent,
    RequirementAgent,
)
from ai_parametric_architect.application import (
    AgentAuthorizationGateway,
    AgentPatchCommitRequest,
    EditingService,
)
from ai_parametric_architect.composition import create_editing_service
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    PatchOperation,
    PatchProposal,
    PlannerContractError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.evaluation import (
    DetachedPatchValidator,
    EvaluationRunner,
    Scenario,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.planning import (
    RuleBasedFloorPlanPlanner,
    RuleBasedPlanner,
    RuleBasedRequirementParser,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy
from ai_parametric_architect.validation import ModelValidator


def _system_identity() -> TrustedAuditIdentity:
    return TrustedAuditIdentity(
        actor_id="security-test-bootstrap",
        actor_type=AuditActorType.SYSTEM,
        trace_id="trace:security-bootstrap",
    )


def _agent_identity() -> TrustedAuditIdentity:
    return TrustedAuditIdentity(
        actor_id="architecture-planning-agent",
        actor_type=AuditActorType.AGENT,
        agent_version="test-v1",
        trace_id="trace:security-agent",
    )


def _initialized_editing(model: dict[str, Any]) -> EditingService:
    editing = create_editing_service()
    editing.initialize(
        model,
        provenance="fixture:security-authorization",
        rationale="Initialize an authoritative model for an authorization test.",
        audit_identity=_system_identity(),
    )
    return editing


def _gateway(editing: EditingService) -> AgentAuthorizationGateway:
    return AgentAuthorizationGateway(
        editing,
        ArchitecturePlanningAuthorizationPolicy(),
        _agent_identity(),
    )


def _intent() -> DesignIntent:
    return DesignIntent(building_type="house", area=60, rooms=("bedroom",))


def test_malicious_geometry_patch_is_denied_before_validation_or_commit(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialized_editing(valid_simple_house)
    current = editing.current("mdl_simple_house")
    intent = _intent()
    canonical = RuleBasedPlanner().plan(intent, current)
    assert canonical is not None
    malicious = PatchProposal(
        base_model_id=canonical.base_model_id,
        base_revision=canonical.base_revision,
        operations=(
            PatchOperation(
                "replace",
                "/entities/rooms/rom_living/geometry/exterior/0/0",
                999,
            ),
            *canonical.operations[1:],
        ),
        provenance="planner:untrusted-output",
        rationale="Attempt to smuggle a geometry mutation into a semantic plan.",
        affected_entity_ids=canonical.affected_entity_ids,
    )

    with pytest.raises(PlannerContractError):
        _gateway(editing).commit(
            "mdl_simple_house",
            AgentPatchCommitRequest(intent, malicious),
        )

    assert editing.current("mdl_simple_house").revision_number == 0
    assert len(editing.audit_log("mdl_simple_house")) == 1


def test_evaluation_outputs_are_evidence_not_commit_authority(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialized_editing(valid_simple_house)
    current = editing.current("mdl_simple_house")
    intent = _intent()
    scenario = Scenario(
        input_requirement="Create a 60 sqm one bedroom house",
        expected_intent=intent,
        expected_constraints=(),
    )
    report = EvaluationRunner(
        intent_agent=RequirementAgent(RuleBasedRequirementParser()),
        floor_plan_agent=ArchitecturePlannerAgent(RuleBasedFloorPlanPlanner()),
        patch_generator=PatchGeneratorAgent(RuleBasedPlanner()),
        patch_validator=DetachedPatchValidator(
            JsonPatchEngine(),
            ModelValidator(ShapelyGeometryEngine()),
        ),
    ).run((scenario,), current)
    assert report.scenarios[0].patch_valid
    gateway = _gateway(editing)

    for evidence in (report, report.scenarios[0]):
        with pytest.raises(PlannerContractError) as error:
            gateway.commit("mdl_simple_house", evidence)
        assert error.value.path == "/request"

    assert editing.current("mdl_simple_house").revision_number == 0
    assert len(editing.audit_log("mdl_simple_house")) == 1


def test_policy_authorized_proposal_runs_validation_and_creates_a_revision(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = _initialized_editing(valid_simple_house)
    current = editing.current("mdl_simple_house")
    intent = _intent()
    proposal = RuleBasedPlanner().plan(intent, current)
    assert proposal is not None

    committed = _gateway(editing).commit(
        "mdl_simple_house",
        AgentPatchCommitRequest(intent, proposal),
    )

    assert committed.revision_number == 1
    assert ModelValidator(ShapelyGeometryEngine()).validate(committed.document).valid
    audit_entry = editing.audit_log("mdl_simple_house")[-1]
    assert audit_entry.actor_id == "architecture-planning-agent"
    assert audit_entry.actor_type is AuditActorType.AGENT
    assert audit_entry.agent_version == "test-v1"
    assert audit_entry.trace_id == "trace:security-agent"
    assert audit_entry.provenance == proposal.provenance
