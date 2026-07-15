from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ai_parametric_architect.agent_trace import AgentTraceRecorder, TenantTraceHasher
from ai_parametric_architect.agents import (
    ArchitecturePlannerAgent,
    PatchGeneratorAgent,
    RequirementAgent,
)
from ai_parametric_architect.application import (
    AgentAuthorizationGateway,
    AgentPatchCommitRequest,
)
from ai_parametric_architect.composition import create_editing_service, create_service
from ai_parametric_architect.domain import (
    AuditActorType,
    DesignIntent,
    ModelRevision,
    PatchProposal,
    TrustedAuditIdentity,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.evaluation import (
    DetachedPatchValidator,
    EvaluationRunner,
    Scenario,
)
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.llm import (
    LLMFloorPlanPlanner,
    LLMPatchProposalGenerator,
    LLMRequirementParser,
    MockLLMProvider,
)
from ai_parametric_architect.planning import (
    FloorPlanProposal,
    RuleBasedFloorPlanPlanner,
    RuleBasedPlanner,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy
from ai_parametric_architect.validation import ModelValidator


@dataclass(frozen=True, slots=True)
class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 15, 6, 0, tzinfo=UTC)


def test_mock_llm_evaluation_trace_and_trusted_commit_form_one_safe_system(
    valid_simple_house: dict[str, Any],
) -> None:
    original = deepcopy(valid_simple_house)
    revision = ModelRevision(
        model_id="mdl_simple_house",
        revision_number=0,
        created_at=datetime(2026, 7, 15, 5, 0, tzinfo=UTC),
        parent_revision=None,
        document=valid_simple_house,
    )
    expected_intent = DesignIntent(
        building_type="house",
        area=60,
        rooms=("bedroom",),
    )
    expected_plan = RuleBasedFloorPlanPlanner().plan(expected_intent)
    expected_patch = RuleBasedPlanner().generate(expected_plan, revision)
    assert expected_patch is not None
    provider = MockLLMProvider((expected_intent, expected_plan, expected_patch))
    scenario = Scenario(
        input_requirement="Create a 60 sqm one bedroom house",
        expected_intent=expected_intent,
        expected_constraints=(),
    )
    runner = EvaluationRunner(
        intent_agent=RequirementAgent(LLMRequirementParser(provider)),
        floor_plan_agent=ArchitecturePlannerAgent(LLMFloorPlanPlanner(provider)),
        patch_generator=PatchGeneratorAgent(LLMPatchProposalGenerator(provider)),
        patch_validator=DetachedPatchValidator(
            JsonPatchEngine(),
            ModelValidator(ShapelyGeometryEngine()),
        ),
    )

    report = runner.run((scenario,), revision)

    assert report.metrics.intent_extraction_accuracy.value == 1.0
    assert report.metrics.plan_validity.value == 1.0
    assert report.metrics.patch_validation_success_rate.value == 1.0
    result = report.scenarios[0]
    assert result.extracted_intent is not None
    assert result.floor_plan is not None
    assert result.patch_proposal is not None
    assert result.patch_proposal == expected_patch
    assert provider.remaining_responses == 0
    assert tuple(request.output_type for request in provider.requests) == (
        DesignIntent,
        FloorPlanProposal,
        PatchProposal,
    )
    assert revision.document == original
    assert valid_simple_house == original

    recorder = AgentTraceRecorder(
        FixedClock(),
        TenantTraceHasher(
            tenant_id="integration-tenant",
            key_id="integration-key-1",
            key=b"integration-trace-key-material-0001",
        ),
    )
    pipeline_trace_id = "trace-evaluation-integration"
    traces = (
        recorder.record(
            agent_name="requirement-agent",
            agent_version="1.0.0",
            trace_id=pipeline_trace_id,
            input_value={"input_requirement": scenario.input_requirement},
            output_value=result.extracted_intent.to_dict(),
        ),
        recorder.record(
            agent_name="architecture-planner-agent",
            agent_version="1.0.0",
            trace_id=pipeline_trace_id,
            input_value=result.extracted_intent.to_dict(),
            output_value=result.floor_plan.to_dict(),
        ),
        recorder.record(
            agent_name="patch-generator-agent",
            agent_version="1.0.0",
            trace_id=pipeline_trace_id,
            input_value={
                "model_id": revision.model_id,
                "revision": revision.revision_number,
                "plan": result.floor_plan.to_dict(),
            },
            output_value=result.patch_proposal.to_dict(),
        ),
    )
    serialized_traces = json.dumps([trace.to_dict() for trace in traces], sort_keys=True)
    assert scenario.input_requirement not in serialized_traces
    assert "chain_of_thought" not in serialized_traces
    assert "world_model" not in serialized_traces

    editing = create_editing_service()
    initialization_identity = TrustedAuditIdentity(
        actor_id="evaluation-fixture",
        actor_type=AuditActorType.SYSTEM,
        trace_id="trace:evaluation-fixture",
    )
    patch_identity = TrustedAuditIdentity(
        actor_id="patch-generator-agent",
        actor_type=AuditActorType.AGENT,
        agent_version="1.0.0",
        trace_id=pipeline_trace_id,
    )
    editing.initialize(
        valid_simple_house,
        provenance="fixture:evaluatable-agent-system",
        rationale="Initialize the authoritative JSON revision.",
        audit_identity=initialization_identity,
    )
    authorization_gateway = AgentAuthorizationGateway(
        editing,
        ArchitecturePlanningAuthorizationPolicy(),
        patch_identity,
    )
    committed = authorization_gateway.commit(
        "mdl_simple_house",
        AgentPatchCommitRequest(result.extracted_intent, result.patch_proposal),
    )

    assert committed.revision_number == 1
    assert create_service().validate(committed.document).valid
    assert valid_simple_house == original
    patch_audit = editing.audit_log("mdl_simple_house")[-1]
    assert patch_audit.trace_id == traces[-1].trace_id == pipeline_trace_id
    assert patch_audit.actor_id == traces[-1].agent_name
    assert patch_audit.agent_version == traces[-1].agent_version
